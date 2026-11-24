"""Versión vigente del modelo, su fecha de entrenamiento y sus métricas (RF-39)."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import acceso
from ..db import obtener_sesion
from ..models import InteraccionConocida, ModeloPrediccion, Usuario

router = APIRouter(prefix="/api/v1/modelo", tags=["Modelo"])


class ModeloVigente(BaseModel):
    disponible: bool
    id: uuid.UUID | None = None
    version: str | None = None
    algoritmo: str | None = None
    entrenado_en: datetime | None = None
    n_entrenamiento: int | None = None
    metricas: dict = {}
    parametros: dict = {}
    interacciones_en_banco: int = 0
    mensaje: str | None = None


@router.get("", response_model=ModeloVigente, summary="Modelo vigente y sus métricas")
def modelo_vigente(_: Usuario = Depends(acceso.requiere("MIC", "ADM")), session: Session = Depends(obtener_sesion)):
    interacciones = session.scalar(select(func.count()).select_from(InteraccionConocida)) or 0
    modelo = session.scalars(select(ModeloPrediccion).where(ModeloPrediccion.activo.is_(True)).order_by(ModeloPrediccion.entrenado_en.desc())).first()
    if modelo is None:
        return {"disponible": False, "interacciones_en_banco": interacciones,
                "mensaje": "Todavía no hay un modelo entrenado y registrado: sin él no se generan predicciones."}
    return {"disponible": True, "id": modelo.id, "version": modelo.version, "algoritmo": modelo.algoritmo, "entrenado_en": modelo.entrenado_en,
            "n_entrenamiento": modelo.n_entrenamiento, "metricas": modelo.metricas or {}, "parametros": modelo.parametros or {},
            "interacciones_en_banco": interacciones}
