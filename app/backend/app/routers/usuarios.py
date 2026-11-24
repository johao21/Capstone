"""Administración de usuarios y centros (RF-03, RF-05). Solo el administrador; los usuarios nunca se borran, se desactivan."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import acceso, auditoria, seguridad
from ..db import obtener_sesion
from ..models import ROLES, Centro, Usuario

router = APIRouter(prefix="/api/v1", tags=["Usuarios"])


class UsuarioAdminOut(BaseModel):
    id: uuid.UUID
    correo: str
    nombre: str
    rol: str
    centro_id: uuid.UUID
    activo: bool
    bloqueado_hasta: datetime | None = None
    creado_en: datetime


class ListaUsuarios(BaseModel):
    total: int
    items: list[UsuarioAdminOut]


class UsuarioNuevo(BaseModel):
    correo: str = Field(min_length=5, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    nombre: str = Field(min_length=1, max_length=200)
    rol: str
    centro_id: uuid.UUID
    password: str = Field(max_length=128)


class UsuarioCambios(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    rol: str | None = None
    centro_id: uuid.UUID | None = None
    activo: bool | None = None


class RestablecerIn(BaseModel):
    password_nueva: str | None = Field(default=None, max_length=128)


class CentroOut(BaseModel):
    id: uuid.UUID
    codigo: str
    nombre: str


class CentroNuevo(BaseModel):
    codigo: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=1, max_length=200)


class ClinicoOut(BaseModel):
    id: uuid.UUID
    nombre: str


@router.get("/centros", response_model=list[CentroOut], summary="Listar centros")
def listar_centros(_: Usuario = Depends(acceso.requiere("ADM", "EPI")), session: Session = Depends(obtener_sesion)):
    return session.scalars(select(Centro).order_by(Centro.codigo)).all()


@router.post("/centros", response_model=CentroOut, status_code=201, summary="Crear un centro")
def crear_centro(datos: CentroNuevo, request: Request, admin: Usuario = Depends(acceso.requiere("ADM")), session: Session = Depends(obtener_sesion)):
    centro = Centro(codigo=datos.codigo.strip().upper(), nombre=datos.nombre.strip())
    session.add(centro)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Ya existe un centro con ese código") from None
    auditoria.registrar(session, "centro_creado", usuario=admin, entidad="centro", entidad_id=centro.id, origen=acceso.origen_de(request),
                        detalle={"codigo": centro.codigo})
    session.commit()
    return centro


@router.get("/usuarios/clinicos", response_model=list[ClinicoOut], summary="Clínicos del centro del técnico")
def listar_clinicos(tec: Usuario = Depends(acceso.requiere("TEC")), session: Session = Depends(obtener_sesion)):
    """Los clínicos activos entre los que el técnico elige al crear una solicitud (RF-11)."""
    return session.scalars(
        select(Usuario).where(Usuario.rol == "CLI", Usuario.activo.is_(True), Usuario.centro_id == tec.centro_id).order_by(Usuario.nombre)
    ).all()


@router.get("/usuarios", response_model=ListaUsuarios, summary="Listar usuarios")
def listar_usuarios(
    q: str | None = Query(None, max_length=100),
    rol: str | None = None,
    activo: bool | None = None,
    limite: int = Query(100, ge=1, le=500),
    desplazamiento: int = Query(0, ge=0),
    _: Usuario = Depends(acceso.requiere("ADM")),
    session: Session = Depends(obtener_sesion),
):
    filtro = []
    if q and q.strip():
        patron = f"%{q.strip().lower()}%"
        filtro.append(or_(func.lower(Usuario.correo).like(patron), func.lower(Usuario.nombre).like(patron)))
    if rol:
        filtro.append(Usuario.rol == rol)
    if activo is not None:
        filtro.append(Usuario.activo.is_(activo))
    total = session.scalar(select(func.count()).select_from(Usuario).where(*filtro)) or 0
    items = session.scalars(select(Usuario).where(*filtro).order_by(Usuario.nombre).limit(limite).offset(desplazamiento)).all()
    return {"total": total, "items": items}


@router.post("/usuarios", response_model=UsuarioAdminOut, status_code=201, summary="Crear un usuario")
def crear_usuario(datos: UsuarioNuevo, request: Request, admin: Usuario = Depends(acceso.requiere("ADM")), session: Session = Depends(obtener_sesion)):
    if datos.rol not in ROLES:
        raise HTTPException(422, f"rol debe ser uno de: {', '.join(ROLES)}")
    if session.get(Centro, datos.centro_id) is None:
        raise HTTPException(422, "El centro no existe")
    problema = seguridad.password_aceptable(datos.password, datos.correo)
    if problema:
        raise HTTPException(422, problema)
    correo = datos.correo.strip().lower()
    if session.scalar(select(func.count()).select_from(Usuario).where(func.lower(Usuario.correo) == correo)):
        raise HTTPException(409, "Ya existe un usuario con ese correo")
    usuario = Usuario(correo=correo, nombre=datos.nombre.strip(), rol=datos.rol, centro_id=datos.centro_id,
                      password_hash=seguridad.hash_password(datos.password))
    session.add(usuario)
    session.flush()
    auditoria.registrar(session, "usuario_creado", usuario=admin, entidad="usuario", entidad_id=usuario.id, origen=acceso.origen_de(request),
                        detalle={"correo": correo, "rol": usuario.rol, "centro_id": usuario.centro_id})
    session.commit()
    return usuario


@router.patch("/usuarios/{usuario_id}", response_model=UsuarioAdminOut, summary="Editar, desactivar o reactivar un usuario")
def editar_usuario(usuario_id: uuid.UUID, datos: UsuarioCambios, request: Request, admin: Usuario = Depends(acceso.requiere("ADM")),
                   session: Session = Depends(obtener_sesion)):
    usuario = session.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "No existe el usuario")
    if usuario.id == admin.id and (datos.activo is False or (datos.rol and datos.rol != usuario.rol)):
        # Evita que el único administrador se deje fuera del sistema por error.
        raise HTTPException(409, "No puedes desactivarte ni cambiar tu propio rol")
    if datos.rol is not None and datos.rol not in ROLES:
        raise HTTPException(422, f"rol debe ser uno de: {', '.join(ROLES)}")
    if datos.centro_id is not None and session.get(Centro, datos.centro_id) is None:
        raise HTTPException(422, "El centro no existe")
    cambios = {}
    for campo in ("nombre", "rol", "centro_id", "activo"):
        nuevo = getattr(datos, campo)
        if nuevo is not None and getattr(usuario, campo) != nuevo:
            cambios[campo] = {"de": getattr(usuario, campo), "a": nuevo}
            setattr(usuario, campo, nuevo)
    if cambios:
        if datos.activo is True:  # al reactivar se limpia el bloqueo por intentos fallidos
            usuario.intentos_fallidos, usuario.bloqueado_hasta = 0, None
        auditoria.registrar(session, "usuario_modificado", usuario=admin, entidad="usuario", entidad_id=usuario.id,
                            origen=acceso.origen_de(request), detalle=cambios)
    session.commit()
    return usuario


@router.post("/usuarios/{usuario_id}/restablecer-password", summary="Restablecer la contraseña de un usuario")
def restablecer_password(usuario_id: uuid.UUID, datos: RestablecerIn, request: Request, admin: Usuario = Depends(acceso.requiere("ADM")),
                         session: Session = Depends(obtener_sesion)):
    """Si no se indica una contraseña nueva se genera una al azar y se devuelve esta única vez."""
    usuario = session.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "No existe el usuario")
    generada = datos.password_nueva is None
    clave = datos.password_nueva or secrets.token_urlsafe(12)
    problema = seguridad.password_aceptable(clave, usuario.correo)
    if problema:
        raise HTTPException(422, problema)
    usuario.password_hash = seguridad.hash_password(clave)
    usuario.intentos_fallidos, usuario.bloqueado_hasta = 0, None
    auditoria.registrar(session, "password_restablecida", usuario=admin, entidad="usuario", entidad_id=usuario.id,
                        origen=acceso.origen_de(request), detalle={"generada": generada})
    session.commit()
    return {"password_temporal": clave} if generada else {"password_temporal": None}
