"""Cola de trabajos y procesamiento de una solicitud (decisión D-02, RF-24, RF-16).

Los workers toman trabajos con `FOR UPDATE SKIP LOCKED`, de modo que varios procesos pueden
consumir la misma cola sin pisarse. Cada intento fallido se reintenta con espera creciente y,
al tercero, la solicitud pasa a Error.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.estados import cambiar_estado
from app.models import AnalisisGenomico, Aislado, Genoma, Solicitud, Trabajo

from .especie import ResultadoEspecie, es_kpneumoniae
from .fasta import validar_fasta
from .genes import ResultadoGenes
from .herramientas import ErrorHerramienta
from .locus_k import ResultadoLocusK
from .qc import RECHAZADO, ResultadoQC, Umbrales, calcular_metricas, clasificar

MAX_INTENTOS = 3
ESPERA_BASE_SEGUNDOS = 30  # la espera antes de reintentar se duplica en cada intento: 30 s, 60 s...


@dataclass
class Pasos:
    """Las herramientas que usa el pipeline; en las pruebas se reemplazan por versiones falsas."""

    especie: Callable[[str, str], ResultadoEspecie]  # (ruta del genoma, especie declarada)
    locus_k: Callable[[str, Path], ResultadoLocusK]  # (ruta del genoma, carpeta de trabajo)
    genes: Callable[[str, Path], ResultadoGenes]  # (ruta del genoma, carpeta de trabajo)
    guardar_crudo: Callable[[dict], str]  # guarda el resultado completo en MongoDB y devuelve su _id
    versiones: Callable[[], dict]


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def reclamar(session: Session, tipo: str, worker_id: str, ahora: datetime | None = None) -> Trabajo | None:
    """Toma el trabajo pendiente más antiguo del tipo dado y lo marca En curso.

    El bloqueo de `FOR UPDATE` dura hasta el commit o rollback de la sesión de quien llama: mientras
    tanto, otros workers saltan esa fila (`SKIP LOCKED`) y toman la siguiente.
    """
    ahora = ahora or _ahora()
    consulta = (
        select(Trabajo)
        .where(
            Trabajo.tipo == tipo,
            Trabajo.estado == "pendiente",
            # Un trabajo en espera de reintento solo se toma cuando llega su hora.
            or_(Trabajo.siguiente_intento_en.is_(None), Trabajo.siguiente_intento_en <= ahora),
        )
        .order_by(Trabajo.creado_en)  # el más antiguo primero (cola FIFO)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    trabajo = session.execute(consulta).scalar_one_or_none()
    if trabajo is not None:
        trabajo.estado = "en_curso"
        trabajo.bloqueado_por = worker_id
        trabajo.intentos += 1
        session.flush()
    return trabajo


def _guardar_qc(genoma: Genoma, qc: ResultadoQC) -> None:
    """Copia las métricas y el veredicto del QC a las columnas del genoma."""
    m = qc.metricas
    genoma.qc_longitud, genoma.qc_contigs, genoma.qc_n50 = m.longitud, m.contigs, m.n50
    genoma.qc_gc, genoma.qc_prop_ambiguas, genoma.qc_resultado = m.gc, m.prop_ambiguas, qc.resultado


def _rechazar(session: Session, solicitud: Solicitud, trabajo: Trabajo, motivo: str) -> None:
    """Pasa la solicitud a Rechazada. El trabajo termina en `ok`: cumplió su tarea, el rechazo es un resultado, no un fallo."""
    cambiar_estado(session, solicitud, "rechazada", motivo=motivo)
    trabajo.estado, trabajo.error, trabajo.terminado_en = "ok", None, _ahora()


def _ejecutar(session: Session, trabajo: Trabajo, sol: Solicitud, pasos: Pasos, umbrales: Umbrales | None, salida: Path) -> None:
    """Aplica en orden los pasos del pipeline; el primero que rechaza el genoma termina el proceso."""
    genoma = session.get(Genoma, sol.genoma_id)
    aislado = session.get(Aislado, sol.aislado_id)

    # 1. El archivo debe ser un FASTA de ADN válido (la API ya lo revisó al subirlo; se repite por seguridad).
    fasta = validar_fasta(genoma.ruta_archivo)
    if not fasta.valido:
        _rechazar(session, sol, trabajo, "FASTA inválido: " + "; ".join(fasta.errores))
        return

    # 2. Control de calidad del ensamblado.
    qc = clasificar(calcular_metricas(genoma.ruta_archivo), umbrales)
    _guardar_qc(genoma, qc)
    if qc.resultado == RECHAZADO:
        _rechazar(session, sol, trabajo, "calidad del genoma: " + "; ".join(qc.motivos))
        return

    # 3. Especie: el MVP solo acepta Klebsiella pneumoniae. Se explica por qué si no lo es.
    esp = pasos.especie(genoma.ruta_archivo, aislado.especie_declarada)
    if not es_kpneumoniae(esp.especie):
        detectada = esp.especie or "no identificada"
        partes = []
        if esp.verificada and esp.distancia is not None and esp.referencia:
            partes.append(f"Mash {esp.distancia:.4f} a {esp.referencia}")
        if esp.motivo:
            partes.append(esp.motivo)
        detalle = f" ({'; '.join(partes)})" if partes else ""
        _rechazar(session, sol, trabajo, f"especie detectada: {detectada}{detalle}; el MVP solo acepta Klebsiella pneumoniae")
        return

    # 4 y 5. Locus K (Kaptive) y genes (Prodigal). Si una herramienta falla lanzan ErrorHerramienta,
    # que `procesar_pipeline` convierte en reintento.
    carpeta = salida / str(sol.id)
    locus = pasos.locus_k(genoma.ruta_archivo, carpeta / "locus_k")
    genes = pasos.genes(genoma.ruta_archivo, carpeta / "genes")

    # Documento completo para MongoDB; en PostgreSQL queda solo el resumen consultable.
    crudo = {
        "solicitud_id": str(sol.id),
        "qc": qc.como_dict(),
        "especie": {
            "detectada": esp.especie,
            "distancia": esp.distancia,
            "verificada": esp.verificada,
            "referencia": esp.referencia,
            "segunda_especie": esp.segunda_especie,
            "segunda_distancia": esp.segunda_distancia,
        },
        "locus_k": {"tipo": locus.tipo, "confianza": locus.confianza, "detalle": locus.detalle},
        "genes": {"n": genes.n_genes, "ruta_proteinas": genes.ruta_proteinas},
        "herramientas": pasos.versiones(),
    }
    mongo_id = pasos.guardar_crudo(crudo)

    session.add(
        AnalisisGenomico(
            solicitud_id=sol.id,
            especie_detectada=esp.especie,
            distancia_especie=esp.distancia,
            locus_k_tipo=locus.tipo,
            locus_k_confianza=locus.confianza,
            n_genes=genes.n_genes,
            n_proteinas=genes.n_proteinas,
            versiones_herramientas=pasos.versiones(),
            parametros={
                "umbrales_qc": (umbrales or Umbrales()).__dict__,
                "especie_verificada": esp.verificada,
                "especie_referencia": esp.referencia,
            },
            mongo_id=mongo_id,
        )
    )
    # Deja encolado el trabajo de predicción: lo atiende worker-prediction (pipeline/prediccion.py).
    session.add(Trabajo(tipo="prediccion", solicitud_id=sol.id))
    trabajo.estado, trabajo.error, trabajo.terminado_en = "ok", None, _ahora()


def procesar_pipeline(
    session: Session,
    trabajo: Trabajo,
    pasos: Pasos,
    umbrales: Umbrales | None = None,
    salida: str | Path = "/data/analisis",
) -> None:
    """Procesa un trabajo `pipeline`; deja la solicitud y el trabajo en su estado resultante.

    No hace commit: lo hace el worker al volver, para que el bloqueo del trabajo dure todo el proceso.
    """
    sol = session.get(Solicitud, trabajo.solicitud_id)
    # Desde `registrada` (primer intento) o `error` (reintento manual) la solicitud pasa a En análisis.
    if sol.estado in ("registrada", "error"):
        cambiar_estado(session, sol, "en_analisis")
        session.flush()
    try:
        # begin_nested() abre un SAVEPOINT: si `_ejecutar` falla a medias, se revierte solo lo que escribió
        # y se conserva la reclamación del trabajo hecha antes.
        with session.begin_nested():
            _ejecutar(session, trabajo, sol, pasos, umbrales, Path(salida))
    except (ErrorHerramienta, OSError) as exc:
        reintentar_o_fallar(session, trabajo, exc)


def reintentar_o_fallar(session: Session, trabajo: Trabajo, exc: Exception) -> None:
    """Falla esperada (herramienta caída, disco, etc.): se recarga el estado previo al SAVEPOINT y se reintenta.

    Con intentos pendientes el trabajo vuelve a `pendiente` con una espera creciente; al agotarse, falla y la solicitud pasa a Error."""
    session.refresh(trabajo)
    sol = session.get(Solicitud, trabajo.solicitud_id)
    trabajo.error = str(exc)
    if trabajo.intentos < MAX_INTENTOS:
        # Espera exponencial: 30 s tras el 1.er fallo, 60 s tras el 2.º.
        espera = ESPERA_BASE_SEGUNDOS * 2 ** (trabajo.intentos - 1)
        trabajo.estado = "pendiente"
        trabajo.siguiente_intento_en = _ahora() + timedelta(seconds=espera)
    else:
        # Se agotaron los intentos: el trabajo falla y la solicitud pasa a Error (el usuario puede reintentar).
        trabajo.estado, trabajo.terminado_en = "fallido", _ahora()
        cambiar_estado(session, sol, "error", motivo=str(exc))


def registrar_fallo_inesperado(session: Session, trabajo_id, motivo: str) -> None:
    """Deja el trabajo en `fallido` y la solicitud en `error`, para que el usuario pueda reintentar.

    Se usa tras un error que `procesar_pipeline` no maneja (p. ej. MongoDB caído). El rollback del worker
    devolvió la solicitud a `registrada`, y la máquina de estados solo llega a `error` desde `en_analisis`.
    """
    trabajo = session.get(Trabajo, trabajo_id)
    if trabajo is None:
        return
    trabajo.estado, trabajo.error, trabajo.terminado_en = "fallido", motivo, _ahora()
    sol = session.get(Solicitud, trabajo.solicitud_id)
    if sol.estado == "registrada":
        cambiar_estado(session, sol, "en_analisis")
    # Una solicitud ya anulada, rechazada o en `error` no se toca.
    if sol.estado == "en_analisis":
        cambiar_estado(session, sol, "error", motivo=motivo)
