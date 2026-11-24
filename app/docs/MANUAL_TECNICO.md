# SIRFA — Manual técnico y de despliegue

*Sistema de Recomendación de Fagos frente a Antibiorresistencia*

|  |  |
|---|---|
| **Proyecto** | SIRFA, proyecto de título individual (Capstone PTY4614 / APT122, Duoc UC) |
| **Versión y fecha** | 1.0 · 23 de noviembre de 2026 |
| **Autor** | Johao Ramírez (desarrollador único) |
| **Probado en** | Windows 11 con Docker Desktop (WSL2), Docker 29 y Compose 5, el 15-11-2026; la app móvil, el 18-11-2026 |

## 1. Propósito y alcance

Este manual explica cómo instalar, configurar, ejecutar, probar y mantener SIRFA en un computador con Docker Compose. Sirve para quien debe levantar el sistema desde cero (el docente o la comisión) y para quien lo opera después.

> **SIRFA no diagnostica ni prescribe.** Toda recomendación es una hipótesis priorizada que debe ensayarse en laboratorio antes de cualquier uso clínico. El sistema se probó solo con genomas públicos y cuentas de demostración.

Linux y macOS deberían funcionar, porque todo corre en contenedores, pero no se han probado.

## 2. Requisitos

- **Docker Desktop** (Windows o macOS) o Docker Engine con el plugin Compose (Linux). Se comprueba con `docker compose version`.
- **Git**, para clonar el repositorio, y **conexión a internet** la primera vez (imágenes, paquetes y datos públicos).
- **Recursos:** no se midió un mínimo. Se probó con 20 CPU y 15,5 GiB de memoria; entrenar el modelo tarda unos 15 minutos. Conviene reservar varios GB de disco.
- **Node.js** reciente (se usó la 24) y **Expo Go** en un teléfono Android, solo si se quiere la app móvil.

## 3. Servicios y puertos

| Servicio | Imagen | Función | Puerto |
|---|---|---|---|
| `postgres` | `postgres:16` | Dominio, cola de trabajos y auditoría | interno |
| `mongo` | `mongo:7` | Salidas crudas del análisis genómico | interno |
| `api` | `sirfa-backend:dev` | API REST (FastAPI) y web; aplica las migraciones al arrancar | **8000** |
| `worker-pipeline` | `sirfa-backend:dev` | Calidad del genoma, especie (Mash), locus K (Kaptive) y genes (Prodigal) | interno |
| `worker-prediction` | `sirfa-backend:dev` | Ranking de fagos con BLAST, XGBoost y SHAP | interno |

La API y los dos workers usan la misma imagen (Python 3.12 con Prodigal, BLAST+ y Mash; Kaptive se instala con pip) y cambian solo el comando. Los datos viven en cuatro volúmenes con nombre (`pgdata`, `mongodata`, `genomas`, `analisis`): sobreviven a `docker compose down` y solo `down -v` los borra. Además se montan `./data` (referencias y genomas de prueba) y `./ml/models` (modelo entrenado).

Solo se publica el puerto 8000. Para dejarlo accesible únicamente desde el mismo equipo, en `docker-compose.yml` se cambia `8000:8000` por `127.0.0.1:8000:8000`.

## 4. Variables de entorno

Se copian de `.env.example` a `.env`, que no se versiona. Las que importan:

