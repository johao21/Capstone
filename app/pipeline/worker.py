"""Worker: consume trabajos de la cola `trabajo` (decisión D-02). Cada servicio atiende un tipo de trabajo.

    python -m pipeline.worker --tipos pipeline            # análisis genómico (worker-pipeline); queda escuchando
    python -m pipeline.worker --tipos prediccion          # ranking de fagos con el modelo (worker-prediction)
    python -m pipeline.worker --tipos pipeline --una-vez  # procesa lo pendiente y termina
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import subprocess
import time
from pathlib import Path

from app.config import get_settings
from app.db import get_sessionmaker

from .especie import identificar_especie, rutas_referencias
from .genes import predecir_genes
from .herramientas import ErrorHerramienta, version
from .locus_k import tipificar_locus_k
from .prediccion import ErrorPrediccion, procesar_prediccion
from .trabajos import Pasos, procesar_pipeline, reclamar, registrar_fallo_inesperado

log = logging.getLogger("sirfa.worker")
TIPOS = ("pipeline", "prediccion")


def construir_pasos() -> Pasos:
    """Conecta el pipeline con las herramientas reales (en las pruebas se usan versiones falsas)."""
    sketch, mapa = rutas_referencias()
    if not (sketch.exists() and mapa.exists()):
        log.warning(
            "sin referencias de especie en %s: la especie NO se verificará. Ejecute: python -m pipeline.referencias construir",
            sketch.parent,
        )

    def versiones() -> dict:
        """Versión de cada herramienta, para dejar constancia de con qué se hizo el análisis."""
        return {
            "prodigal": version(["prodigal", "-v"]),
            "kaptive": version(["kaptive", "--version"]),
            "mash": version(["mash", "--version"]),
        }

    return Pasos(
        # El sketch y el mapa se fijan aquí; el pipeline solo pasa la ruta del genoma y la especie declarada.
        especie=lambda ruta, declarada: identificar_especie(ruta, declarada, sketch, mapa),
        locus_k=tipificar_locus_k,
        genes=predecir_genes,
        versiones=versiones,
    )


def construir_prediccion():
    """Devuelve la función `predecir(ruta de proteinas.faa)` que usa `procesar_prediccion`, respaldada por el modelo de `ml/models`.

    El modelo se carga la primera vez y se vuelve a cargar solo si `modelo.json` cambió (se entrenó una versión nueva)."""
    ajustes = get_settings()
    cache: dict = {}

    def predecir(proteinas: Path) -> dict:
        from ml.modelo import Predictor  # importa xgboost y shap: solo lo necesita este worker

        archivo = Path(ajustes.modelo_dir) / "modelo.json"
        if not archivo.exists():
            raise ErrorPrediccion(f"Faltan los artefactos del modelo en {ajustes.modelo_dir}: entrénalo con `python -m ml.entrenar --registrar`")
        marca = archivo.stat().st_mtime
        if cache.get("marca") != marca:
            cache["predictor"], cache["marca"] = Predictor(ajustes.modelo_dir), marca
            log.info("modelo cargado desde %s", ajustes.modelo_dir)
        try:
            return cache["predictor"].predecir(proteinas)
        except subprocess.CalledProcessError as exc:  # blastp falló: se trata como una herramienta caída y se reintenta
            raise ErrorHerramienta(f"blastp falló: {(exc.stderr or '')[:300]}") from exc

    return predecir


def marcar_fallido(trabajo_id, motivo: str) -> None:
    """Registra el fallo en una sesión nueva (la anterior ya se revirtió y no se puede reutilizar)."""
    with get_sessionmaker()() as session:
        registrar_fallo_inesperado(session, trabajo_id, motivo)
        session.commit()


def main(argv: list[str] | None = None) -> int:
    """Bucle del worker: reclama un trabajo, lo procesa y repite; si no hay nada, espera y vuelve a mirar."""
    ap = argparse.ArgumentParser(description="Worker de SIRFA")
    ap.add_argument("--tipos", default="pipeline", help="tipos de trabajo que atiende, separados por coma: pipeline, prediccion")
    ap.add_argument("--una-vez", action="store_true", help="termina cuando no quedan trabajos pendientes")
    ap.add_argument("--espera", type=float, default=5.0, help="segundos entre consultas con la cola vacía")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    tipos = [t.strip() for t in args.tipos.split(",") if t.strip()]
    if not tipos or set(tipos) - set(TIPOS):
        ap.error(f"--tipos debe ser una lista de: {', '.join(TIPOS)}")
    # Identifica a este worker en la columna `bloqueado_por`: nombre del contenedor + número de proceso.
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    pasos = construir_pasos() if "pipeline" in tipos else None
    predecir = construir_prediccion() if "prediccion" in tipos else None
    salida = Path(os.environ.get("ANALISIS_DIR", "/data/analisis"))
    log.info("worker %s escuchando trabajos de tipo %s", worker_id, ", ".join(tipos))

    while True:
        # Una sesión (y una transacción) por trabajo: el commit libera el bloqueo de la fila reclamada.
        with get_sessionmaker()() as session:
            # Se prueba cada tipo que este worker atiende, en el orden indicado.
            trabajo = next((t for t in (reclamar(session, tipo, worker_id) for tipo in tipos) if t is not None), None)
            if trabajo is None:
                session.rollback()
            else:
                trabajo_id = trabajo.id
                log.info("procesando trabajo %s de tipo %s (intento %s)", trabajo_id, trabajo.tipo, trabajo.intentos)
                try:
                    if trabajo.tipo == "pipeline":
                        procesar_pipeline(session, trabajo, pasos, salida=salida)
                    else:
                        procesar_prediccion(session, trabajo, predecir, salida=salida)
                    session.commit()
                    log.info("trabajo %s -> %s", trabajo_id, trabajo.estado)
                except Exception as exc:  # noqa: BLE001 - un error inesperado no debe tumbar el worker
                    session.rollback()
                    log.exception("error inesperado en el trabajo %s", trabajo_id)
                    marcar_fallido(trabajo_id, f"error inesperado: {exc}")
                # Con trabajo en mano no se duerme: se busca enseguida el siguiente.
                continue
        # Cola vacía: terminar si se pidió `--una-vez`; si no, esperar antes de volver a consultar.
        if args.una_vez:
            return 0
        time.sleep(args.espera)


if __name__ == "__main__":
    raise SystemExit(main())
