"""Ejecución de herramientas externas (Prodigal, Kaptive, Mash) con errores uniformes."""
from __future__ import annotations

import subprocess


class ErrorHerramienta(RuntimeError):
    """Una herramienta externa falló o no está disponible.

    Es el error "esperado" del pipeline: `trabajos.procesar_pipeline` lo captura para reintentar el trabajo.
    """


def ejecutar(comando: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    """Corre un programa externo y devuelve su resultado; cualquier falla se convierte en `ErrorHerramienta`.

    El timeout por defecto es de una hora; `text=True` entrega la salida como texto.
    """
    try:
        # check=False: el código de salida se revisa a mano más abajo para armar un mensaje claro.
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise ErrorHerramienta(f"no se encontró el programa '{comando[0]}'") from exc
    except subprocess.TimeoutExpired as exc:
        raise ErrorHerramienta(f"'{comando[0]}' superó el tiempo máximo de {timeout} s") from exc
    if resultado.returncode != 0:
        # Se incluyen solo las últimas 3 líneas del error: suelen traer la causa sin inundar el mensaje.
        detalle = (resultado.stderr or resultado.stdout or "").strip().splitlines()
        raise ErrorHerramienta(f"'{comando[0]}' terminó con código {resultado.returncode}: {' '.join(detalle[-3:])}")
    return resultado


def version(comando: list[str]) -> str:
    """Primera línea que imprime el programa; 'desconocida' si no se puede obtener."""
    try:
        r = subprocess.run(comando, capture_output=True, text=True, timeout=60, check=False)
        # Algunas herramientas imprimen la versión por stdout y otras por stderr.
        salida = (r.stdout or r.stderr or "").strip().splitlines()
        return salida[0] if salida else "desconocida"
    except (OSError, subprocess.TimeoutExpired):
        return "desconocida"
