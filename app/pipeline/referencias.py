"""Construcción de las referencias de especie para Mash (RF-20).

    python -m pipeline.referencias construir [--destino data/referencias]

Descarga los genomas de `referencias.tsv` desde NCBI y arma el sketch `referencias.msh` con su mapa
`especies.tsv` (archivo -> especie). Nada de esto se versiona: se reconstruye con el comando.
"""
from __future__ import annotations

import argparse
import gzip
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .herramientas import ejecutar

LISTA = Path(__file__).with_name("referencias.tsv")
FTP_NCBI = "https://ftp.ncbi.nlm.nih.gov/genomes/all"
TAMANO_SKETCH = 10_000  # más hashes que el valor por defecto (1.000) para separar especies cercanas
K = 21  # largo de los k-mers (fragmentos de 21 bases) con los que Mash resume cada genoma


@dataclass(frozen=True)
class Referencia:
    """Un genoma de referencia: una fila de `referencias.tsv`."""

    accesion: str  # p. ej. GCF_000240185.1
    ensamblado: str  # nombre del ensamblado en NCBI, p. ej. ASM24018v2
    especie: str
    cepa: str

    @property
    def archivo(self) -> str:
        """Nombre del archivo local donde se guarda el genoma descargado."""
        return f"{self.accesion}.fna.gz"

    @property
    def url(self) -> str:
        """Dirección de descarga en el FTP de NCBI."""
        return url_genoma(self.accesion, self.ensamblado)


def url_genoma(accesion: str, ensamblado: str) -> str:
    """GCF_000240185.1 + ASM24018v2 -> .../GCF/000/240/185/GCF_000240185.1_ASM24018v2/..._genomic.fna.gz"""
    prefijo, resto = accesion.split("_")
    numero = resto.split(".")[0]
    # NCBI reparte los genomas en carpetas de a tres dígitos: los 9 dígitos del número se cortan en 3 tramos.
    tramos = "/".join(numero[i : i + 3] for i in range(0, 9, 3))
    base = f"{accesion}_{ensamblado}"
    return f"{FTP_NCBI}/{prefijo}/{tramos}/{base}/{base}_genomic.fna.gz"


def leer_lista(ruta: Path = LISTA) -> list[Referencia]:
    """Lee `referencias.tsv` (cuatro columnas separadas por tabulador); ignora líneas vacías y las que empiezan con `#`."""
    referencias: list[Referencia] = []
    for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
        if not linea.strip() or linea.startswith("#"):
            continue
        partes = linea.split("\t")
        if len(partes) < 4:
            raise ValueError(f"{ruta.name}, línea {numero}: se esperan 4 columnas separadas por tabulador")
        referencias.append(Referencia(*(p.strip() for p in partes[:4])))
    return referencias


def descargar(url: str, destino: Path) -> None:
    """Descarga un genoma y solo lo deja en `destino` si lo descargado es un gzip válido."""
    # Se baja a un archivo ".parte" y se renombra al final: una descarga fallida no queda con el nombre definitivo.
    temporal = destino.with_suffix(destino.suffix + ".parte")
    print(f"  descargando {destino.name}", file=sys.stderr)
    urllib.request.urlretrieve(url, temporal)  # noqa: S310 - URL de NCBI construida desde la lista
    with gzip.open(temporal, "rb") as f:  # falla si el archivo no es gzip válido
        f.read(1024)
    temporal.replace(destino)


def construir(destino: Path, lista: list[Referencia] | None = None, tamano: int = TAMANO_SKETCH) -> Path:
    """Descarga las referencias que falten, escribe el mapa archivo -> especie y arma el sketch de Mash."""
    lista = lista if lista is not None else leer_lista()
    genomas = destino / "genomas"
    genomas.mkdir(parents=True, exist_ok=True)

    # Los genomas ya descargados no se vuelven a bajar.
    for ref in lista:
        archivo = genomas / ref.archivo
        if not archivo.exists():
            descargar(ref.url, archivo)

    mapa = destino / "especies.tsv"
    mapa.write_text("".join(f"{r.archivo}\t{r.especie}\n" for r in lista), encoding="utf-8")

    # `mash sketch` resume cada genoma en una huella pequeña; luego `mash dist` compara contra ellas.
    prefijo = destino / "referencias"
    ejecutar(
        ["mash", "sketch", "-k", str(K), "-s", str(tamano), "-o", str(prefijo), *(str(genomas / r.archivo) for r in lista)],
        timeout=1800,
    )
    return prefijo.with_suffix(".msh")


def main(argv: list[str] | None = None) -> int:
    """Línea de comandos: `construir` es la única orden disponible."""
    ap = argparse.ArgumentParser(description="Referencias de especie para Mash")
    sub = ap.add_subparsers(dest="orden", required=True)
    c = sub.add_parser("construir", help="descarga los genomas y arma el sketch")
    c.add_argument("--destino", type=Path, default=Path("data/referencias"))
    args = ap.parse_args(argv)

    lista = leer_lista()
    print(f"{len(lista)} genomas de referencia en {args.destino}", file=sys.stderr)
    sketch = construir(args.destino, lista)
    print(f"Sketch listo: {sketch} ({sketch.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
