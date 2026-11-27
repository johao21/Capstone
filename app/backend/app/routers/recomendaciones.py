"""Predicción, validación y emisión de recomendaciones (RF-34 a RF-38, RF-41 a RF-46, RF-17, RF-53).

Recorrido de una solicitud: el worker de predicción deja el ranking y la solicitud en `prediccion_lista`; un microbiólogo la
toma (`en_validacion`), descarta candidatos con justificación y la aprueba (`emitida`) o la rechaza. Lo emitido no se
modifica: una corrección crea otra versión y conserva la anterior (RF-46). Después de la emisión el microbiólogo registra el
resultado de los ensayos de laboratorio y cierra la solicitud (RF-17).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import acceso, auditoria, recomendacion
from ..db import obtener_sesion
from ..estados import cambiar_estado, historial_de
from ..models import (
    RESULTADOS_ENSAYO,
    Aislado,
    Auditoria,
    Fago,
    Prediccion,
    PrediccionFago,
    RecomendacionEmitida,
    Solicitud,
    Usuario,
)

router = APIRouter(prefix="/api/v1/solicitudes", tags=["Validación y recomendación"])

TOP_POR_DEFECTO = 5


# ---------------------------------------------------------------- esquemas
class ModeloOut(BaseModel):
    """Ficha del modelo que generó la predicción, tal como estaba cuando se generó."""

    version: str
    algoritmo: str = ""
    entrenado_en: datetime | None = None
    n_entrenamiento: int | None = None
    metricas: dict = {}


class EvidenciaOut(BaseModel):
    """Interacciones conocidas del fago sobre el mismo locus K del aislado (RF-37)."""

    interacciones_positivas: int
    interacciones_negativas: int
    cepas_probadas: int
    referencias: list[str]


class CandidatoPrediccion(BaseModel):
    fago_id: uuid.UUID
    accesion: str
    nombre: str
    familia: str | None = None
    genero: str | None = None
    ciclo_vida: str
    puntaje: float
    rango: int
    explicacion: dict  # SHAP: las características que más pesaron (RF-36)
    evidencia: EvidenciaOut | None = None


class PrediccionOut(BaseModel):
    id: uuid.UUID
    solicitud_id: uuid.UUID
    generada_en: datetime
    locus_k_tipo: str | None = None
    baja_confianza: bool
    motivo_baja_confianza: str | None = None
    modelo: ModeloOut
    aviso: str
    total_fagos: int
    detalle: dict = {}  # similitud máxima y cepas de entrenamiento a las que se parece el locus K del aislado
    items: list[CandidatoPrediccion]


class Descarte(BaseModel):
    fago_id: uuid.UUID
    justificacion: str = Field(min_length=5, max_length=500)


class AprobacionIn(BaseModel):
    """Lo que el microbiólogo decide: cuántos candidatos emitir y cuáles descarta (RF-43)."""

    top: int = Field(default=TOP_POR_DEFECTO, ge=1, le=20)
    descartes: list[Descarte] = Field(default_factory=list)
    observacion: str | None = Field(default=None, max_length=1000)


class JustificacionIn(BaseModel):
    justificacion: str = Field(min_length=5, max_length=1000)


class ReasignarIn(BaseModel):
    usuario_id: uuid.UUID


class ResultadoEnsayo(BaseModel):
    fago_id: uuid.UUID
    resultado: str


class EnsayosIn(BaseModel):
    resultados: list[ResultadoEnsayo] = Field(min_length=1)
    cerrar: bool = False


class CandidatoEmitido(BaseModel):
    fago_id: uuid.UUID
    accesion: str
    nombre: str
    rango: int
    puntaje: float
    descartado: bool
    justificacion: str | None = None
    resultado_ensayo: str


class VersionResumen(BaseModel):
    version: int
    estado: str
    emitida_en: datetime
    validador: str


class RecomendacionEmitidaOut(BaseModel):
    solicitud_id: uuid.UUID
    version: int
    estado: str
    emitida_en: datetime
    validador: str
    observacion: str | None = None
    advertencia: str
    modelo_version: str
    locus_k_tipo: str | None = None
    baja_confianza: bool
    candidatos: list[CandidatoEmitido]
    versiones: list[VersionResumen]


# ---------------------------------------------------------------- ayudas
def _prediccion_vigente(session: Session, solicitud_id: uuid.UUID) -> Prediccion | None:
    return session.scalars(
        select(Prediccion).where(Prediccion.solicitud_id == solicitud_id).order_by(Prediccion.generada_en.desc()).limit(1)
    ).first()


def _bloquear(session: Session, solicitud: Solicitud) -> None:
    """Relee la solicitud con bloqueo de fila: dos personas no pueden decidir sobre la misma a la vez."""
    session.refresh(solicitud, with_for_update=True)


def _validar_asignada(solicitud: Solicitud, mic: Usuario, estado: str) -> None:
    """La solicitud debe estar en el estado esperado y asignada a este microbiólogo."""
    if solicitud.estado != estado:
        raise HTTPException(409, f"La solicitud debe estar en estado '{estado}' (actual: '{solicitud.estado}')")
    if solicitud.asignada_a != mic.id:
        raise HTTPException(403, "La solicitud está asignada a otro microbiólogo")


def _nombre(session: Session, usuario_id) -> str:
    u = session.get(Usuario, usuario_id)
    return u.nombre if u else "—"


def _armar_emitida(session: Session, rec: RecomendacionEmitida, solo_aceptados: bool) -> dict:
    sol = session.get(Solicitud, rec.solicitud_id)
    pred = session.get(Prediccion, rec.prediccion_id)
    # Los candidatos viven dentro de la recomendación (JSON); de la tabla `fago` solo se toma el nombre y la accesión.
    fagos = {f.id: f for f in session.scalars(select(Fago).where(Fago.id.in_([uuid.UUID(c["fago_id"]) for c in rec.candidatos])))}
    candidatos = [
        {"fago_id": c["fago_id"], "accesion": fagos[uuid.UUID(c["fago_id"])].accesion, "nombre": fagos[uuid.UUID(c["fago_id"])].nombre,
         "rango": c["rango"], "puntaje": c["puntaje"], "descartado": c["descartado"], "justificacion": c.get("justificacion"),
         "resultado_ensayo": c.get("resultado_ensayo", "no_ensayado")}
        for c in sorted(rec.candidatos, key=lambda c: c["rango"])
        if not (solo_aceptados and c["descartado"])
    ]
    versiones = session.scalars(
        select(RecomendacionEmitida).where(RecomendacionEmitida.solicitud_id == sol.id).order_by(RecomendacionEmitida.version.desc())
    ).all()
    return {
        "solicitud_id": sol.id,
        "version": rec.version,
        "estado": rec.estado,
        "emitida_en": rec.emitida_en,
        "validador": _nombre(session, rec.validador_id),
        "observacion": rec.observacion,
        "advertencia": rec.advertencia,
        "modelo_version": pred.modelo_version,
        "locus_k_tipo": pred.locus_k_tipo,
        "baja_confianza": pred.baja_confianza,
        "candidatos": candidatos,
        "versiones": [
            {"version": v.version, "estado": v.estado, "emitida_en": v.emitida_en, "validador": _nombre(session, v.validador_id)}
            for v in versiones
        ],
    }


def _crear_version(session: Session, sol: Solicitud, pred: Prediccion, mic: Usuario, datos: AprobacionIn, version: int) -> RecomendacionEmitida:
    """Crea una versión de la recomendación con los `top` mejores candidatos que el microbiólogo no descartó."""
    ranking = session.scalars(select(PrediccionFago).where(PrediccionFago.prediccion_id == pred.id).order_by(PrediccionFago.rango)).all()
    por_fago = {r.fago_id: r for r in ranking}
    descartes = {d.fago_id: d.justificacion for d in datos.descartes}
    desconocidos = [f for f in descartes if f not in por_fago]
    if desconocidos:
        raise HTTPException(422, "Se descartó un fago que no está en el ranking de esta predicción")
    aceptados = [r for r in ranking if r.fago_id not in descartes][: datos.top]
    if not aceptados:
        raise HTTPException(422, "No queda ningún candidato: si descartas todos, rechaza la solicitud con una justificación")
    # Se conservan también los descartados que estaban dentro del top: queda constancia de por qué se sacaron.
    ultimo_rango = aceptados[-1].rango
    incluidos = aceptados + [por_fago[f] for f in descartes if por_fago[f].rango <= ultimo_rango]
    rec = RecomendacionEmitida(
        solicitud_id=sol.id, version=version, prediccion_id=pred.id, validador_id=mic.id, observacion=datos.observacion,
        advertencia=recomendacion.AVISO,
        candidatos=[
            {"fago_id": str(r.fago_id), "rango": r.rango, "puntaje": r.puntaje, "descartado": r.fago_id in descartes,
             "justificacion": descartes.get(r.fago_id), "resultado_ensayo": "no_ensayado"}
            for r in sorted(incluidos, key=lambda x: x.rango)
        ],
    )
    session.add(rec)
    session.flush()
    return rec


# ---------------------------------------------------------------- predicción y bandeja
@router.get("/{solicitud_id}/prediccion", response_model=PrediccionOut, summary="Ranking de fagos generado por el modelo")
def obtener_prediccion(solicitud_id: uuid.UUID, limite: int = 30, usuario: Usuario = Depends(acceso.requiere("MIC", "ADM")),
                       session: Session = Depends(obtener_sesion)):
    """El ranking completo ordenado de mayor a menor, con la explicación SHAP y la evidencia conocida de cada fago (RF-34 a RF-37)."""
    sol = acceso.solicitud_visible_o_404(session, usuario, solicitud_id)
    pred = _prediccion_vigente(session, sol.id)
    if pred is None:
        raise HTTPException(404, "La solicitud todavía no tiene una predicción")
    ficha = pred.modelo or {}
    limite = max(1, min(limite, 200))
    total = session.scalar(select(func.count()).select_from(PrediccionFago).where(PrediccionFago.prediccion_id == pred.id)) or 0
    filas = session.execute(
        select(PrediccionFago, Fago).join(Fago, Fago.id == PrediccionFago.fago_id)
        .where(PrediccionFago.prediccion_id == pred.id).order_by(PrediccionFago.rango).limit(limite)
    ).all()
    # Evidencia de apoyo: cuántas interacciones positivas y negativas se conocen de cada fago sobre este locus K.
    evidencia = {c["fago_id"]: c for c in recomendacion.candidatos_por_evidencia(session, pred.locus_k_tipo, limite=100_000)}
    items = []
    for pf, f in filas:
        e = evidencia.get(str(f.id))
        items.append({
            "fago_id": f.id, "accesion": f.accesion, "nombre": f.nombre, "familia": f.familia, "genero": f.genero,
            "ciclo_vida": f.ciclo_vida, "puntaje": pf.puntaje, "rango": pf.rango, "explicacion": pf.explicacion or {},
            "evidencia": {k: e[k] for k in ("interacciones_positivas", "interacciones_negativas", "cepas_probadas", "referencias")} if e else None,
        })
    return {
        "id": pred.id, "solicitud_id": sol.id, "generada_en": pred.generada_en, "locus_k_tipo": pred.locus_k_tipo,
        "baja_confianza": pred.baja_confianza, "motivo_baja_confianza": pred.motivo_baja_confianza,
        "modelo": {"version": pred.modelo_version, "algoritmo": ficha.get("algoritmo", ""), "entrenado_en": ficha.get("entrenado_en"),
                   "n_entrenamiento": ficha.get("n_entrenamiento"), "metricas": ficha.get("metricas") or {}},
        "aviso": recomendacion.AVISO, "total_fagos": total, "detalle": pred.detalle or {}, "items": items,
    }


@router.post("/{solicitud_id}/tomar", summary="El microbiólogo toma la solicitud para validarla")
def tomar(solicitud_id: uuid.UUID, request: Request, mic: Usuario = Depends(acceso.requiere("MIC")), session: Session = Depends(obtener_sesion)):
    sol = acceso.solicitud_visible_o_404(session, mic, solicitud_id)
    _bloquear(session, sol)
    if sol.estado != "prediccion_lista" or (sol.asignada_a is not None and sol.asignada_a != mic.id):
        raise HTTPException(409, "La solicitud no está disponible para tomarla")
    sol.asignada_a = mic.id
    cambiar_estado(session, sol, "en_validacion", usuario_id=mic.id)
    auditoria.registrar(session, "solicitud_tomada", usuario=mic, entidad="solicitud", entidad_id=sol.id, origen=acceso.origen_de(request))
    session.commit()
    return {"estado": sol.estado}


@router.post("/{solicitud_id}/liberar", summary="Devolver la solicitud a la bandeja sin decidir")
def liberar(solicitud_id: uuid.UUID, request: Request, mic: Usuario = Depends(acceso.requiere("MIC")), session: Session = Depends(obtener_sesion)):
    sol = acceso.solicitud_visible_o_404(session, mic, solicitud_id)
    _bloquear(session, sol)
    _validar_asignada(sol, mic, "en_validacion")
    sol.asignada_a = None
    cambiar_estado(session, sol, "prediccion_lista", usuario_id=mic.id, motivo="Devuelta a la bandeja")
    session.commit()
    return {"estado": sol.estado}


@router.post("/{solicitud_id}/reasignar", summary="El administrador reasigna la solicitud a otro microbiólogo")
def reasignar(solicitud_id: uuid.UUID, datos: ReasignarIn, request: Request, admin: Usuario = Depends(acceso.requiere("ADM")),
              session: Session = Depends(obtener_sesion)):
    sol = acceso.solicitud_visible_o_404(session, admin, solicitud_id)
    if sol.estado not in ("prediccion_lista", "en_validacion"):
        raise HTTPException(409, "Solo se reasigna una solicitud con predicción lista o en validación")
    destino = session.get(Usuario, datos.usuario_id)
    if destino is None or destino.rol != "MIC" or not destino.activo:
        raise HTTPException(422, "El destino debe ser un microbiólogo activo")
    _bloquear(session, sol)
    anterior = sol.asignada_a
    sol.asignada_a = destino.id
    auditoria.registrar(session, "solicitud_reasignada", usuario=admin, entidad="solicitud", entidad_id=sol.id, origen=acceso.origen_de(request),
                        detalle={"de": anterior, "a": destino.id})
    session.commit()
    return {"asignada_a": destino.nombre}


# ---------------------------------------------------------------- validación
@router.post("/{solicitud_id}/validacion/aprobar", response_model=RecomendacionEmitidaOut, status_code=201,
             summary="Aprobar la predicción y emitir la recomendación")
def aprobar(solicitud_id: uuid.UUID, datos: AprobacionIn, request: Request, mic: Usuario = Depends(acceso.requiere("MIC")),
            session: Session = Depends(obtener_sesion)):
    sol = acceso.solicitud_visible_o_404(session, mic, solicitud_id)
    _bloquear(session, sol)
    _validar_asignada(sol, mic, "en_validacion")
    pred = _prediccion_vigente(session, sol.id)
    if pred is None:
        raise HTTPException(409, "La solicitud no tiene predicción que aprobar")
    rec = _crear_version(session, sol, pred, mic, datos, version=1)
    cambiar_estado(session, sol, "emitida", usuario_id=mic.id)
    auditoria.registrar(session, "recomendacion_emitida", usuario=mic, entidad="solicitud", entidad_id=sol.id, origen=acceso.origen_de(request),
                        modelo_version=pred.modelo_version, detalle={"version": 1, "descartes": len(datos.descartes), "top": datos.top})
    session.commit()
    return _armar_emitida(session, rec, solo_aceptados=False)


@router.post("/{solicitud_id}/validacion/rechazar", summary="Rechazar la solicitud con una justificación")
def rechazar(solicitud_id: uuid.UUID, datos: JustificacionIn, request: Request, mic: Usuario = Depends(acceso.requiere("MIC")),
             session: Session = Depends(obtener_sesion)):
    sol = acceso.solicitud_visible_o_404(session, mic, solicitud_id)
    _bloquear(session, sol)
    _validar_asignada(sol, mic, "en_validacion")
    cambiar_estado(session, sol, "rechazada", usuario_id=mic.id, motivo=datos.justificacion)
    auditoria.registrar(session, "validacion_rechazada", usuario=mic, entidad="solicitud", entidad_id=sol.id, origen=acceso.origen_de(request),
                        detalle={"justificacion": datos.justificacion})
    session.commit()
    return {"estado": sol.estado}


# ---------------------------------------------------------------- recomendación emitida
@router.get("/{solicitud_id}/recomendacion-emitida", response_model=RecomendacionEmitidaOut, summary="Recomendación emitida vigente")
def consultar_emitida(solicitud_id: uuid.UUID, request: Request, version: int | None = None,
                      usuario: Usuario = Depends(acceso.requiere("TEC", "MIC", "CLI", "ADM")), session: Session = Depends(obtener_sesion)):
    """La versión vigente (o la indicada). Quien no es microbiólogo ni administrador no ve los candidatos descartados. Cada consulta queda auditada."""
    sol = acceso.solicitud_visible_o_404(session, usuario, solicitud_id)
    consulta = select(RecomendacionEmitida).where(RecomendacionEmitida.solicitud_id == sol.id)
    consulta = consulta.where(RecomendacionEmitida.version == version) if version else consulta.order_by(RecomendacionEmitida.version.desc())
    rec = session.scalars(consulta.limit(1)).first()
    if rec is None:
        raise HTTPException(404, "La solicitud todavía no tiene una recomendación emitida")
    salida = _armar_emitida(session, rec, solo_aceptados=usuario.rol not in ("MIC", "ADM"))
    auditoria.registrar(session, "recomendacion_consultada", usuario=usuario, entidad="solicitud", entidad_id=sol.id,
                        origen=acceso.origen_de(request), modelo_version=salida["modelo_version"], detalle={"version": rec.version})
    session.commit()
    return salida


@router.post("/{solicitud_id}/recomendacion-emitida/corregir", response_model=RecomendacionEmitidaOut, status_code=201,
             summary="Emitir una nueva versión corregida, conservando la anterior")
def corregir(solicitud_id: uuid.UUID, datos: AprobacionIn, request: Request, mic: Usuario = Depends(acceso.requiere("MIC")),
             session: Session = Depends(obtener_sesion)):
    sol = acceso.solicitud_visible_o_404(session, mic, solicitud_id)
    _bloquear(session, sol)
    _validar_asignada(sol, mic, "emitida")
    if not datos.observacion or len(datos.observacion.strip()) < 5:
        raise HTTPException(422, "Indica en la observación el motivo de la corrección")
    actual = session.scalars(
        select(RecomendacionEmitida).where(RecomendacionEmitida.solicitud_id == sol.id).order_by(RecomendacionEmitida.version.desc()).limit(1)
    ).first()
    pred = session.get(Prediccion, actual.prediccion_id)
    nueva = _crear_version(session, sol, pred, mic, datos, version=actual.version + 1)
    actual.estado = "reemplazada"
    auditoria.registrar(session, "recomendacion_corregida", usuario=mic, entidad="solicitud", entidad_id=sol.id, origen=acceso.origen_de(request),
                        modelo_version=pred.modelo_version, detalle={"version": nueva.version, "motivo": datos.observacion})
    session.commit()
    return _armar_emitida(session, nueva, solo_aceptados=False)


@router.post("/{solicitud_id}/ensayos", response_model=RecomendacionEmitidaOut, summary="Registrar los ensayos de laboratorio y, si se pide, cerrar")
def registrar_ensayos(solicitud_id: uuid.UUID, datos: EnsayosIn, request: Request, mic: Usuario = Depends(acceso.requiere("MIC")),
                      session: Session = Depends(obtener_sesion)):
    """Anota infecta / no infecta / no ensayado por candidato (RF-17). Solo agrega el resultado del ensayo: no cambia fagos, rangos ni puntajes."""
    sol = acceso.solicitud_visible_o_404(session, mic, solicitud_id)
    _bloquear(session, sol)
    _validar_asignada(sol, mic, "emitida")
    for r in datos.resultados:
        if r.resultado not in RESULTADOS_ENSAYO:
            raise HTTPException(422, f"resultado debe ser uno de: {', '.join(RESULTADOS_ENSAYO)}")
    rec = session.scalars(
        select(RecomendacionEmitida).where(RecomendacionEmitida.solicitud_id == sol.id, RecomendacionEmitida.estado == "vigente")
    ).first()
    # Los candidatos son un JSON dentro de la recomendación: se copia la lista, se anota el resultado y se vuelve a asignar entera
    # (así SQLAlchemy nota el cambio). La solicitud está bloqueada (`_bloquear`), de modo que nadie más la modifica a la vez.
    candidatos = [dict(c) for c in rec.candidatos]
    por_fago = {c["fago_id"]: c for c in candidatos}
    if any(str(r.fago_id) not in por_fago for r in datos.resultados):
        raise HTTPException(422, "Un fago del ensayo no es candidato de esta recomendación")
    for r in datos.resultados:
        por_fago[str(r.fago_id)]["resultado_ensayo"] = r.resultado
    rec.candidatos = candidatos
    auditoria.registrar(session, "ensayo_registrado", usuario=mic, entidad="solicitud", entidad_id=sol.id, origen=acceso.origen_de(request),
                        detalle={"resultados": {str(r.fago_id): r.resultado for r in datos.resultados}, "cerrada": datos.cerrar})
    if datos.cerrar:
        cambiar_estado(session, sol, "cerrada", usuario_id=mic.id)
    session.commit()
    return _armar_emitida(session, rec, solo_aceptados=False)


# ---------------------------------------------------------------- reconstrucción (RF-53)
@router.get("/{solicitud_id}/reconstruccion", summary="Reconstruir una recomendación: quién, con qué datos, qué modelo y quién validó")
def reconstruir(solicitud_id: uuid.UUID, admin: Usuario = Depends(acceso.requiere("ADM")), session: Session = Depends(obtener_sesion)):
    sol = acceso.solicitud_visible_o_404(session, admin, solicitud_id)
    aislado = session.get(Aislado, sol.aislado_id)
    pred = _prediccion_vigente(session, sol.id)
    ficha = (pred.modelo or {}) if pred else {}
    versiones = session.scalars(select(RecomendacionEmitida).where(RecomendacionEmitida.solicitud_id == sol.id).order_by(RecomendacionEmitida.version)).all()
    eventos = session.scalars(
        select(Auditoria).where(Auditoria.entidad == "solicitud", Auditoria.entidad_id == str(sol.id)).order_by(Auditoria.seq)
    ).all()
    return {
        "solicitud_id": sol.id,
        "estado": sol.estado,
        "solicitada_por": {"tecnico": _nombre(session, sol.creada_por), "clinico": _nombre(session, sol.solicitante_id), "centro_id": sol.centro_id},
        "datos": {
            "aislado": aislado.codigo_interno, "fecha_aislamiento": aislado.fecha_aislamiento, "especie_declarada": aislado.especie_declarada,
            "genoma_sha256": aislado.sha256, "qc": aislado.qc_resultado,
            "especie_detectada": sol.especie_detectada,
            "locus_k": sol.locus_k_tipo,
            "herramientas": sol.versiones_herramientas if sol.analizado_en else None,
        },
        "modelo": {"version": pred.modelo_version, "algoritmo": ficha.get("algoritmo"), "entrenado_en": ficha.get("entrenado_en"),
                   "metricas": ficha.get("metricas"), "prediccion_generada_en": pred.generada_en} if pred else None,
        "recomendaciones": [{"version": v.version, "estado": v.estado, "validada_por": _nombre(session, v.validador_id),
                             "emitida_en": v.emitida_en} for v in versiones],
        "historial_estados": [{"de": h["estado_anterior"], "a": h["estado_nuevo"], "por": _nombre(session, h["usuario_id"]) if h["usuario_id"] else "sistema",
                               "motivo": h["motivo"], "en": h["creado_en"]} for h in historial_de(session, sol)],
        "eventos_auditoria": [{"seq": e.seq, "ts": e.ts, "accion": e.accion, "usuario": e.correo, "resultado": e.resultado} for e in eventos],
    }
