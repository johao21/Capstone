"""Una sola base de datos: el detalle del análisis pasa a una columna JSONB de PostgreSQL.

`analisis_genomico.detalle` guarda el resultado completo del pipeline y reemplaza a `documento_id`, el identificador de
un documento guardado fuera de PostgreSQL. Se quita también `fago.documento_id`, que nunca se usó. Los análisis hechos antes de
esta migración conservan su resumen (especie, locus K, genes, versiones) pero su `detalle` queda vacío: ese documento
no se copia.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Agrega `detalle` y quita las columnas `documento_id`."""
    op.add_column(
        "analisis_genomico",
        sa.Column("detalle", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.drop_column("analisis_genomico", "documento_id")
    op.drop_column("fago", "documento_id")


def downgrade() -> None:
    """Deja el esquema como estaba: vuelven las columnas `documento_id` (vacías) y se quita `detalle`."""
    op.add_column("fago", sa.Column("documento_id", sa.String(length=40), nullable=True))
    op.add_column("analisis_genomico", sa.Column("documento_id", sa.String(length=40), nullable=True))
    op.drop_column("analisis_genomico", "detalle")
