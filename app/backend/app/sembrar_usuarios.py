"""Crea las cuentas de demostración, una por rol, y deja sus contraseñas en un archivo local.

    python -m app.sembrar_usuarios               # crea las que faltan
    python -m app.sembrar_usuarios --restablecer  # además, genera contraseña nueva para todas

Las contraseñas se generan al azar, nunca se imprimen en la consola y se guardan en `data/credenciales_demo.txt`
(carpeta `data/` del proyecto, que no se sube a Git). El SRS (2.6) establece que los usuarios de cada rol son cuentas
de demostración: el proyecto no opera con un hospital real.
"""
from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

from sqlalchemy import select

from . import auditoria, seguridad
from .config import get_settings
from .db import get_sessionmaker
from .models import Usuario
from .registro import CORREO_DEMO, usuario_demo

# Una cuenta por rol, todas en el centro de demostración (el clínico debe compartir centro con el técnico).
CUENTAS = (
    ("TEC", CORREO_DEMO, "Técnico de demostración"),
    ("MIC", "demo.microbiologo@sirfa.local", "Microbiólogo de demostración"),
    ("CLI", "demo.clinico@sirfa.local", "Clínico de demostración"),
    ("EPI", "demo.epidemiologo@sirfa.local", "Epidemiólogo de demostración"),
    ("ADM", "demo.admin@sirfa.local", "Administrador de demostración"),
)


def archivo_credenciales() -> Path:
    return Path(os.environ.get("CREDENCIALES_DEMO", "/app/data/credenciales_demo.txt"))


def leer_credenciales(ruta: Path) -> dict[str, str]:
    """Lee `correo<TAB>contraseña` por línea; ignora comentarios."""
    if not ruta.exists():
        return {}
    pares = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.strip() and not linea.startswith("#") and "\t" in linea:
            correo, clave = linea.split("\t", 1)
            pares[correo.strip()] = clave.strip()
    return pares


def escribir_credenciales(ruta: Path, pares: dict[str, str]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cabecera = "# Cuentas de demostración de SIRFA (correo<TAB>contraseña). No se sube a Git.\n"
    ruta.write_text(cabecera + "".join(f"{c}\t{k}\n" for c, k in pares.items()), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Crea las cuentas de demostración de SIRFA")
    ap.add_argument("--restablecer", action="store_true", help="genera una contraseña nueva para todas las cuentas")
    ap.add_argument("--forzar", action="store_true", help="permite ejecutarlo fuera del entorno de desarrollo")
    args = ap.parse_args(argv)
    if get_settings().api_env != "development" and not args.forzar:
        print("Entorno distinto de 'development': las cuentas de demostración no se crean (usa --forzar si es a propósito).")
        return 1

    ruta = archivo_credenciales()
    credenciales = leer_credenciales(ruta)
    nuevas = []
    with get_sessionmaker()() as session:
        centro_id = usuario_demo(session).centro_id  # crea el centro y el técnico de demostración la primera vez
        for rol, correo, nombre in CUENTAS:
            usuario = session.scalar(select(Usuario).where(Usuario.correo == correo))
            sin_acceso = usuario is not None and not usuario.password_hash.startswith("$argon2")
            if usuario is not None and not (args.restablecer or sin_acceso):
                continue
            clave = secrets.token_urlsafe(12)
            if usuario is None:
                usuario = Usuario(correo=correo, nombre=nombre, rol=rol, centro_id=centro_id, password_hash=seguridad.hash_password(clave))
                session.add(usuario)
                session.flush()
                auditoria.registrar(session, "usuario_creado", usuario_id=None, entidad="usuario", entidad_id=usuario.id,
                                    detalle={"correo": correo, "rol": rol, "origen": "sembrar_usuarios"})
            else:
                usuario.password_hash = seguridad.hash_password(clave)
                usuario.intentos_fallidos, usuario.bloqueado_hasta, usuario.activo = 0, None, True
                auditoria.registrar(session, "password_restablecida", usuario_id=None, entidad="usuario", entidad_id=usuario.id,
                                    detalle={"origen": "sembrar_usuarios"})
            credenciales[correo] = clave
            nuevas.append(correo)
        session.commit()
    if nuevas:
        escribir_credenciales(ruta, credenciales)
    print(f"Cuentas creadas o restablecidas: {len(nuevas)}" + "".join(f"\n  - {c}" for c in nuevas))
    print(f"Contraseñas en: {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
