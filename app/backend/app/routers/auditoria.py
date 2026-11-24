"""Consulta, verificación y exportación de la auditoría (RF-51, RF-52, RF-54). Solo el administrador."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import acceso, auditoria
from ..db import obtener_sesion
from ..models import Auditoria, Usuario

router = APIRouter(prefix="/api/v1/auditoria", tags=["Auditoría"])

TOPE_EXPORTACION = 50_000


class EventoOut(BaseModel):
    seq: int
    ts: datetime
    usuario_id: uuid.UUID | None = None
    correo: str | None = None
    rol: str | None = None
    accion: str
    entidad: str | None = None
    entidad_id: str | None = None
    resultado: str
    origen: str | None = None
    modelo_version: str | None = None
    detalle: dict


class ListaEventos(BaseModel):
    total: int
    items: list[EventoOut]


class Verificacion(BaseModel):
    ok: bool
    eventos: int
    primer_error_seq: int | None = None
    motivo: str | None = None


def _filtros(usuario: str | None, desde: datetime | None, hasta: datetime | None, accion: str | None, entidad: str | None):
    return dict(correo=usuario.strip().lower() if usuario else None, desde=desde, hasta=hasta, accion=accion, entidad=entidad)


@router.get("", response_model=ListaEventos, summary="Consultar la auditoría con filtros")
def consultar(
    usuario: str | None = Query(None, max_length=254, description="Correo del usuario"),
    desde: datetime | None = None,
    hasta: datetime | None = None,
    accion: str | None = Query(None, max_length=60),
    entidad: str | None = Query(None, max_length=60),
    limite: int = Query(50, ge=1, le=500),
    desplazamiento: int = Query(0, ge=0),
    _: Usuario = Depends(acceso.requiere("ADM")),
    session: Session = Depends(obtener_sesion),
):
    q = auditoria.consulta(**_filtros(usuario, desde, hasta, accion, entidad))
    total = session.scalar(select(func.count()).select_from(q.order_by(None).subquery())) or 0
    items = session.scalars(q.limit(limite).offset(desplazamiento)).all()
    return {"total": total, "items": items}


@router.get("/acciones", response_model=list[str], summary="Acciones que aparecen en la auditoría")
def acciones(_: Usuario = Depends(acceso.requiere("ADM")), session: Session = Depends(obtener_sesion)):
    """Para llenar el filtro por acción de la pantalla."""
    return session.scalars(select(Auditoria.accion).distinct().order_by(Auditoria.accion)).all()


@router.get("/verificar", response_model=Verificacion, summary="Verificar la integridad de la cadena de hashes")
def verificar(_: Usuario = Depends(acceso.requiere("ADM")), session: Session = Depends(obtener_sesion)):
    return auditoria.verificar(session)


@router.get("/exportar.csv", summary="Exportar el resultado de una consulta a CSV")
def exportar(
    request: Request,
    usuario: str | None = Query(None, max_length=254),
    desde: datetime | None = None,
    hasta: datetime | None = None,
    accion: str | None = Query(None, max_length=60),
    entidad: str | None = Query(None, max_length=60),
    admin: Usuario = Depends(acceso.requiere("ADM")),
    session: Session = Depends(obtener_sesion),
):
    q = auditoria.consulta(**_filtros(usuario, desde, hasta, accion, entidad))
    eventos = session.scalars(q.limit(TOPE_EXPORTACION)).all()
    auditoria.registrar(session, "auditoria_exportada", usuario=admin, entidad="auditoria", origen=acceso.origen_de(request),
                        detalle={"filtros": {k: v for k, v in _filtros(usuario, desde, hasta, accion, entidad).items() if v}, "filas": len(eventos)})
    session.commit()
    return Response(auditoria.a_csv(eventos), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="auditoria_sirfa.csv"'})
