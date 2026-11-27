"""Comprobación de estado de los servicios (RNF-19)."""
from sqlalchemy import text

from .db import get_engine


def comprobar_postgres() -> str:
    """`"ok"` si PostgreSQL responde a una consulta trivial; si no, `"falla: <tipo de error>"`."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 - se informa el motivo, no se propaga
        # Solo el nombre del error: el mensaje completo puede traer datos de la conexión y esta ruta es pública.
        return f"falla: {type(exc).__name__}"


def estado_general() -> dict:
    """Resultado de la comprobación: `ok` si la base responde; si no, `degradado`."""
    postgres = comprobar_postgres()
    return {"estado": "ok" if postgres == "ok" else "degradado", "postgres": postgres}
