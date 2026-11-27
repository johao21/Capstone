"""Versión vigente del modelo, su fecha de entrenamiento y sus métricas (RF-39).

El modelo vigente son los artefactos de `ml/models/` (los que carga el worker de predicción); no hay una tabla de modelos.
Cada predicción guarda además una copia de la ficha del modelo que la generó.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ml.modelo import leer_ficha

from .. import acceso
from ..config import get_settings
from ..db import obtener_sesion
from ..models import InteraccionConocida, Usuario

router = APIRouter(prefix="/api/v1/modelo", tags=["Modelo"])


class ModeloVigente(BaseModel):
    disponible: bool
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
    ficha = leer_ficha(get_settings().modelo_dir)
    if ficha is None:
        return {"disponible": False, "interacciones_en_banco": interacciones,
                "mensaje": "Todavía no hay un modelo entrenado: sin él no se generan predicciones."}
    return {"disponible": True, "version": ficha["version"], "algoritmo": ficha["algoritmo"], "entrenado_en": ficha["entrenado_en"],
            "n_entrenamiento": ficha["n_entrenamiento"], "metricas": ficha["metricas"] or {}, "parametros": ficha["parametros"] or {},
            "interacciones_en_banco": interacciones}
