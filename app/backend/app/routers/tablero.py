"""Tablero de cobertura, brechas terapéuticas y tendencias (RF-55 a RF-60).

Muestra solo datos agregados: cada grupo con menos casos que `tablero_minimo_grupo` (5 por defecto, RF-59) se
suprime y se reúne en una fila "otros", para que el tablero no permita reconocer una solicitud en particular.
La supresión protege la lectura directa; no pretende resistir a quien reste totales entre consultas con filtros distintos.
"""
from __future__ import annotations

import csv
import io
import uuid
from collections import Counter, defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import acceso, recomendacion
from ..config import get_settings
from ..db import obtener_sesion
from ..models import Aislado, Centro, Fago, InteraccionConocida, Prediccion, PrediccionFago, Solicitud, Usuario

router = APIRouter(prefix="/api/v1/tablero", tags=["Tablero"])

ETIQUETA_OTROS = "Otros (grupos pequeños)"


def _agrupar(contador: Counter, minimo: int) -> list[dict]:
    """Grupos ordenados de mayor a menor; los de menos de `minimo` casos se suman en una fila de "otros"."""
    visibles = [{"grupo": g, "n": n, "suprimido": False} for g, n in contador.most_common() if n >= minimo]
    otros = sum(n for n in contador.values() if n < minimo)
    if otros:
        visibles.append({"grupo": ETIQUETA_OTROS, "n": otros, "suprimido": True})
    return visibles


def _filas(session: Session, desde: date | None, hasta: date | None, centro_id: uuid.UUID | None, especie: str | None, locus_k: str | None) -> list[dict]:
    """Una fila por solicitud no anulada, con su locus K, especie y mecanismo, según los filtros (RF-58)."""
    filtro = [Solicitud.estado != "anulada"]
    if desde:
        filtro.append(func.date(Solicitud.creada_en) >= desde.isoformat())
    if hasta:
        filtro.append(func.date(Solicitud.creada_en) <= hasta.isoformat())
    if centro_id:
        filtro.append(Solicitud.centro_id == centro_id)
    consulta = (
        select(Solicitud, Aislado, Centro.codigo)
        .join(Aislado, Aislado.id == Solicitud.aislado_id)
        .join(Centro, Centro.id == Solicitud.centro_id)
        .where(*filtro)
    )
    filas = session.execute(consulta).all()
    salida = []
    for sol, aislado, centro in filas:
        fila = {
            "solicitud_id": sol.id,
            "mes": sol.creada_en.strftime("%Y-%m"),
            "centro": centro,
            "mecanismo": aislado.mecanismo_resistencia or "desconocido",
            "especie": sol.especie_detectada or aislado.especie_declarada,
            "locus_k": sol.locus_k_tipo if recomendacion.locus_tipificado(sol.locus_k_tipo) else None,
        }
        if especie and fila["especie"].lower() != especie.lower():
            continue
        if locus_k and fila["locus_k"] != locus_k:
            continue
        salida.append(fila)
    return salida


def _contar(filas: list[dict], campo: str) -> Counter:
    return Counter(f[campo] for f in filas if f[campo])


@router.get("/cobertura", summary="Cobertura del banco: fagos aprobados por taxonomía, ciclo de vida y hospedador (RF-55)")
def cobertura(_: Usuario = Depends(acceso.requiere("MIC", "EPI", "ADM")), session: Session = Depends(obtener_sesion)):
    aprobados = session.scalars(select(Fago).where(Fago.estado_curaduria == "aprobado")).all()
    por = lambda campo: [{"grupo": g, "n": n} for g, n in Counter((getattr(f, campo) or "sin dato") for f in aprobados).most_common()]  # noqa: E731
    return {
        "fagos_aprobados": len(aprobados),
        "fagos_total": session.scalar(select(func.count()).select_from(Fago)) or 0,
        "por_familia": por("familia"),
        "por_genero": por("genero"),
        "por_ciclo_vida": por("ciclo_vida"),
        "por_hospedador": por("hospedador_declarado"),
    }


