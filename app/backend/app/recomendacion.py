"""Evidencia conocida y advertencia de toda recomendación (RF-37, RF-45).

`candidatos_por_evidencia` no usa el modelo: propone un fago solo si existe al menos una interacción conocida y
positiva con una cepa del mismo locus K que el aislado. Es la evidencia de apoyo que se muestra junto al ranking del
modelo (ver `routers/recomendaciones.py`). Si el banco no trae esas interacciones, la respuesta lo dice en vez de
ordenar los fagos con criterios inventados.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Fago, InteraccionConocida

# RF-45: va en toda recomendación (web y exportación).
AVISO = (
    "SIRFA no diagnostica ni prescribe. Toda recomendación es una hipótesis priorizada que debe ensayarse en "
    "laboratorio antes de cualquier uso clínico; apoya la decisión de un profesional, no la reemplaza."
)


def locus_tipificado(tipo: str | None) -> bool:
    """El locus K sirve para buscar evidencia solo si Kaptive entregó un tipo concreto."""
    if tipo is None:
        return False
    limpio = tipo.strip().lower()
    # Se descartan el valor vacío y las etiquetas de "sin tipo" (unknown, none...): no identifican un locus concreto.
    return bool(limpio) and not limpio.startswith(("unknown", "desconocido", "none", "no "))


def estadisticas_banco(session: Session) -> dict:
    """Cuatro conteos que dicen cuánto del banco está curado y cuánta evidencia hay cargada."""
    total = session.scalar(select(func.count()).select_from(Fago)) or 0
    curados = session.scalar(select(func.count()).select_from(Fago).where(Fago.estado_curaduria == "aprobado")) or 0
    con_ciclo = session.scalar(select(func.count()).select_from(Fago).where(Fago.ciclo_vida != "desconocido")) or 0
    interacciones = session.scalar(select(func.count()).select_from(InteraccionConocida)) or 0
    return {
        "fagos_total": total,
        "fagos_curados": curados,
        "fagos_con_ciclo_de_vida": con_ciclo,
        "interacciones_conocidas": interacciones,
    }


def candidatos_por_evidencia(session: Session, locus_k_tipo: str | None, limite: int = 20) -> list[dict]:
    """Fagos con interacciones positivas conocidas sobre el mismo locus K, de mayor a menor tasa de éxito."""
    if not locus_tipificado(locus_k_tipo):
        return []
    # Una sola consulta trae todas las interacciones de ese locus (salvo fagos descartados en la curaduría).
    filas = session.execute(
        select(InteraccionConocida.fago_id, InteraccionConocida.resultado, InteraccionConocida.cepa, InteraccionConocida.referencia)
        .join(Fago, Fago.id == InteraccionConocida.fago_id)
        .where(InteraccionConocida.locus_k_tipo == locus_k_tipo, Fago.estado_curaduria != "descartado")
    ).all()

    # Se agrupan en Python por fago: cuántas positivas y negativas, y qué cepas y publicaciones las respaldan.
    por_fago: dict = {}
    for fago_id, resultado, cepa, referencia in filas:
        dato = por_fago.setdefault(fago_id, {"positivas": 0, "negativas": 0, "cepas": set(), "referencias": set()})
        dato["positivas" if resultado == "infecta" else "negativas"] += 1
        if cepa:
            dato["cepas"].add(cepa)
        if referencia:
            dato["referencias"].add(referencia)

    candidatos = []
    for fago_id, d in por_fago.items():
        # Un fago que solo tiene resultados negativos no es candidato.
        if d["positivas"] == 0:
            continue
        fago = session.get(Fago, fago_id)
        probadas = d["positivas"] + d["negativas"]
        candidatos.append(
            {
                "fago_id": str(fago.id),
                "accesion": fago.accesion,
                "nombre": fago.nombre,
                "interacciones_positivas": d["positivas"],
                "interacciones_negativas": d["negativas"],
                "tasa_positiva": round(d["positivas"] / probadas, 3),
                "cepas_probadas": len(d["cepas"]),
                "referencias": sorted(d["referencias"]),
            }
        )
    # Orden estable: mejor tasa, luego más positivas y, al empatar, por accesión para que el resultado no varíe.
    candidatos.sort(key=lambda c: (-c["tasa_positiva"], -c["interacciones_positivas"], c["accesion"]))
    return candidatos[:limite]
