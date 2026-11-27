"""Endpoints de solicitudes (Documento de Diseño, API REST /api/v1/solicitudes)."""
from __future__ import annotations

import re
import tempfile
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pipeline.fasta import validar_fasta

from .. import acceso, auditoria, recomendacion
from ..config import get_settings
from ..db import obtener_sesion
from ..esquemas import ListaSolicitudes, MotivoIn, Recomendacion, SolicitudDetalle, SolicitudResumen
from ..estados import TransicionInvalida, cambiar_estado, historial_de
from ..models import (
    ESTADOS_SOLICITUD,
    MECANISMOS,
    TIPOS_MUESTRA,
    Aislado,
    Solicitud,
    Trabajo,
    Usuario,
)
from ..registro import crear_solicitud

router = APIRouter(prefix="/api/v1/solicitudes", tags=["Solicitudes"])

TAMANO_MAXIMO = 60 * 1024 * 1024  # un genoma de Klebsiella ocupa unos 5,5 MB; el tope evita subidas absurdas
EXTENSIONES = (".fasta", ".fna", ".fa", ".fas", ".fasta.gz", ".fna.gz", ".fa.gz", ".fas.gz")


# Texto que ve el usuario para cada estado. `en_analisis` no está aquí: su texto depende de si ya
# hay análisis guardado (ver `etapa_visible`).
ETAPAS = {
    "registrada": "En cola de análisis",
    "prediccion_lista": "Predicción lista",
    "en_validacion": "En validación",
    "emitida": "Recomendación emitida",
    "cerrada": "Cerrada",
    "rechazada": "Rechazada",
    "anulada": "Anulada",
    "error": "Error en el análisis",
}


def etapa_visible(estado: str, tiene_analisis: bool) -> str:
    """Texto de la etapa. `en_analisis` con análisis guardado significa que el pipeline terminó y que
    el worker de predicción está generando el ranking de fagos."""
    if estado == "en_analisis":
        return "Análisis genómico completo; generando la predicción" if tiene_analisis else "Analizando el genoma"
    return ETAPAS.get(estado, estado)


def _extension(nombre: str) -> str | None:
    """Extensión admitida del nombre de archivo, o None si no es una de `EXTENSIONES`."""
    minusculas = nombre.lower()
    # Se prueban de la más larga a la más corta: ".fasta.gz" debe ganarle a ".fasta".
    return next((e for e in sorted(EXTENSIONES, key=len, reverse=True) if minusculas.endswith(e)), None)


def _resumen(sol: Solicitud, aislado: Aislado) -> dict:
    """Arma el diccionario de `SolicitudResumen`; sin análisis, los campos genómicos van en None."""
    return {
        "id": sol.id,
        "codigo_interno": aislado.codigo_interno,
        "estado": sol.estado,
        "etapa": etapa_visible(sol.estado, sol.analizado_en is not None),
        "motivo_estado": sol.motivo_estado,
        "creada_en": sol.creada_en,
        "actualizada_en": sol.actualizada_en,
        "especie_detectada": sol.especie_detectada,
        "locus_k_tipo": sol.locus_k_tipo,
        "locus_k_confianza": sol.locus_k_confianza,
    }


def _guardar_subida(archivo: UploadFile, carpeta: Path, extension: str) -> Path:
    """Copia el archivo subido a `carpeta` por bloques, cortando si pasa del tamaño máximo."""
    destino = carpeta / f"genoma{extension}"
    total = 0
    with open(destino, "wb") as f:
        # Se lee de a 1 MiB: así un archivo enorme se rechaza sin haberlo cargado entero en memoria.
        while bloque := archivo.file.read(1 << 20):
            total += len(bloque)
            if total > TAMANO_MAXIMO:
                raise HTTPException(413, f"El archivo supera el máximo de {TAMANO_MAXIMO // (1024 * 1024)} MB")
            f.write(bloque)
    if total == 0:
        raise HTTPException(422, "El archivo está vacío")
    return destino


