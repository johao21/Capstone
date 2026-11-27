"""Inicio y cierre de sesión, perfil y cambio de contraseña (RF-01, RF-02, RF-05, RNF-05)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import acceso, auditoria, seguridad
from ..config import get_settings
from ..db import obtener_sesion
from ..models import Centro, Usuario

router = APIRouter(prefix="/api/v1/auth", tags=["Acceso"])


def _vigentes(sesiones: list | None, ahora: datetime) -> list:
    """Las sesiones revocadas cuyo último token todavía no vence; las demás ya no hacen falta y se descartan."""
    return [s for s in (sesiones or []) if datetime.fromisoformat(s["expira_en"]) > ahora]


class LoginIn(BaseModel):
    correo: str = Field(max_length=254)
    password: str = Field(max_length=128)


class UsuarioOut(BaseModel):
    """El usuario conectado, con lo que puede hacer (la web usa `permisos` para mostrar u ocultar opciones)."""

    id: uuid.UUID
    correo: str
    nombre: str
    rol: str
    centro_id: uuid.UUID
    centro_codigo: str
    centro_nombre: str
    permisos: list[str]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_en: datetime
    usuario: UsuarioOut


class CambioPasswordIn(BaseModel):
    password_actual: str = Field(max_length=128)
    password_nueva: str = Field(max_length=128)


def _con_zona(fecha: datetime | None) -> datetime | None:
    """SQLite devuelve fechas sin zona horaria; se interpretan como UTC."""
    return fecha.replace(tzinfo=timezone.utc) if fecha is not None and fecha.tzinfo is None else fecha


def perfil(session: Session, usuario: Usuario) -> dict:
    centro = session.get(Centro, usuario.centro_id)
    return {
        "id": usuario.id,
        "correo": usuario.correo,
        "nombre": usuario.nombre,
        "rol": usuario.rol,
        "centro_id": usuario.centro_id,
        "centro_codigo": centro.codigo,
        "centro_nombre": centro.nombre,
        "permisos": acceso.permisos_de(usuario.rol),
    }


def _falla_login(session: Session, request: Request, correo: str, motivo: str, usuario: Usuario | None, estado: int, mensaje: str, headers=None):
    """Deja el intento fallido en la auditoría (con commit propio, porque la petición termina en error) y responde."""
    auditoria.registrar(session, "inicio_sesion", usuario=usuario, correo=correo, resultado="fallido",
                        origen=acceso.origen_de(request), detalle={"motivo": motivo})
    session.commit()
    raise HTTPException(estado, mensaje, headers=headers)


@router.post("/login", response_model=TokenOut, summary="Iniciar sesión con correo y contraseña")
def login(datos: LoginIn, request: Request, session: Session = Depends(obtener_sesion)):
    """Devuelve un token JWT. Tras 5 intentos fallidos la cuenta se bloquea 15 minutos (RNF-05)."""
    ajustes = get_settings()
    correo = datos.correo.strip().lower()
    ahora = datetime.now(timezone.utc)
    usuario = session.scalar(select(Usuario).where(func.lower(Usuario.correo) == correo))
    generico = "Correo o contraseña incorrectos"

    if usuario is None:
        seguridad.verificar_contra_senuelo(datos.password)
        _falla_login(session, request, correo, "correo desconocido", None, 401, generico)

    bloqueo = _con_zona(usuario.bloqueado_hasta)
    if bloqueo is not None and bloqueo > ahora:
        espera = int((bloqueo - ahora).total_seconds()) + 1
        _falla_login(session, request, correo, "cuenta bloqueada", usuario, 423,
                     f"Cuenta bloqueada por intentos fallidos. Intenta de nuevo en {espera // 60 + 1} minutos",
                     headers={"Retry-After": str(espera)})

    if not seguridad.verificar_password(usuario.password_hash, datos.password):
        usuario.intentos_fallidos += 1
        if usuario.intentos_fallidos >= ajustes.login_max_intentos:
            usuario.bloqueado_hasta = ahora + timedelta(minutes=ajustes.login_bloqueo_minutos)
            usuario.intentos_fallidos = 0
        _falla_login(session, request, correo, "contraseña incorrecta", usuario, 401, generico)

    if not usuario.activo:
        # Solo se avisa después de acertar la contraseña, para no revelar qué cuentas existen.
        _falla_login(session, request, correo, "cuenta desactivada", usuario, 403, "La cuenta está desactivada. Contacta al administrador")

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    # Aprovecha el inicio de sesión para limpiar, de la lista del usuario, las sesiones revocadas que ya vencieron.
    usuario.sesiones_revocadas = _vigentes(usuario.sesiones_revocadas, ahora)
    token, vence, _ = seguridad.crear_token(usuario, ajustes, ahora=ahora)
    auditoria.registrar(session, "inicio_sesion", usuario=usuario, origen=acceso.origen_de(request))
    session.commit()
    return {"access_token": token, "expira_en": vence, "usuario": perfil(session, usuario)}


@router.post("/logout", status_code=204, summary="Cerrar la sesión")
def logout(request: Request, usuario: Usuario = Depends(acceso.usuario_actual), session: Session = Depends(obtener_sesion)):
    """Revoca la sesión: ningún token de ella vuelve a servir, aunque no haya vencido (RF-02)."""
    ajustes = get_settings()
    # Un token de esta sesión vive, como mucho, lo que dura uno nuevo a partir de ahora.
    vence = datetime.now(timezone.utc) + timedelta(minutes=ajustes.jwt_access_token_expire_minutes)
    # Se bloquea la fila del usuario: dos cierres de sesión a la vez (p. ej. web y móvil) no se pisan la lista.
    session.refresh(usuario, with_for_update=True)
    revocadas = _vigentes(usuario.sesiones_revocadas, datetime.now(timezone.utc))
    if all(s["sid"] != request.state.sid for s in revocadas):
        revocadas.append({"sid": request.state.sid, "expira_en": vence.isoformat()})
    usuario.sesiones_revocadas = revocadas
    auditoria.registrar(session, "cierre_sesion", usuario=usuario, origen=acceso.origen_de(request))
    session.commit()


@router.get("/yo", response_model=UsuarioOut, summary="Datos y permisos del usuario conectado")
def yo(usuario: Usuario = Depends(acceso.usuario_actual), session: Session = Depends(obtener_sesion)):
    return perfil(session, usuario)


@router.post("/cambiar-password", status_code=204, summary="Cambiar la contraseña propia")
def cambiar_password(datos: CambioPasswordIn, request: Request, usuario: Usuario = Depends(acceso.usuario_actual),
                     session: Session = Depends(obtener_sesion)):
    if not seguridad.verificar_password(usuario.password_hash, datos.password_actual):
        auditoria.registrar(session, "cambio_password", usuario=usuario, resultado="fallido", origen=acceso.origen_de(request),
                            detalle={"motivo": "contraseña actual incorrecta"})
        session.commit()
        raise HTTPException(400, "La contraseña actual no es correcta")
    problema = seguridad.password_aceptable(datos.password_nueva, usuario.correo)
    if problema:
        raise HTTPException(422, problema)
    usuario.password_hash = seguridad.hash_password(datos.password_nueva)
    auditoria.registrar(session, "cambio_password", usuario=usuario, origen=acceso.origen_de(request))
    session.commit()
