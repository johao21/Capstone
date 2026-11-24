"""Comprobación de estado de los servicios (RNF-19)."""
from sqlalchemy import text

from .db import get_engine, get_mongo


def comprobar_postgres() -> str:
    """`"ok"` si PostgreSQL responde a una consulta trivial; si no, `"falla: <tipo de error>"`."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 - se informa el motivo, no se propaga
        # Solo el nombre del error: el mensaje completo puede traer datos de la conexión y esta ruta es pública.
        return f"falla: {type(exc).__name__}"


def comprobar_mongo() -> str:
    """`"ok"` si MongoDB responde al comando `ping`; si no, `"falla: <tipo de error>"`."""
    try:
        get_mongo().admin.command("ping")
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"falla: {type(exc).__name__}"


def estado_general() -> dict:
    """Resultado combinado: `ok` solo si ambas bases responden; si no, `degradado`."""
    postgres, mongo = comprobar_postgres(), comprobar_mongo()
    sano = postgres == "ok" and mongo == "ok"
    return {"estado": "ok" if sano else "degradado", "postgres": postgres, "mongo": mongo}
