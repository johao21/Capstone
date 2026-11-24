"""Lectura del conjunto PhageHostLearn (Boeckaerts et al., 2024, Nature Communications; Zenodo 11061100, CC-BY-4.0).

Archivos (en `data/raw/phagehostlearn/`):
- `phage_host_interactions.csv`: matriz cepas × fagos con 1 (el fago infecta), 0 (no infecta) o vacío (no ensayado).
- `RBPbase.csv` y `esm2_embeddings_rbp.csv`: proteínas de unión al receptor (RBP) de cada fago y su embedding ESM-2 (1280 números).
- `Locibase.json` y `esm2_embeddings_loci.csv`: proteínas del locus K de cada cepa y un embedding ESM-2 por cepa.
- `all_loci_score_matrix.txt`: similitud entre los loci de las cepas (1 = idéntico), en el orden de `esm2_embeddings_loci.csv`.
- `phages_genomes.zip`: genomas de los fagos.
"""
from __future__ import annotations

import csv
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CARPETA_POR_DEFECTO = Path("data/raw/phagehostlearn")


@dataclass
class ConjuntoPHL:
    """Todo lo que el entrenamiento necesita, ya alineado."""

    cepas: list[str]  # cepas con locus K, en el orden de `emb_locus` y `sim_locus`
    emb_locus: np.ndarray  # (n_cepas, 1280)
    sim_locus: np.ndarray  # (n_cepas, n_cepas)
    proteinas_locus: dict[str, list[str]]  # secuencias de aminoácidos del locus de cada cepa
    fagos: list[str]  # fagos con al menos una RBP
    rbp_ids: list[str]
    rbp_fago: list[str]  # fago al que pertenece cada RBP
    rbp_emb: np.ndarray  # (n_rbp, 1280)
    etiquetas: np.ndarray  # (n_cepas, n_fagos): 1.0, 0.0 o NaN (no ensayado), solo cepas con locus y fagos con RBP
    # Toda la matriz original, incluidas las cepas sin locus y los fagos sin RBP (se usa para cargar las interacciones al banco).
    matriz_cepas: list[str] = field(default_factory=list)
    matriz_fagos: list[str] = field(default_factory=list)
    matriz: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))


def _leer_embeddings(ruta: Path, columnas_id: int) -> tuple[list[list[str]], np.ndarray]:
    ids, filas = [], []
    with open(ruta, encoding="utf-8", newline="") as f:
        lector = csv.reader(f)
        next(lector)  # encabezado
        for fila in lector:
            ids.append(fila[:columnas_id])
            filas.append(np.asarray(fila[columnas_id:], dtype=np.float32))
    return ids, np.vstack(filas)


def cargar(carpeta: Path | str = CARPETA_POR_DEFECTO) -> ConjuntoPHL:
    carpeta = Path(carpeta)
    # --- cepas y loci
    ids_loci, emb_locus = _leer_embeddings(carpeta / "esm2_embeddings_loci.csv", 1)
    cepas = [i[0] for i in ids_loci]
    proteinas_locus = json.loads((carpeta / "Locibase.json").read_text(encoding="utf-8"))
    sim = np.loadtxt(carpeta / "all_loci_score_matrix.txt", delimiter="\t", dtype=np.float32)
    if sim.shape != (len(cepas), len(cepas)) or set(proteinas_locus) != set(cepas):
        raise ValueError("Los archivos de loci no coinciden entre sí")

    # --- RBP
    ids_rbp, rbp_emb = _leer_embeddings(carpeta / "esm2_embeddings_rbp.csv", 2)
    rbp_fago = [i[0] for i in ids_rbp]
    rbp_ids = [i[1] for i in ids_rbp]
    fagos = sorted(set(rbp_fago))

    # --- matriz de interacciones (las celdas vacías son "no ensayado")
    with open(carpeta / "phage_host_interactions.csv", encoding="utf-8", newline="") as f:
        filas = list(csv.reader(f))
    matriz_fagos = filas[0][1:]
    matriz_cepas = [r[0] for r in filas[1:]]
    matriz = np.array([[float(v) if v != "" else np.nan for v in r[1:]] for r in filas[1:]], dtype=np.float32)

    # Sub-matriz usable para entrenar: cepas con locus y fagos con RBP.
    fila_de = {c: i for i, c in enumerate(matriz_cepas)}
    col_de = {p: j for j, p in enumerate(matriz_fagos)}
    faltan = [c for c in cepas if c not in fila_de] + [p for p in fagos if p not in col_de]
    if faltan:
        raise ValueError(f"Hay cepas o fagos que no están en la matriz de interacciones: {faltan[:5]}")
    etiquetas = matriz[np.ix_([fila_de[c] for c in cepas], [col_de[p] for p in fagos])]

    return ConjuntoPHL(cepas=cepas, emb_locus=emb_locus, sim_locus=sim, proteinas_locus=proteinas_locus, fagos=fagos,
                       rbp_ids=rbp_ids, rbp_fago=rbp_fago, rbp_emb=rbp_emb, etiquetas=etiquetas,
                       matriz_cepas=matriz_cepas, matriz_fagos=matriz_fagos, matriz=matriz)


def longitudes_de_genomas(carpeta: Path | str = CARPETA_POR_DEFECTO) -> dict[str, int]:
    """Largo (pb) del genoma de cada fago, leído de `phages_genomes.zip`: {nombre del fago: pares de bases}."""
    salida: dict[str, int] = {}
    with zipfile.ZipFile(Path(carpeta) / "phages_genomes.zip") as z:
        for nombre in z.namelist():
            if nombre.endswith(".fasta") and "__MACOSX" not in nombre:
                texto = z.read(nombre).decode("utf-8", errors="replace")
                salida[Path(nombre).stem] = sum(len(l.strip()) for l in texto.splitlines() if not l.startswith(">"))
    return salida