@router.get("/brechas", summary="Brechas terapéuticas: locus K sin fagos con compatibilidad conocida ni candidatos (RF-56)")
def brechas(
    desde: date | None = None, hasta: date | None = None, centro_id: uuid.UUID | None = None, especie: str | None = None, locus_k: str | None = None,
    _: Usuario = Depends(acceso.requiere("EPI", "ADM")), session: Session = Depends(obtener_sesion),
):
    ajustes = get_settings()
    minimo = ajustes.tablero_minimo_grupo
    # Un fago es candidato si su probabilidad estimada (calibrada) llega a este umbral; por defecto 0,5. Se configura con UMBRAL_CANDIDATO.
    umbral = ajustes.umbral_candidato
    filas = _filas(session, desde, hasta, centro_id, especie, locus_k)
    casos = _contar(filas, "locus_k")
    # Fagos con al menos una interacción positiva conocida sobre cada locus K.
    positivos: dict[str, set] = defaultdict(set)
    for fago_id, locus in session.execute(
        select(InteraccionConocida.fago_id, InteraccionConocida.locus_k_tipo)
        .join(Fago, Fago.id == InteraccionConocida.fago_id)
        .where(InteraccionConocida.resultado == "infecta", Fago.estado_curaduria == "aprobado")
    ).all():
        if locus:
            positivos[locus].add(fago_id)
    # Fagos que el modelo pone sobre el umbral en alguna solicitud de ese locus K.
    candidatos: dict[str, set] = defaultdict(set)
    ids_por_locus: dict[str, list] = defaultdict(list)
    for f in filas:
        if f["locus_k"]:
            ids_por_locus[f["locus_k"]].append(f["solicitud_id"])
    for locus, ids in ids_por_locus.items():
        for fago_id in session.scalars(
            select(PrediccionFago.fago_id).join(Prediccion, Prediccion.id == PrediccionFago.prediccion_id)
            .where(Prediccion.solicitud_id.in_(ids), PrediccionFago.puntaje >= umbral)
        ):
            candidatos[locus].add(fago_id)
    visibles, suprimidos = [], 0
    for locus, n in casos.most_common():
        if n < minimo:
            suprimidos += n
            continue
        pos, cand = len(positivos.get(locus, ())), len(candidatos.get(locus, ()))
        visibles.append({"locus_k": locus, "solicitudes": n, "fagos_con_evidencia": pos, "fagos_candidatos": cand, "brecha": pos == 0 and cand == 0})
    return {"minimo_grupo": minimo, "umbral_candidato": umbral, "grupos": visibles, "casos_suprimidos": suprimidos}


@router.get("/tendencias", summary="Solicitudes por mes y distribución de locus K y mecanismos, por centro (RF-57)")
def tendencias(
    desde: date | None = None, hasta: date | None = None, centro_id: uuid.UUID | None = None, especie: str | None = None, locus_k: str | None = None,
    _: Usuario = Depends(acceso.requiere("EPI", "ADM")), session: Session = Depends(obtener_sesion),
):
    minimo = get_settings().tablero_minimo_grupo
    filas = _filas(session, desde, hasta, centro_id, especie, locus_k)
    por_mes = Counter(f["mes"] for f in filas)
    return {
        "minimo_grupo": minimo,
        "total_solicitudes": len(filas) if len(filas) >= minimo else None,
        # Los meses van en orden cronológico; los que no llegan al mínimo se reúnen en "otros" (no se pueden ordenar).
        "por_mes": [g for g in sorted(_agrupar(por_mes, minimo), key=lambda g: (g["suprimido"], g["grupo"]))],
        "por_locus_k": _agrupar(_contar(filas, "locus_k"), minimo),
        "por_mecanismo": _agrupar(_contar(filas, "mecanismo"), minimo),
        "por_centro": _agrupar(_contar(filas, "centro"), minimo),
    }


@router.get("/exportar.csv", summary="Exportar los datos agregados a CSV (RF-60)")
def exportar(
    desde: date | None = None, hasta: date | None = None, centro_id: uuid.UUID | None = None, especie: str | None = None, locus_k: str | None = None,
    usuario: Usuario = Depends(acceso.requiere("EPI")), session: Session = Depends(obtener_sesion),
):
    t = tendencias(desde, hasta, centro_id, especie, locus_k, usuario, session)
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow(["indicador", "grupo", "casos", "suprimido"])
    for indicador in ("por_mes", "por_locus_k", "por_mecanismo", "por_centro"):
        for g in t[indicador]:
            w.writerow([indicador, g["grupo"], g["n"], "si" if g["suprimido"] else "no"])
    return Response(salida.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="tablero_sirfa.csv"'})