| Variable | Para qué sirve | Por defecto |
|---|---|---|
| `JWT_SECRET_KEY` | Clave que firma las sesiones. **Hay que cambiarla.** Fuera de `API_ENV=development`, la API se niega a arrancar con la clave de ejemplo o con una de menos de 32 caracteres. | valor de ejemplo |
| `API_ENV` | Entorno de ejecución. | `development` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Duración de la sesión sin actividad; con actividad se renueva sola. | `15` |
| `LOGIN_MAX_INTENTOS`, `LOGIN_BLOQUEO_MINUTOS` | Intentos fallidos antes de bloquear la cuenta y minutos de bloqueo. | `5` y `15` |
| `POSTGRES_*`, `MONGO_*` | Servidor, base, usuario y clave de cada base de datos. **Hay que cambiar las claves.** | hosts `postgres` y `mongo`; clave `cambiar` |
| `TABLERO_MINIMO_GRUPO` | Los grupos con menos casos se reúnen en «Otros» en el tablero. Para una demo con pocas solicitudes, bajarlo a `1`. | `5` |
| `UMBRAL_CANDIDATO` | Probabilidad calibrada desde la que un fago cuenta como candidato en las brechas terapéuticas. | `0.5` |
| `MODELO_DIR`, `GENOMAS_DIR`, `ANALISIS_DIR` | Carpetas del modelo y de los archivos, dentro del contenedor. | `/app/ml/models`, `/data/genomas`, `/data/analisis` |

`NEXT_PUBLIC_API_URL` aparece en el ejemplo por el diseño original con Next.js; la web actual no la usa.

## 5. Instalación paso a paso

1. **Clonar el repositorio** y entrar a la carpeta del código.

```bash
git clone URL_DEL_REPOSITORIO
cd sirfa
```

2. **Crear el `.env`** y cambiar las claves. Una clave segura se genera con el comando de abajo.

```bash
cp .env.example .env            # en PowerShell: Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

3. **Levantar el sistema.** La primera vez construye la imagen y tarda varios minutos.

```bash
docker compose up --build -d
docker compose ps                         # deben verse los 5 servicios
curl http://localhost:8000/api/v1/salud   # responde: estado ok, postgres ok, mongo ok
```

4. **Crear las cuentas de demostración** (una por rol). Las contraseñas quedan en `data/credenciales_demo.txt`, que no se versiona.

```bash
docker compose exec api python -m app.sembrar_usuarios
```

5. **Cargar las referencias de especie y el banco de fagos.** Sin las referencias el pipeline no verifica la especie y usa la declarada.

```bash
docker compose exec api python -m pipeline.referencias construir
docker compose exec api python -m pipeline.seed_phage_bank --descargar --hospedador Klebsiella --limite 200
```

6. **Entrenar y registrar el modelo.** Hay que descargar los 7 archivos del conjunto PhageHostLearn (registro 11061100 de Zenodo) en `data/raw/phagehostlearn`. Tarda unos 15 minutos. Si `ml/models/` ya trae los artefactos, basta registrarlos con `--sin-entrenar`.

```bash
docker compose run --rm worker-prediction python -m ml.entrenar --registrar
# o, con los artefactos ya guardados:
docker compose run --rm worker-prediction python -m ml.entrenar --registrar --sin-entrenar
```

7. **Aprobar los fagos.** Ingresar a `http://localhost:8000/` como microbiólogo y, en «Banco de fagos», usar «Aprobar todos los pendientes de la búsqueda». Sin fagos aprobados la predicción termina en error con ese motivo.

8. **Probar el flujo.** Como técnico, subir `data/genomas/HS11286.fna.gz`; en cerca de un minuto la solicitud queda «Predicción lista». El microbiólogo la toma, revisa el ranking y la emite; el clínico lee la recomendación.

## 6. Operación y mantenimiento

| Tarea | Comando |
|---|---|
| Ver el estado y los registros | `docker compose ps` · `docker compose logs -f api` (o `worker-pipeline`, `worker-prediction`) |
| Detener sin perder datos / reanudar | `docker compose down` · `docker compose up -d` |
| Borrar todos los datos (irreversible) | `docker compose down -v` |
| Reconstruir tras cambiar el código | `docker compose up --build -d` |
| Respaldo de PostgreSQL | `docker compose exec -T postgres pg_dump -U sirfa sirfa > respaldo.sql` (usuario y base según el `.env`). La restauración no se ha probado. |
| Más workers del pipeline | `docker compose up -d --scale worker-pipeline=3`. La cola usa bloqueo de filas (`FOR UPDATE SKIP LOCKED`) y se probó con 8 workers contra PostgreSQL real, pero no con el compose. |

