"""Bandeja de alertas con marca de leída (RF-65). Las alertas se generan en `alertas.py` al cambiar el estado de una solicitud."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import acceso
from ..db import obtener_sesion
from ..models import Alerta, Usuario

router = APIRouter(prefix="/api/v1/alertas", tags=["Alertas"])


class AlertaOut(BaseModel):
    id: uuid.UUID
    solicitud_id: uuid.UUID
    tipo: str
    mensaje: str
    leida: bool
    creada_en: datetime


class ListaAlertas(BaseModel):
    no_leidas: int
    items: list[AlertaOut]


@router.get("", response_model=ListaAlertas, summary="Alertas del usuario, las más recientes primero")
def listar(
    solo_no_leidas: bool = False,
    limite: int = Query(50, ge=1, le=200),
    usuario: Usuario = Depends(acceso.requiere("TEC", "MIC", "CLI")),
    session: Session = Depends(obtener_sesion),
):
    propias = [Alerta.usuario_id == usuario.id]
    no_leidas = session.scalar(select(func.count()).select_from(Alerta).where(*propias, Alerta.leida.is_(False))) or 0
    filtro = propias + ([Alerta.leida.is_(False)] if solo_no_leidas else [])
    items = session.scalars(select(Alerta).where(*filtro).order_by(Alerta.creada_en.desc()).limit(limite)).all()
    return {"no_leidas": no_leidas, "items": items}


@router.post("/leer-todas", status_code=204, summary="Marcar todas las alertas como leídas")
def leer_todas(usuario: Usuario = Depends(acceso.requiere("TEC", "MIC", "CLI")), session: Session = Depends(obtener_sesion)):
    session.execute(update(Alerta).where(Alerta.usuario_id == usuario.id, Alerta.leida.is_(False)).values(leida=True))
    session.commit()


@router.post("/{alerta_id}/leida", status_code=204, summary="Marcar una alerta como leída")
def marcar_leida(alerta_id: uuid.UUID, usuario: Usuario = Depends(acceso.requiere("TEC", "MIC", "CLI")),
                 session: Session = Depends(obtener_sesion)):
    alerta = session.get(Alerta, alerta_id)
    if alerta is None or alerta.usuario_id != usuario.id:  # la de otra persona responde igual que una inexistente
        raise HTTPException(404, "No existe la alerta")
    alerta.leida = True
    session.commit()
