"""Genera el DDL de PostgreSQL a partir de los modelos.

Se usó para producir la instantánea de `migrations/versions/0001_esquema_inicial.sql`.
Los cambios posteriores al esquema van en migraciones nuevas, no regenerando esa instantánea:
con nombres de tabla como argumentos genera solo esas tablas (así se hizo la 0002).

    python backend/scripts/generar_ddl.py > backend/migrations/versions/0001_esquema_inicial.sql
    python backend/scripts/generar_ddl.py auditoria alerta ... > backend/migrations/versions/0002_....sql
"""
import sys
from pathlib import Path

# Permite importar el paquete `app` (está en backend/) al ejecutar el script desde la raíz del proyecto.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from app.models import Base  # noqa: E402

dialecto = postgresql.dialect()
partes: list[str] = []
solo = set(sys.argv[1:])  # sin argumentos: todas las tablas
# sorted_tables respeta las dependencias: cada tabla aparece después de las que referencia.
for tabla in Base.metadata.sorted_tables:
    if solo and tabla.name not in solo:
        continue
    partes.append(str(CreateTable(tabla).compile(dialect=dialecto)).strip())
    # Los índices se ordenan por nombre para que el SQL generado sea siempre el mismo.
    for indice in sorted(tabla.indexes, key=lambda i: i.name):
        partes.append(str(CreateIndex(indice).compile(dialect=dialecto)).strip())

sys.stdout.write(";\n\n".join(partes) + ";\n")