@router.post("", response_model=SolicitudResumen, status_code=201, summary="Registrar un genoma y encolar su análisis")
def crear(
    archivo: UploadFile = File(..., description="Genoma ensamblado en FASTA, plano o .gz"),
    codigo_interno: str = Form(..., description="Código del aislado en el centro"),
    tipo_muestra: str = Form("otra"),
    mecanismo_resistencia: str = Form("desconocido"),
    especie_declarada: str = Form("Klebsiella pneumoniae"),
    fecha_aislamiento: date | None = Form(None),
    observaciones: str | None = Form(None),
    clinico_id: uuid.UUID | None = Form(None, description="Clínico solicitante del mismo centro; por defecto, el propio técnico"),
    request: Request = None,
    tecnico: Usuario = Depends(acceso.requiere("TEC")),
    session: Session = Depends(obtener_sesion),
):
    """Valida el formulario y el FASTA, guarda el genoma y deja el trabajo de análisis en cola (RF-07, RF-09 a RF-11).

    Responde de inmediato (201): el análisis lo hace después el worker, no esta petición.
    """
    # Validaciones baratas primero: se rechaza antes de tocar el disco o la base de datos.
    codigo = codigo_interno.strip()
    if not 1 <= len(codigo) <= 80:
        raise HTTPException(422, "El código interno debe tener entre 1 y 80 caracteres")
    if tipo_muestra not in TIPOS_MUESTRA:
        raise HTTPException(422, f"tipo_muestra debe ser uno de: {', '.join(TIPOS_MUESTRA)}")
    if mecanismo_resistencia not in MECANISMOS:
        raise HTTPException(422, f"mecanismo_resistencia debe ser uno de: {', '.join(MECANISMOS)}")
    if fecha_aislamiento is not None and fecha_aislamiento > date.today():
        raise HTTPException(422, "La fecha de aislamiento no puede ser futura")
    extension = _extension(archivo.filename or "")
    if extension is None:
        raise HTTPException(422, f"Formato no admitido. Use una de estas extensiones: {', '.join(EXTENSIONES)}")
    if clinico_id is not None:
        clinico = session.get(Usuario, clinico_id)
        if clinico is None or clinico.rol != "CLI" or not clinico.activo or clinico.centro_id != tecnico.centro_id:
            raise HTTPException(422, "El clínico solicitante debe ser un clínico activo de tu centro")

    genomas_dir = Path(get_settings().genomas_dir)
    genomas_dir.mkdir(parents=True, exist_ok=True)
    # El nombre que envía el navegador solo se guarda como texto informativo, ya limpiado:
    # nunca forma parte de una ruta del disco.
    nombre_original = re.sub(r"[^A-Za-z0-9._-]", "_", Path(archivo.filename or "genoma").name)[:200]
    # Carpeta temporal dentro de genomas_dir (mismo volumen): se borra sola al salir del `with`, con éxito o con error.
    with tempfile.TemporaryDirectory(dir=genomas_dir) as tmp:
        ruta = _guardar_subida(archivo, Path(tmp), extension)
        fasta = validar_fasta(ruta)
        if not fasta.valido:
            raise HTTPException(422, "FASTA inválido: " + "; ".join(fasta.errores))
        try:
            sol = crear_solicitud(
                session,
                ruta,
                codigo,
                genomas_dir,
                especie_declarada=especie_declarada.strip() or "Klebsiella pneumoniae",
                tipo_muestra=tipo_muestra,
                mecanismo_resistencia=mecanismo_resistencia,
                fecha_aislamiento=fecha_aislamiento,
                observaciones=(observaciones or "").strip() or None,
                codigo_unico=False,
                nombre_original=nombre_original,
                usuario=tecnico,
                solicitante_id=clinico_id,
            )
            origen = acceso.origen_de(request)
            # Un evento por cada cosa que se registró (RF-48): el aislado, su genoma y la solicitud.
            auditoria.registrar(session, "aislado_registrado", usuario=tecnico, entidad="aislado", entidad_id=sol.aislado_id, origen=origen,
                                detalle={"codigo_interno": codigo, "tipo_muestra": tipo_muestra})
            auditoria.registrar(session, "genoma_cargado", usuario=tecnico, entidad="aislado", entidad_id=sol.aislado_id, origen=origen,
                                detalle={"nombre_original": nombre_original, "sha256": session.get(Aislado, sol.aislado_id).sha256})
            auditoria.registrar(session, "solicitud_creada", usuario=tecnico, entidad="solicitud", entidad_id=sol.id, origen=origen)
            session.commit()
        except IntegrityError:
            # La restricción única (centro, código) de la base de datos es la que detecta el duplicado.
            session.rollback()
            raise HTTPException(409, f"Ya existe un aislado con el código '{codigo}' en este centro") from None
    aislado = session.get(Aislado, sol.aislado_id)
    return _resumen(sol, aislado)


