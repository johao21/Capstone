"""Predicción de compatibilidad de una solicitud: genera el ranking de fagos y deja la solicitud lista para validar (RF-34 a RF-38).

Lo consume `worker-prediction` (`python -m pipeline.worker --tipos prediccion`). Parte de las proteínas que Prodigal dejó
para la solicitud, le pide el ranking al modelo (`ml.modelo.Predictor`, inyectado como `predecir` para poder probar esto sin
modelo), se queda con los fagos que un microbiólogo aprobó (RF-33) y guarda el ranking con la versión del modelo (RF-35).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auditoria
from app.estados import cambiar_estado
from app.models import AnalisisGenomico, Fago, ModeloPrediccion, Prediccion, PrediccionFago, Solicitud, Trabajo

from .herramientas import ErrorHerramienta
from .trabajos import _ahora, reintentar_o_fallar

PREFIJO_ACCESION = "PHL-"  # los fagos del conjunto PhageHostLearn se guardan en el banco como PHL-<nombre del fago>


class ErrorPrediccion(Exception):
    """Falla que reintentar no arregla (falta el modelo, las proteínas o fagos aprobados): la solicitud pasa a Error con este mensaje."""


def _predecir(session: Session, trabajo: Trabajo, sol: Solicitud, predecir: Callable[[Path], dict], salida: Path) -> None:
    modelo = session.scalars(select(ModeloPrediccion).where(ModeloPrediccion.activo.is_(True)).order_by(ModeloPrediccion.entrenado_en.desc())).first()
    if modelo is None:
        raise ErrorPrediccion("No hay un modelo entrenado y registrado: entrénalo con `python -m ml.entrenar --registrar` y reintenta")
    analisis = session.scalars(select(AnalisisGenomico).where(AnalisisGenomico.solicitud_id == sol.id).order_by(AnalisisGenomico.creado_en.desc())).first()
    if analisis is None:
        raise ErrorPrediccion("La solicitud no tiene análisis genómico")
    proteinas = salida / str(sol.id) / "genes" / "proteinas.faa"
    if not proteinas.exists():
        raise ErrorPrediccion("No se encuentran las proteínas del aislado (genes/proteinas.faa): repite el análisis genómico")

    resultado = predecir(proteinas)

    # Solo participan los fagos aprobados por un microbiólogo (RF-33) que el modelo conoce.
    aprobados = {f.accesion: f for f in session.scalars(
        select(Fago).where(Fago.estado_curaduria == "aprobado", Fago.accesion.like(f"{PREFIJO_ACCESION}%")))}
    ranking = [(aprobados[PREFIJO_ACCESION + r["fago"]], r) for r in resultado["ranking"] if PREFIJO_ACCESION + r["fago"] in aprobados]
    if not ranking:
        raise ErrorPrediccion("No hay fagos aprobados con representación para el modelo: un microbiólogo debe aprobar fagos en el banco")

    pred = Prediccion(
        solicitud_id=sol.id, modelo_id=modelo.id, locus_k_tipo=analisis.locus_k_tipo, baja_confianza=resultado["baja_confianza"],
        motivo_baja_confianza=resultado["motivo_baja_confianza"],
        detalle={"similitud_maxima": resultado["similitud_maxima"], "cepas_similares": resultado["cepas_similares"],
                 "fagos_en_el_modelo": len(resultado["ranking"]), "fagos_aprobados": len(ranking)},
    )
    session.add(pred)
    session.flush()
    for rango, (fago, r) in enumerate(ranking, start=1):  # el rango se recalcula entre los aprobados
        explicacion = dict(r["explicacion"])
        if r["evidencia"]:
            explicacion["evidencia"] = r["evidencia"]
        session.add(PrediccionFago(prediccion_id=pred.id, fago_id=fago.id, puntaje=round(r["puntaje"], 6), rango=rango, explicacion=explicacion))
    auditoria.registrar(session, "prediccion_generada", entidad="solicitud", entidad_id=sol.id, modelo_version=modelo.version,
                        detalle={"fagos": len(ranking), "baja_confianza": resultado["baja_confianza"]})
    cambiar_estado(session, sol, "prediccion_lista")  # avisa a los microbiólogos (alertas.py)
    trabajo.estado, trabajo.error, trabajo.terminado_en = "ok", None, _ahora()


def procesar_prediccion(session: Session, trabajo: Trabajo, predecir: Callable[[Path], dict], salida: str | Path = "/data/analisis") -> None:
    """Procesa un trabajo `prediccion`. No hace commit: lo hace el worker al volver."""
    sol = session.get(Solicitud, trabajo.solicitud_id)
    if sol.estado not in ("en_analisis", "error"):
        # Anulada, rechazada o ya avanzada: no hay nada que predecir.
        trabajo.estado, trabajo.error, trabajo.terminado_en = "fallido", f"la solicitud está '{sol.estado}'", _ahora()
        return
    if sol.estado == "error":  # reintento manual
        cambiar_estado(session, sol, "en_analisis")
        session.flush()
    try:
        with session.begin_nested():
            _predecir(session, trabajo, sol, predecir, Path(salida))
    except ErrorPrediccion as exc:
        session.refresh(trabajo)
        sol = session.get(Solicitud, trabajo.solicitud_id)
        trabajo.estado, trabajo.error, trabajo.terminado_en = "fallido", str(exc), _ahora()
        cambiar_estado(session, sol, "error", motivo=str(exc))
    except (ErrorHerramienta, OSError) as exc:
        reintentar_o_fallar(session, trabajo, exc)
