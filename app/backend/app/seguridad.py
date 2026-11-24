"""Contraseñas y tokens JWT (RF-01, RF-02, RF-05, RNF-01, RNF-03).

- Las contraseñas se guardan solo como hash Argon2id (algoritmo adaptativo, con sal propia por contraseña).
- El token es un JWT firmado (HS256) que lleva el usuario (`sub`), su rol y centro, y un identificador de sesión (`sid`)
  que no cambia cuando el token se renueva: así "Cerrar sesión" invalida todos los tokens de esa sesión.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import Settings

LARGO_MINIMO_PASSWORD = 10

_hasher = PasswordHasher()
# Hash de una contraseña inventada: se verifica contra él cuando el correo no existe, para que responder
# "no existe" no sea más rápido que responder "contraseña incorrecta" (no se filtra qué correos están registrados).
_HASH_SENUELO = _hasher.hash("contraseña-senuelo-que-nadie-usa")


def hash_password(clave: str) -> str:
    """Hash Argon2id de la contraseña."""
    return _hasher.hash(clave)


def verificar_password(hash_guardado: str, clave: str) -> bool:
    """True si la contraseña corresponde al hash. Un hash inválido (p. ej. la cuenta sin acceso) nunca coincide."""
    try:
        return _hasher.verify(hash_guardado, clave)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def verificar_contra_senuelo(clave: str) -> None:
    """Gasta el mismo tiempo que una verificación real (para correos que no existen)."""
    verificar_password(_HASH_SENUELO, clave)


def password_aceptable(clave: str, correo: str = "") -> str | None:
    """Mensaje de error si la contraseña no cumple la política, o None si es aceptable."""
    if len(clave) < LARGO_MINIMO_PASSWORD:
        return f"La contraseña debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres"
    if len(clave) > 128:
        return "La contraseña no puede superar los 128 caracteres"
    if correo and clave.lower() == correo.lower():
        return "La contraseña no puede ser igual al correo"
    return None


def crear_token(usuario, ajustes: Settings, sid: str | None = None, ahora: datetime | None = None) -> tuple[str, datetime, str]:
    """Token firmado para el usuario. Devuelve (token, vence_en, sid); si se pasa `sid`, es una renovación de esa sesión."""
    ahora = ahora or datetime.now(timezone.utc)
    vence = ahora + timedelta(minutes=ajustes.jwt_access_token_expire_minutes)
    sid = sid or uuid.uuid4().hex
    reclamos = {
        "sub": str(usuario.id),
        "rol": usuario.rol,
        "centro": str(usuario.centro_id),
        "sid": sid,
        "iat": int(ahora.timestamp()),
        "exp": int(vence.timestamp()),
    }
    return jwt.encode(reclamos, ajustes.jwt_secret_key, algorithm=ajustes.jwt_algorithm), vence, sid


def decodificar_token(token: str, ajustes: Settings) -> dict:
    """Reclamos del token. Lanza `jwt.ExpiredSignatureError` si venció y `jwt.PyJWTError` si no es válido."""
    # `algorithms` fijo: un token firmado con otro algoritmo (o sin firma) se rechaza.
    return jwt.decode(token, ajustes.jwt_secret_key, algorithms=[ajustes.jwt_algorithm], options={"require": ["exp", "sub", "sid"]})
