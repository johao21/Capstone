"""Punto de entrada de la API (FastAPI) y de la web que sirve."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

from . import salud
from .config import get_settings
from .routers import alertas, auditoria, auth, fagos, modelo, recomendaciones, solicitudes, tablero, usuarios

CLAVE_JWT_POR_DEFECTO = "cambiar-por-un-valor-generado"


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    """Al arrancar: fuera de desarrollo, la API se niega a funcionar con una clave JWT de ejemplo o demasiado corta."""
    ajustes = get_settings()
    if ajustes.jwt_secret_key == CLAVE_JWT_POR_DEFECTO or len(ajustes.jwt_secret_key) < 32:
        if ajustes.api_env != "development":
            raise RuntimeError("JWT_SECRET_KEY debe ser un valor secreto de al menos 32 caracteres fuera del entorno de desarrollo")
        logging.getLogger("sirfa").warning("JWT_SECRET_KEY es la clave de ejemplo o es corta: solo es aceptable en desarrollo")
    yield


app = FastAPI(
    title="SIRFA API",
    description=(
        "Sistema de Recomendación de Fagos frente a Antibiorresistencia. Registro y análisis genómico de aislados de "
        "Klebsiella pneumoniae, predicción de compatibilidad con fagos, validación y emisión de recomendaciones, banco de fagos, "
        "tablero, alertas y auditoría. Autenticación con JWT y permisos por rol. Toda recomendación es una hipótesis a ensayar."
    ),
    version="1.0.0",
    lifespan=ciclo_de_vida,
)


@app.get("/api/v1/salud", tags=["Sistema"])
def obtener_salud(respuesta: Response) -> dict:
    """Estado de PostgreSQL y MongoDB; responde 503 si alguno falla."""
    estado = salud.estado_general()
    if estado["estado"] != "ok":
        # El 503 es lo que lee el healthcheck de Docker Compose para marcar el contenedor como no sano.
        respuesta.status_code = 503
    return estado


for ruta in (auth, usuarios, solicitudes, recomendaciones, fagos, modelo, tablero, alertas, auditoria):
    app.include_router(ruta.router)

# La web (HTML, CSS y JavaScript sin paso de compilación) se sirve desde la misma API.
# Va al final: los endpoints de /api tienen prioridad sobre los archivos estáticos.
# parents[2] sube de backend/app/main.py a la raíz del proyecto, donde está la carpeta frontend/.
WEB = Path(__file__).resolve().parents[2] / "frontend"
if (WEB / "index.html").exists():
    # html=True: "/" entrega index.html sin tener que escribirlo en la URL.
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
