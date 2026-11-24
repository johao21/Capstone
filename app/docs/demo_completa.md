# Demostración del sistema completo

Recorrido de una solicitud por los cinco roles. Parte de los servicios levantados (`docker compose up --build -d`),
el banco de INPHARED y las referencias de especie ya cargados (ver `demo_avance.md`, pasos 2 y 3) y el modelo entrenado.

## 0. Preparación (una sola vez)

```bash
docker compose exec api python -m app.sembrar_usuarios
```

Crea las cuentas `demo.tecnico@sirfa.local`, `demo.microbiologo@…`, `demo.clinico@…`, `demo.epidemiologo@…` y `demo.admin@…`.
Las contraseñas quedan en `data/credenciales_demo.txt` (no se versiona).

Datos y modelo (descargar antes los 7 archivos del conjunto PhageHostLearn, Zenodo 11061100, a `data/raw/phagehostlearn/`):

```bash
docker compose run --rm worker-prediction python -m ml.entrenar --registrar
```

Para que el tablero muestre grupos con pocas solicitudes (en una demo), bajar `TABLERO_MINIMO_GRUPO` a 1 en `.env` y reiniciar la API.

## 1. Curaduría del banco — microbiólogo

Ingresar como microbiólogo → **Banco de fagos** → buscar «Klebsiella phage» → **Aprobar todos los pendientes de la búsqueda**.
Solo los fagos aprobados entran al ranking (RF-33). En **Modelo** se ven la versión vigente y sus métricas de validación.

## 2. Registro — técnico

Ingresar como técnico → **Nueva solicitud**: subir `data/genomas/HS11286.fna.gz`, código `DEMO-1`, tipo de muestra «Sangre»,
mecanismo «KPC» y el clínico solicitante. La solicitud pasa por *Registrada → En análisis → Predicción lista* en cerca de un minuto
(unos 20 s de análisis genómico y unos 35 s de predicción).

## 3. Validación y emisión — microbiólogo

**Bandeja de validación** (la alerta «predicción lista» también aparece en **Alertas**) → abrir la solicitud → **Tomar para validar**.
Revisar el ranking, abrir «¿Por qué este puntaje?» (SHAP), descartar algún candidato con justificación y **Aprobar y emitir la recomendación**.
Si el locus K del aislado casi no aparece en los datos de entrenamiento, el ranking lleva la marca de baja confianza (RF-38).

## 4. Consulta — clínico y técnico

El clínico y el técnico reciben la alerta «recomendación emitida». El clínico (solo las solicitudes de su centro) abre la recomendación:
ve los candidatos validados y la advertencia, y puede imprimirla o guardarla como PDF.

## 5. Ensayo y cierre — microbiólogo

En la recomendación emitida, registrar el resultado del ensayo de laboratorio de cada candidato y **Guardar y cerrar la solicitud**.
Una corrección se emite como versión nueva y conserva la anterior (RF-46).

## 6. Tablero — epidemiólogo

**Tablero**: cobertura del banco, brechas terapéuticas por locus K y tendencias por mes, locus K, mecanismo y centro, con filtros y exportación a CSV.
Los grupos con menos casos que el mínimo (5) se reúnen en «Otros».

## 7. Administración y auditoría — administrador

**Usuarios**: crear, cambiar rol o centro, desactivar y restablecer contraseñas (los usuarios no se borran).
**Auditoría**: filtrar por usuario, fecha, acción y entidad; **Verificar la cadena de hashes**; exportar a CSV.
En una solicitud, el administrador puede reasignarla a otro microbiólogo y reconstruirla (`GET /api/v1/solicitudes/{id}/reconstruccion`:
quién la pidió, con qué datos, qué versión del modelo y quién validó).

## Qué comprobar de la seguridad

- Sin sesión, cualquier endpoint responde 401; con el rol equivocado, 403; una solicitud ajena responde 404 (no revela que existe).
- Cinco contraseñas incorrectas seguidas bloquean la cuenta 15 minutos.
- En PostgreSQL, `UPDATE`, `DELETE` y `TRUNCATE` sobre `auditoria` fallan por un disparador.
