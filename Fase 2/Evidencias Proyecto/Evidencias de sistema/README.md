# Evidencias de sistema (aplicación y base de datos) — SIRFA

El sistema completo está en la carpeta `app/` de este repositorio. Esta carpeta reúne las evidencias de la base de datos y apunta a lo demás.

| Evidencia | Dónde está |
|---|---|
| Aplicación: API, pipeline genómico, modelo, web y app móvil | `app/backend`, `app/pipeline`, `app/ml`, `app/frontend`, `app/mobile` |
| Cómo levantarla | `docker compose up -d` desde `app/` (4 servicios: postgres, api, worker-pipeline y worker-prediction); procedimiento completo en `app/docs/MANUAL_TECNICO.md` |
| Base de datos (PostgreSQL): 12 tablas | Esquema versionado con Alembic en `app/backend/migrations/versions/` (migraciones 0001 a 0004). Las migraciones 0001 y 0002 dejaron 20 tablas; la 0004 las simplificó a 12 (SC-07, iniciada el 12-11-2026). Los scripts SQL de esta carpeta, `postgresql_0001_esquema_inicial.sql` y `postgresql_0002_acceso_auditoria_prediccion.sql`, son copias de las dos primeras (el esquema inicial, antes de SC-06 y SC-07); las migraciones 0003 y 0004 solo existen como código Python. La fuente de verdad es `app/` |
| Detalle de cada análisis genómico | Columna JSONB `solicitud.detalle_analisis` de PostgreSQL (`app/backend/app/models.py`), que escribe el worker del pipeline (`app/pipeline/trabajos.py`). La migración `0003_detalle_en_postgresql.py` la creó como `analisis_genomico.detalle` y la `0004_doce_tablas.py` la pasó a `solicitud`. Hasta la migración 0002 estaba en MongoDB, que se quitó para dejar una sola base de datos (SC-06, iniciada el 12-11-2026) |
| Pruebas automáticas | `app/backend/tests` (217) y `app/mobile/tests` (38); integración continua en `.github/workflows/ci.yml` |
| Recorrido de demostración | `app/docs/demo_completa.md` y `app/docs/demo_avance.md` |

Alcance y límites, tal como están en el README de `app/`: la app móvil es un primer corte probado a mano en teléfonos Android con Expo Go (25-11-2026), sin notificaciones push; no hay capturas de pantalla en esta carpeta, porque el sistema se muestra en vivo en la demostración.