En Windows, `iniciar_sirfa.bat` enciende Docker Desktop, levanta los servicios y abre la web con un doble clic; hay que ajustar la ruta `APP` dentro del archivo.

## 7. Pruebas

```bash
docker compose exec api pytest      # API y pipeline: 212 pruebas
cd mobile && npm test               # app móvil: 29 pruebas de su lógica
```

La prueba de concurrencia necesita una base PostgreSQL desechable y se omite sin ella: se activa con `SIRFA_TEST_POSTGRES_DB=sirfa_test` y se niega a usar la base real. La interfaz de la web y de la app no tienen pruebas automáticas. En GitHub, las mismas pruebas están configuradas para correr en cada push (`.github/workflows/ci.yml`).

## 8. App móvil

Con el sistema corriendo: `cd mobile`, `npm install` y `npm start`, y abrir con Expo Go en un teléfono Android conectado a la misma red wifi. La app prueba primero `http://<IP del computador>:8000`; si no conecta, se corrige tocando «Servidor» en la pantalla de ingreso. En el emulador de Android el computador es `http://10.0.2.2:8000`. La conexión es HTTP dentro de la red local; fuera de ella la API debe ir detrás de HTTPS. Detalle en `mobile/README.md`.

## 9. Seguridad al desplegar

- Cambiar `JWT_SECRET_KEY` y las claves de las dos bases antes de usar el sistema con datos reales; no versionar `.env` ni `data/credenciales_demo.txt`.
- **HTTPS no está configurado** (RNF-02 queda pendiente fuera del entorno local). Antes de exponer SIRFA fuera de una red de confianza, hay que ponerle delante un proxy inverso con TLS.
- PostgreSQL y MongoDB no publican puertos. Los permisos por rol los exige el servidor y la auditoría es de solo adición (disparador en PostgreSQL y hashes encadenados).

## 10. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `failed to connect to the docker API` | Docker Desktop está apagado. | Abrirlo, esperar a que arranque y repetir el comando (o usar `iniciar_sirfa.bat`). |
| `/api/v1/salud` responde 503 | PostgreSQL o MongoDB no están sanos. | `docker compose ps` y `docker compose logs postgres mongo`. |
| La solicitud queda en «Error»: «No hay un modelo entrenado y registrado» | Falta registrar el modelo. | Paso 6 de la instalación y luego «Reintentar» la solicitud. |
| La predicción termina en error por falta de fagos | No hay fagos aprobados en el banco. | Paso 7: aprobar fagos en «Banco de fagos». |
| La especie no se verifica | No se construyeron las referencias. | `docker compose exec api python -m pipeline.referencias construir`. |
| «Cuenta bloqueada» | Cinco intentos fallidos de inicio de sesión. | Esperar 15 minutos; un administrador puede restablecer la contraseña. |
| El teléfono no se conecta | Otra red, cortafuegos o dirección equivocada. | Misma wifi, permitir el acceso en redes privadas y escribir `http://<IP del computador>:8000` en «Servidor». |
| El puerto 8000 está ocupado | Otro programa lo usa. | Cambiar el puerto publicado en `docker-compose.yml`, por ejemplo `8001:8000`. |

## 11. Limitaciones conocidas

- Probado solo en Windows con Docker Desktop; sin HTTPS; la integración continua (GitHub Actions) está definida pero aún no se ha ejecutado en GitHub; la restauración de respaldos y el escalado de workers con el compose no se han probado.
- Rendimiento medido con 21 solicitudes y 305 fagos, no con la escala del diseño (1.000 solicitudes y 25.000 fagos).
- La app móvil es un primer corte, verificado en un navegador y aún sin probar en un teléfono Android; no tiene notificaciones push.
