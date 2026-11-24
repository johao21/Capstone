"""Sesiones revocadas, auditoría de solo adición, alertas, predicciones y recomendaciones emitidas.

Aplica la instantánea de DDL `0002_acceso_auditoria_prediccion.sql` (generada con
`backend/scripts/generar_ddl.py` para estas tablas) y agrega el disparador que vuelve la tabla `auditoria`
de solo adición (RF-50, RNF-08).
"""
from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Orden de borrado inverso al de creación: primero las que tienen claves foráneas hacia otras.
TABLAS = (
    "recomendacion_candidato",
    "recomendacion_emitida",
    "prediccion_fago",
    "prediccion",
    "modelo_prediccion",
    "alerta",
    "auditoria",
    "sesion_revocada",
)

# Una función que siempre falla y dos disparadores que la llaman: ni UPDATE ni DELETE (por fila) ni TRUNCATE.
# Ni siquiera el dueño de la tabla puede alterar el registro sin antes quitar el disparador, y eso queda a la vista.
SQL_SOLO_ADICION = (
    """
    CREATE FUNCTION auditoria_solo_adicion() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'La tabla auditoria es de solo adicion: no se permite modificar ni borrar eventos';
    END;
    $$ LANGUAGE plpgsql
    """,
    "CREATE TRIGGER auditoria_no_modificar BEFORE UPDATE OR DELETE ON auditoria "
    "FOR EACH ROW EXECUTE FUNCTION auditoria_solo_adicion()",
    "CREATE TRIGGER auditoria_no_truncar BEFORE TRUNCATE ON auditoria "
    "FOR EACH STATEMENT EXECUTE FUNCTION auditoria_solo_adicion()",
)


def upgrade() -> None:
    """Crea las tablas del .sql y, en PostgreSQL, el disparador de solo adición."""
    sql = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    conexion = op.get_bind()
    for sentencia in sql.split(";\n\n"):
        sentencia = sentencia.strip().rstrip(";")
        if sentencia:
            conexion.exec_driver_sql(sentencia)
    for sentencia in SQL_SOLO_ADICION:
        conexion.exec_driver_sql(sentencia.strip())


def downgrade() -> None:
    """Quita los disparadores y borra las tablas de esta migración."""
    op.execute("DROP TRIGGER IF EXISTS auditoria_no_truncar ON auditoria")
    op.execute("DROP TRIGGER IF EXISTS auditoria_no_modificar ON auditoria")
    op.execute("DROP FUNCTION IF EXISTS auditoria_solo_adicion()")
    for tabla in TABLAS:
        op.execute(f"DROP TABLE IF EXISTS {tabla}")