@router.get("", response_model=ListaSolicitudes, summary="Listar solicitudes, las más recientes primero")
def listar(
    estado: str | None = Query(None, description="Filtra por estado"),
    desde: date | None = Query(None, description="Creadas desde esta fecha (inclusive)"),
    hasta: date | None = Query(None, description="Creadas hasta esta fecha (inclusive)"),
    centro_id: uuid.UUID | None = Query(None, description="Solo el administrador puede filtrar por centro"),
    limite: int = Query(50, ge=1, le=200),
    desplazamiento: int = Query(0, ge=0),
    usuario: Usuario = Depends(acceso.requiere("TEC", "MIC", "CLI", "ADM")),
    session: Session = Depends(obtener_sesion),
):
    """Lista paginada de las solicitudes que el usuario puede ver (RF-06), con filtros por estado, fechas y centro (RF-13)."""
    if estado is not None and estado not in ESTADOS_SOLICITUD:
        raise HTTPException(422, f"estado debe ser uno de: {', '.join(ESTADOS_SOLICITUD)}")
    filtro = acceso.solicitudes_visibles(usuario)
    if estado:
        filtro.append(Solicitud.estado == estado)
    if desde:
        filtro.append(func.date(Solicitud.creada_en) >= desde.isoformat())
    if hasta:
        filtro.append(func.date(Solicitud.creada_en) <= hasta.isoformat())
    if centro_id and usuario.rol == "ADM":
        filtro.append(Solicitud.centro_id == centro_id)
    total = session.scalar(select(func.count()).select_from(Solicitud).where(*filtro)) or 0
    filas = session.execute(
        select(Solicitud, Aislado)
        .join(Aislado, Aislado.id == Solicitud.aislado_id)
        .where(*filtro)
        .order_by(Solicitud.creada_en.desc())
        .limit(limite)
        .offset(desplazamiento)
    ).all()
    return {"total": total, "items": [_resumen(s, a) for s, a in filas]}


@router.get("/{solicitud_id}", response_model=SolicitudDetalle, summary="Detalle de una solicitud")
def detalle(solicitud_id: uuid.UUID, usuario: Usuario = Depends(acceso.requiere("TEC", "MIC", "CLI", "ADM")),
            session: Session = Depends(obtener_sesion)):
    """Todo lo asociado a una solicitud: aislado, genoma, análisis, trabajos e historial de estados (RF-14)."""
    sol = acceso.solicitud_visible_o_404(session, usuario, solicitud_id)
    aislado = session.get(Aislado, sol.aislado_id)
    trabajos = session.execute(select(Trabajo).where(Trabajo.solicitud_id == sol.id).order_by(Trabajo.creado_en)).scalars().all()

    salida = _resumen(sol, aislado)
    salida["aislado"] = aislado
    salida["genoma"] = aislado  # el genoma vive en las columnas del aislado: `GenomaOut` toma de ahí sus campos
    salida["trabajos"] = trabajos
    salida["historial"] = historial_de(session, sol)
    # Quién la registró, quién la pidió y quién la valida: nombres, no identificadores (los usuarios no se borran, siempre existen).
    def nombre(uid):
        return session.get(Usuario, uid).nombre if uid else None

    salida["registrada_por"] = nombre(sol.creada_por)
    salida["solicitante"] = nombre(sol.solicitante_id)
    salida["asignada_a"] = nombre(sol.asignada_a)
    if sol.analizado_en is not None:
        # La verificación de especie no tiene columna propia: viaja en el JSON `parametros_analisis`.
        parametros = sol.parametros_analisis or {}
        salida["analisis"] = {
            "especie_detectada": sol.especie_detectada,
            "distancia_especie": sol.distancia_especie,
            "especie_verificada": parametros.get("especie_verificada"),
            "especie_referencia": parametros.get("especie_referencia"),
            "locus_k_tipo": sol.locus_k_tipo,
            "locus_k_confianza": sol.locus_k_confianza,
            "n_genes": sol.n_genes,
            "n_proteinas": sol.n_proteinas,
            "versiones_herramientas": sol.versiones_herramientas or {},
            "creado_en": sol.analizado_en,
        }
    return salida


@router.post("/{solicitud_id}/anular", response_model=SolicitudResumen, summary="Anular una solicitud")
def anular(solicitud_id: uuid.UUID, datos: MotivoIn | None = None, usuario: Usuario = Depends(acceso.requiere("TEC", "ADM")),
           session: Session = Depends(obtener_sesion)):
    """Pasa la solicitud a `anulada` (si la máquina de estados lo permite) y cancela su trabajo pendiente (RF-15)."""
    sol = acceso.solicitud_visible_o_404(session, usuario, solicitud_id)
    try:
        cambiar_estado(session, sol, "anulada", usuario_id=usuario.id, motivo=(datos.motivo if datos else None) or "Anulada por el usuario")
    except TransicionInvalida:
        raise HTTPException(409, f"No se puede anular una solicitud en estado '{sol.estado}'") from None
    # Un trabajo que aún no empezó no debe ejecutarse sobre una solicitud anulada.
    session.execute(
        update(Trabajo)
        .where(Trabajo.solicitud_id == sol.id, Trabajo.estado == "pendiente")
        .values(estado="fallido", error="solicitud anulada")
    )
    session.commit()
    return _resumen(sol, session.get(Aislado, sol.aislado_id))


