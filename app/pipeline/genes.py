"""Predicción de genes y proteínas con Prodigal (RF-22)."""
from __future__ import annotations

import gzip
import shutil
from dataclasses import dataclass
from pathlib import Path

from .herramientas import ejecutar


@dataclass(frozen=True)
class ResultadoGenes:
    """Cantidad de genes predichos y dónde quedó el archivo de proteínas."""

    n_genes: int
    n_proteinas: int
    ruta_proteinas: str  # FASTA de aminoácidos (.faa) que generó Prodigal


def _a_plano(ruta: Path, directorio: Path) -> Path:
    """Prodigal no lee gzip: se descomprime a una copia de trabajo."""
    if ruta.suffix.lower() != ".gz":
        return ruta
    destino = directorio / ruta.stem  # stem quita el ".gz": genoma.fasta.gz -> genoma.fasta
    with gzip.open(ruta, "rb") as origen, open(destino, "wb") as salida:
        shutil.copyfileobj(origen, salida)
    return destino


def contar_proteinas(ruta_faa: Path) -> int:
    """Cuenta los encabezados (`>`) del FASTA de proteínas: uno por proteína."""
    with open(ruta_faa, "rt", encoding="utf-8") as f:
        return sum(1 for linea in f if linea.startswith(">"))


def predecir_genes(ruta_genoma: str | Path, directorio: str | Path) -> ResultadoGenes:
    """Corre Prodigal sobre el genoma y deja proteínas y anotación en `directorio`."""
    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    entrada = _a_plano(Path(ruta_genoma), directorio)
    proteinas = directorio / "proteinas.faa"
    genes = directorio / "genes.gff"
    # -i entrada, -a proteínas traducidas, -o/-f anotación en formato GFF, -p single: un solo genoma
    # (Prodigal se entrena con él), -q: sin mensajes de progreso.
    ejecutar(
        ["prodigal", "-i", str(entrada), "-a", str(proteinas), "-f", "gff", "-o", str(genes), "-p", "single", "-q"]
    )
    n = contar_proteinas(proteinas)
    # Cada gen predicho genera exactamente una proteína, por eso ambos conteos coinciden.
    return ResultadoGenes(n_genes=n, n_proteinas=n, ruta_proteinas=str(proteinas))
