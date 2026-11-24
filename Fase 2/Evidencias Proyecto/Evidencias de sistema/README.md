# Evidencias de sistema (aplicación y base de datos) — SIRFA

El sistema completo está en la carpeta `app/` de este repositorio. Esta carpeta reúne las evidencias de la base de datos y apunta a lo demás.

| Evidencia | Dónde está |
|---|---|
| Aplicación: API, pipeline genómico, modelo, web y app móvil | `app/backend`, `app/pipeline`, `app/ml`, `app/frontend`, `app/mobile` |
| Cómo levantarla | `docker compose up -d` desde `app/` (5 servicios: postgres, mongo, api, worker-pipeline y worker-prediction); procedimiento completo en `app/docs/MANUAL_TECNICO.md` |
| Base relacional (PostgreSQL): 20 tablas | Scripts SQL de esta carpeta, `postgresql_0001_esquema_inicial.sql` y `postgresql_0002_acceso_auditoria_prediccion.sql`. Son copias de `app/backend/migrations/versions/*.sql`, que se generan con las migraciones de Alembic; la fuente de verdad es `app/` |
| Base documental (MongoDB): colección `analisis_genomico` | La escribe el worker del pipeline (`app/pipeline/worker.py`); la tabla `analisis_genomico` de PostgreSQL (`app/backend/app/models.py`) guarda la referencia al documento |
| Pruebas automáticas | `app/backend/tests` (212) y `app/mobile/tests` (29); integración continua en `.github/workflows/ci.yml` |
| Recorrido de demostración | `app/docs/demo_completa.md` y `app/docs/demo_avance.md` |

Alcance y límites, tal como están en el README de `app/`: la app móvil es un primer corte verificado en el navegador y no en un teléfono; no hay capturas de pantalla en esta carpeta, porque el sistema se muestra en vivo en la demostración.
