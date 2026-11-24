"""Tipificación del locus K con Kaptive (RF-21).

Verificado con Kaptive 3.3.2 sobre el genoma HS11286 (base `kpsc_k`): `-o` recibe un ARCHIVO, no una
carpeta, y el TSV trae las columnas "Best match locus" y "Match confidence". La línea de comandos
depende de la versión, así que se puede cambiar con la variable KAPTIVE_CMD (plantilla con {fasta} y
{salida}, donde {salida} es la carpeta de trabajo).
"""
from __future__ import annotations

import csv
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from .herramientas import ErrorHerramienta, ejecutar

PLANTILLA_POR_DEFECTO = "kaptive assembly kpsc_k {fasta} -o {salida}/resultado.tsv"


@dataclass(frozen=True)
class ResultadoLocusK:
    """Locus K (tipo de cápsula) más probable y qué tan confiable es el resultado."""

    tipo: str | None
    confianza: str | None
    detalle: dict = field(default_factory=dict)  # la fila completa de Kaptive, tal como salió


def _buscar(fila: dict[str, str], candidatos: tuple[str, ...]) -> str | None:
    """Valor de la primera columna candidata que exista y tenga dato (sin distinguir mayúsculas en el nombre)."""
    minusculas = {k.lower(): v for k, v in fila.items()}
    for c in candidatos:
        if c in minusculas and minusculas[c] not in ("", "N/A", "NA"):
            return minusculas[c]
    return None


def leer_resultado(directorio: Path) -> ResultadoLocusK:
    """Lee el primer TSV de resultados que haya en el directorio de salida de Kaptive."""
    tablas = sorted(directorio.rglob("*.tsv"))
    if not tablas:
        raise ErrorHerramienta("Kaptive no produjo ninguna tabla de resultados (.tsv)")
    with open(tablas[0], newline="", encoding="utf-8") as f:
        filas = list(csv.DictReader(f, delimiter="\t"))
    if not filas:
        raise ErrorHerramienta("la tabla de resultados de Kaptive está vacía")
    # Se procesa un solo genoma por corrida, así que interesa la primera (y única) fila de datos.
    fila = filas[0]
    return ResultadoLocusK(
        # Varios nombres candidatos por columna: los encabezados cambian entre versiones de Kaptive.
        tipo=_buscar(fila, ("best match locus", "best_match", "locus")),
        confianza=_buscar(fila, ("match confidence", "confidence")),
        detalle=dict(fila),
    )


def tipificar_locus_k(ruta_genoma: str | Path, directorio: str | Path) -> ResultadoLocusK:
    """Corre Kaptive sobre el genoma y devuelve el locus K que reporta."""
    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    plantilla = os.environ.get("KAPTIVE_CMD", PLANTILLA_POR_DEFECTO)
    # shlex.split después de rellenar la plantilla: respeta comillas y evita pasar todo por un shell.
    comando = shlex.split(plantilla.format(fasta=str(ruta_genoma), salida=str(directorio)))
    ejecutar(comando)
    return leer_resultado(directorio)
