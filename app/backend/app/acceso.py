"""Quién es el usuario de cada petición y qué puede hacer (RF-01, RF-02, RF-04, RF-06, RNF-03, RNF-04).

- `usuario_actual`: lee el token Bearer, comprueba que la sesión siga abierta y devuelve el `Usuario`.
- `requiere(*roles)`: lo anterior más "su rol debe estar en la lista"; si no, responde 403 y lo audita.
- `solicitudes_visibles` / `puede_ver`: alcance de los datos por rol (RF-06): propios para el técnico, asignados y
  pendientes para el microbiólogo, del centro para el clínico, todos para el administrador.

Lo que no figura como permitido queda denegado (SRS 2.3).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from . import auditoria, seguridad
from .config import get_settings
from .db import obtener_sesion
from .models import SesionRevocada, Solicitud, Usuario

_bearer = HTTPBearer(auto_error=False)

# Matriz de permisos de SRS 2.3: función -> roles que pueden. La API la hace cumplir y la web la usa para mostrar u ocultar opciones.
PERMISOS: dict[str, set[str]] = {
    "registrar_solicitud": {"TEC"},
    "ver_solicitudes": {"TEC", "MIC", "CLI", "ADM"},
    "anular_solicitud": {"TEC", "ADM"},
    "reintentar_solicitud": {"TEC", "ADM"},
    "validar_recomendacion": {"MIC"},
    "reasignar_solicitud": {"ADM"},
    "ver_prediccion": {"MIC", "ADM"},
    "curar_banco": {"MIC"},
    "consultar_banco": {"MIC", "ADM"},
    "ver_tablero": {"MIC", "EPI", "ADM"},
    "ver_tablero_completo": {"EPI", "ADM"},
    "ver_modelo": {"MIC", "ADM"},
    "gestionar_usuarios": {"ADM"},
    "ver_auditoria": {"ADM"},
    "recibir_alertas": {"TEC", "MIC", "CLI"},
}


def permisos_de(rol: str) -> list[str]:
    """Nombres de las funciones que el rol puede usar."""
    return sorted(nombre for nombre, roles in PERMISOS.items() if rol in roles)


def origen_de(request: Request) -> str | None:
    """Dirección IP de la conexión (RF-49)."""
    return request.client.host if request.client else None


def _no_autenticado(mensaje: str) -> HTTPException:
    return HTTPException(401, mensaje, headers={"WWW-Authenticate": "Bearer"})


def usuario_actual(
    request: Request,
    response: Response,
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(obtener_sesion),
) -> Usuario:
    """El usuario del token. 401 si falta, venció, no es válido, su sesión se cerró o la cuenta está desactivada."""
    if credenciales is None:
        raise _no_autenticado("Inicia sesión para continuar")
    ajustes = get_settings()
    try:
        datos = seguridad.decodificar_token(credenciales.credentials, ajustes)
    except jwt.ExpiredSignatureError:
        raise _no_autenticado("La sesión expiró: inicia sesión de nuevo") from None
    except jwt.PyJWTError:
        raise _no_autenticado("Token no válido") from None
    if session.get(SesionRevocada, datos["sid"]) is not None:
        raise _no_autenticado("La sesión se cerró: inicia sesión de nuevo")
    try:
        usuario = session.get(Usuario, uuid.UUID(datos["sub"]))
    except ValueError:
        raise _no_autenticado("Token no válido") from None
    if usuario is None or not usuario.activo:
        raise _no_autenticado("La cuenta no está activa")
    request.state.sid = datos["sid"]
    # Sesión deslizante: si a este token le queda menos de la mitad de su vida, la respuesta trae uno nuevo de la misma sesión.
    restante = datos["exp"] - datetime.now(timezone.utc).timestamp()
    if restante < ajustes.jwt_access_token_expire_minutes * 30:
        nuevo, _, _ = seguridad.crear_token(usuario, ajustes, sid=datos["sid"])
        response.headers["X-Token-Renovado"] = nuevo
    return usuario


def requiere(*roles: str):
    """Dependencia de FastAPI: deja pasar solo a los roles indicados; a los demás les responde 403 y deja el intento en la auditoría."""

    def dependencia(request: Request, usuario: Usuario = Depends(usuario_actual), session: Session = Depends(obtener_sesion)) -> Usuario:
        if usuario.rol not in roles:
            auditoria.registrar(
                session, "acceso_denegado", usuario=usuario, entidad="endpoint", entidad_id=f"{request.method} {request.url.path}",
                resultado="denegado", origen=origen_de(request), detalle={"metodo": request.method, "ruta": request.url.path},
            )
            session.commit()  # el intento debe quedar registrado aunque la petición termine en error
            raise HTTPException(403, "Tu rol no permite esta operación")
        return usuario

    return dependencia


def solicitudes_visibles(usuario: Usuario) -> list:
    """Condiciones SQL que limitan las solicitudes que ve el usuario (RF-06). Lista vacía = todas."""
    if usuario.rol == "TEC":
        return [Solicitud.creada_por == usuario.id]
    if usuario.rol == "CLI":
        return [Solicitud.centro_id == usuario.centro_id]
    if usuario.rol == "MIC":
        # Las que tiene asignadas y las que esperan a que alguien las tome.
        return [or_(Solicitud.asignada_a == usuario.id, and_(Solicitud.estado == "prediccion_lista", Solicitud.asignada_a.is_(None)))]
    if usuario.rol == "ADM":
        return []
    return [Solicitud.id.is_(None)]  # EPI y cualquier otro: ninguna (el SQL nunca coincide)


def puede_ver(usuario: Usuario, solicitud: Solicitud) -> bool:
    """Misma regla que `solicitudes_visibles`, para una solicitud ya cargada."""
    if usuario.rol == "ADM":
        return True
    if usuario.rol == "TEC":
        return solicitud.creada_por == usuario.id
    if usuario.rol == "CLI":
        return solicitud.centro_id == usuario.centro_id
    if usuario.rol == "MIC":
        return solicitud.asignada_a == usuario.id or (solicitud.estado == "prediccion_lista" and solicitud.asignada_a is None)
    return False


def solicitud_visible_o_404(session: Session, usuario: Usuario, solicitud_id: uuid.UUID) -> Solicitud:
    """La solicitud si el usuario puede verla. Una ajena responde 404, igual que una inexistente: no revela que existe (RNF-04)."""
    solicitud = session.get(Solicitud, solicitud_id)
    if solicitud is None or not puede_ver(usuario, solicitud):
        raise HTTPException(404, "No existe la solicitud")
    return solicitud
