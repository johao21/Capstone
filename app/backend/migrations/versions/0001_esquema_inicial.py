"""Esquema inicial: acceso, solicitudes, pipeline y banco de fagos.

Aplica la instantánea de DDL `0001_esquema_inicial.sql`, generada desde los modelos con
`backend/scripts/generar_ddl.py`.
"""
from pathlib import Path

from alembic import op

# Identificadores que Alembic usa para encadenar migraciones. `down_revision = None`: es la primera.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Orden de borrado inverso al de creación: primero las tablas que tienen claves foráneas hacia otras.
TABLAS = (
    "interaccion_conocida",
    "fago_origen",
    "fago",
    "fuente_datos",
    "analisis_genomico",
    "trabajo",
    "solicitud_historial",
    "solicitud",
    "genoma",
    "aislado",
    "usuario",
    "centro",
)


def upgrade() -> None:
    """Ejecuta, una por una, las sentencias del archivo .sql que está junto a esta migración."""
    sql = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    conexion = op.get_bind()
    # generar_ddl.py separa las sentencias con ";" + línea en blanco; el driver ejecuta una por llamada.
    for sentencia in sql.split(";\n\n"):
        sentencia = sentencia.strip().rstrip(";")
        if sentencia:
            conexion.exec_driver_sql(sentencia)


def downgrade() -> None:
    """Deshace la migración borrando todas las tablas."""
    for tabla in TABLAS:
        op.execute(f"DROP TABLE IF EXISTS {tabla}")