@router.post("/{solicitud_id}/reintentar", response_model=SolicitudResumen, summary="Reintentar una solicitud con error")
def reintentar(solicitud_id: uuid.UUID, request: Request, usuario: Usuario = Depends(acceso.requiere("TEC", "ADM")),
               session: Session = Depends(obtener_sesion)):
    """Encola un nuevo trabajo para una solicitud en `error`; el worker la devuelve a `en_analisis` (RF-16)."""
    sol = acceso.solicitud_visible_o_404(session, usuario, solicitud_id)
    if sol.estado != "error":
        raise HTTPException(409, f"Solo se reintenta una solicitud en estado 'error' (actual: '{sol.estado}')")
    # Evita encolar dos veces el mismo análisis si el usuario pulsa el botón más de una vez.
    activo = session.scalar(
        select(func.count())
        .select_from(Trabajo)
        .where(Trabajo.solicitud_id == sol.id, Trabajo.tipo == "pipeline", Trabajo.estado.in_(("pendiente", "en_curso")))
    )
    if activo:
        raise HTTPException(409, "Ya hay un análisis en cola para esta solicitud")
    # Si el análisis genómico ya existe, el fallo fue de la predicción y solo se repite ese paso.
    ya_analizada = sol.analizado_en is not None
    session.add(Trabajo(tipo="prediccion" if ya_analizada else "pipeline", solicitud_id=sol.id))
    auditoria.registrar(session, "reintento_solicitud", usuario=usuario, entidad="solicitud", entidad_id=sol.id, origen=acceso.origen_de(request))
    session.commit()
    return _resumen(sol, session.get(Aislado, sol.aislado_id))


@router.get("/{solicitud_id}/recomendacion", response_model=Recomendacion, summary="Evidencia conocida para el aislado")
def obtener_recomendacion(solicitud_id: uuid.UUID, usuario: Usuario = Depends(acceso.requiere("TEC", "MIC", "CLI", "ADM")),
                          session: Session = Depends(obtener_sesion)):
    """Evidencia conocida para el locus K del aislado. No es una predicción: ver recomendacion.py.

    El campo `estado` de la respuesta distingue cuatro casos: `no_aplica`, `analisis_pendiente`,
    `evidencia_disponible` y `sin_evidencia` (con el motivo en `mensaje`).
    """
    sol = acceso.solicitud_visible_o_404(session, usuario, solicitud_id)
    base = {
        "solicitud_id": sol.id,
        "aviso": recomendacion.AVISO,
        "banco": recomendacion.estadisticas_banco(session),
        "candidatos": [],
        "perfil": None,
    }
    # Casos que no llegan a buscar evidencia: solicitud muerta o análisis todavía sin terminar.
    if sol.estado in ("rechazada", "anulada"):
        return {**base, "estado": "no_aplica", "mensaje": f"La solicitud está {sol.estado}: no hay análisis que usar."}
    if sol.analizado_en is None:
        return {**base, "estado": "analisis_pendiente", "mensaje": "El análisis genómico todavía no termina."}

    base["perfil"] = {
        "especie_detectada": sol.especie_detectada,
        "locus_k_tipo": sol.locus_k_tipo,
        "locus_k_confianza": sol.locus_k_confianza,
    }
    candidatos = recomendacion.candidatos_por_evidencia(session, sol.locus_k_tipo)
    if candidatos:
        return {
            **base,
            "estado": "evidencia_disponible",
            "mensaje": f"Fagos con interacciones positivas conocidas sobre aislados de locus {sol.locus_k_tipo}.",
            "candidatos": candidatos,
        }
    # Sin candidatos: se explica por qué, en orden de causa (sin locus, banco sin interacciones, locus sin positivas).
    if not recomendacion.locus_tipificado(sol.locus_k_tipo):
        motivo = "El locus K del aislado no se pudo tipificar, así que no hay con qué buscar evidencia."
    elif base["banco"]["interacciones_conocidas"] == 0:
        motivo = (
            f"El banco tiene {base['banco']['fagos_total']} fagos de Klebsiella, pero ninguna interacción fago-cepa cargada; "
            "sin esos datos SIRFA no puede decir cuáles son compatibles con este aislado."
        )
    else:
        motivo = f"Ningún fago del banco tiene interacciones positivas registradas sobre el locus {sol.locus_k_tipo}."
    return {**base, "estado": "sin_evidencia", "mensaje": motivo}
