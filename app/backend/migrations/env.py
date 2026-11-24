"""Entorno de Alembic: toma la URL de las variables de entorno de la aplicación."""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# Permite importar el paquete `app` (está en backend/) cuando Alembic se ejecuta desde la raíz del proyecto.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

# Los metadatos de los modelos son lo que Alembic compara contra la base de datos.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Modo sin conexión: en vez de ejecutar, emite el SQL (`alembic upgrade head --sql`)."""
    context.configure(url=get_settings().postgres_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Modo normal: se conecta a PostgreSQL y aplica las migraciones pendientes."""
    # NullPool: la migración usa una conexión y la cierra; no hace falta un pool.
    engine = create_engine(get_settings().postgres_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
