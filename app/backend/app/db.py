"""Acceso a PostgreSQL y MongoDB.

PostgreSQL guarda los datos estructurados (solicitudes, cola de trabajos, banco de fagos);
MongoDB guarda el resultado crudo y voluminoso del análisis genómico. Todo se crea una sola vez
por proceso (`lru_cache`) y se comparte entre peticiones.
"""
from collections.abc import Iterator
from functools import lru_cache

from pymongo import MongoClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Motor de SQLAlchemy con su pool de conexiones."""
    # pool_pre_ping: prueba la conexión antes de usarla, para sobrevivir a un reinicio de Postgres.
    return create_engine(get_settings().postgres_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    """Fábrica de sesiones; la usan la API (vía `obtener_sesion`) y el worker directamente."""
    # expire_on_commit=False: los objetos siguen legibles después de `commit()` (la API los serializa al responder).
    return sessionmaker(get_engine(), expire_on_commit=False)


def obtener_sesion() -> Iterator[Session]:
    """Una sesión por petición de la API; se cierra al terminar."""
    with get_sessionmaker()() as session:
        yield session


@lru_cache
def get_mongo() -> MongoClient:
    """Cliente de MongoDB. El timeout corto hace que /salud falle rápido si Mongo no responde."""
    return MongoClient(get_settings().mongo_url, serverSelectionTimeoutMS=2000)
