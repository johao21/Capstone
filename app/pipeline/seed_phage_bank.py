"""Carga del banco de fagos desde la tabla pública de INPHARED (RF-27, RF-28, RF-29).

Uso dentro del contenedor:

    python -m pipeline.seed_phage_bank --descargar --hospedador Klebsiella --limite 200

Formato verificado de la tabla `<fecha>_millardlab_website_table.txt.gz` (abril 2026), con tabuladores:
Accession (envuelta en un enlace HTML), Description, Genome Length (KB), molGC (%), Genus, Sub-family,
Family, Host. La longitud viene en KB redondeados, por lo que `longitud_pb` es aproximada.
INPHARED pasó a INPHARED2 (phagebank.uk); cuando publique una tabla descargable se ajusta el mapeo.

La carga es idempotente: una segunda ejecución no duplica fagos ni orígenes.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fago, FagoOrigen, FuenteDatos

URL_INPHARED = "https://s3.climb.ac.uk/millardlab-inphared/2026/7Apr2026_millardlab_website_table.txt.gz"

# Filtros de calidad básicos (RF-29): rango de longitud de un genoma de fago completo.
LONGITUD_MIN_PB = 3_000
LONGITUD_MAX_PB = 600_000

# Campo interno -> nombres posibles de la columna en la tabla (en minúsculas). Se prueban en orden y se usa
# el primero que exista; así la carga tolera cambios de encabezado entre versiones de la tabla.
COLUMNAS = {
    "accesion": ("accession",),
    "nombre": ("description",),
    "longitud_bp": ("genome length (bp)",),
    "longitud_kb": ("genome length (kb)",),
    "familia": ("family",),
    "genero": ("genus",),
    "hospedador": ("host",),
    "ciclo": ("phageleads lifestyle", "lifestyle"),
    "completitud": ("checkv completeness",),
}


@dataclass
class Resumen:
    """Contadores de lo ocurrido en la carga; se imprimen al terminar."""

    leidos: int = 0
    filtrados_por_hospedador: int = 0
    descartados_por_calidad: int = 0
    duplicados_en_archivo: int = 0
    fagos_nuevos: int = 0
    fagos_existentes: int = 0
    origenes_nuevos: int = 0


def limpiar_html(valor: str) -> str:
    """Quita las etiquetas HTML (la accesión viene dentro de un enlace) y los espacios sobrantes."""
    return re.sub(r"<[^>]+>", "", valor).strip()


def normalizar_ciclo(valor: str | None) -> str:
    """Convierte el ciclo de vida de la fuente (en inglés) a los valores del modelo; si no se reconoce, `desconocido`."""
    v = (valor or "").strip().lower()
    if v in ("lytic", "virulent", "litico", "lítico"):
        return "litico"
    if v in ("temperate", "templado"):
        return "templado"
    return "desconocido"


def _opcional(texto: str | None) -> str | None:
    """Texto limpio, o None si la fuente dejó el campo vacío o con un marcador de 'sin dato'."""
    texto = limpiar_html(texto or "")
    return None if texto in ("", "NA", "N/A", "Unclassified") else texto


def leer_filas(texto: Iterable[str]) -> Iterator[dict]:
    """Lee la tabla de INPHARED y entrega diccionarios con las claves internas."""
    lector = csv.DictReader(texto, delimiter="\t")
    por_clave = {c.strip().lower(): c for c in (lector.fieldnames or [])}
    # Para cada campo interno, el nombre real de la columna en este archivo (o None si no existe).
    indice: dict[str, str | None] = {}
    for clave, candidatos in COLUMNAS.items():
        indice[clave] = next((por_clave[c] for c in candidatos if c in por_clave), None)
    if indice["accesion"] is None or indice["nombre"] is None:
        raise ValueError("la tabla no tiene las columnas 'Accession' y 'Description'")

    def valor(fila: dict, clave: str) -> str | None:
        columna = indice[clave]
        return fila.get(columna) if columna else None

    for fila in lector:
        # La longitud puede venir en pb o en KB redondeados; en KB se convierte, por eso queda aproximada.
        longitud = None
        if valor(fila, "longitud_bp"):
            longitud = int(float(valor(fila, "longitud_bp")))
        elif valor(fila, "longitud_kb"):
            longitud = int(float(valor(fila, "longitud_kb")) * 1000)
        yield {
            "accesion": limpiar_html(valor(fila, "accesion") or ""),
            "nombre": limpiar_html(valor(fila, "nombre") or ""),
            "longitud_pb": longitud,
            "familia": _opcional(valor(fila, "familia")),
            "genero": _opcional(valor(fila, "genero")),
            "hospedador": _opcional(valor(fila, "hospedador")),
            "ciclo": normalizar_ciclo(valor(fila, "ciclo")),
            "completitud": _opcional(valor(fila, "completitud")),
        }


def sembrar(
    session: Session,
    filas: Iterable[dict],
    fuente: str,
    version: str,
    hospedador: str | None = None,
    limite: int | None = None,
    url: str | None = None,
) -> Resumen:
    """Inserta fagos y su origen; no hace commit."""
    resumen = Resumen()
    # Registra (o reutiliza) la fuente y versión de la que vienen los datos.
    fuente_db = session.execute(
        select(FuenteDatos).where(FuenteDatos.nombre == fuente, FuenteDatos.version == version)
    ).scalar_one_or_none()
    if fuente_db is None:
        fuente_db = FuenteDatos(nombre=fuente, version=version, url=url)
        session.add(fuente_db)
        session.flush()

    vistos: set[str] = set()  # accesiones ya aceptadas en esta corrida
    for fila in filas:
        resumen.leidos += 1
        if hospedador and hospedador.lower() not in (fila["hospedador"] or "").lower():
            resumen.filtrados_por_hospedador += 1
            continue
        largo = fila["longitud_pb"]
        # Calidad: sin accesión no hay identificador, y fuera del rango de longitud no es un fago completo.
        # Si la fuente no informa longitud (None) no se descarta.
        if not fila["accesion"] or (largo is not None and not LONGITUD_MIN_PB <= largo <= LONGITUD_MAX_PB):
            resumen.descartados_por_calidad += 1
            continue
        if fila["accesion"] in vistos:
            resumen.duplicados_en_archivo += 1
            continue
        # El límite cuenta fagos aceptados (no filas leídas) y corta la lectura al alcanzarlo.
        if limite is not None and len(vistos) >= limite:
            break
        vistos.add(fila["accesion"])

        # Idempotencia: si el fago ya existe en la base se reutiliza en vez de duplicarlo.
        fago = session.execute(select(Fago).where(Fago.accesion == fila["accesion"])).scalar_one_or_none()
        if fago is None:
            fago = Fago(
                accesion=fila["accesion"],
                nombre=fila["nombre"],
                familia=fila["familia"],
                genero=fila["genero"],
                ciclo_vida=fila["ciclo"],
                longitud_pb=largo,
                completitud=fila["completitud"],
                hospedador_declarado=fila["hospedador"],
            )
            session.add(fago)
            session.flush()
            resumen.fagos_nuevos += 1
        else:
            resumen.fagos_existentes += 1

        # Un fago puede tener varios orígenes (uno por fuente y versión); el par (fago, fuente) es la clave.
        origen = session.get(FagoOrigen, (fago.id, fuente_db.id))
        if origen is None:
            session.add(
                FagoOrigen(fago_id=fago.id, fuente_id=fuente_db.id, id_externo=fila["accesion"], version_origen=version)
            )
            resumen.origenes_nuevos += 1
    session.flush()
    return resumen


def abrir_tabla(ruta: Path) -> io.TextIOBase:
    """Abre la tabla de INPHARED, comprimida con gzip o en texto plano."""
    if ruta.suffix.lower() == ".gz":
        return gzip.open(ruta, "rt", encoding="utf-8", errors="replace")
    return open(ruta, "rt", encoding="utf-8", errors="replace")


def descargar(url: str, destino: Path) -> Path:
    """Descarga la tabla a `destino` (creando la carpeta si hace falta)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    print(f"Descargando {url}", file=sys.stderr)
    urllib.request.urlretrieve(url, destino)  # noqa: S310 - URL fija o indicada por el operador
    return destino


def version_desde_nombre(nombre: str) -> str:
    """'7Apr2026_millardlab_website_table.txt.gz' -> '7Apr2026'."""
    coincidencia = re.match(r"(\d{1,2}[A-Za-z]{3}\d{4})", nombre)
    return coincidencia.group(1) if coincidencia else "desconocida"


def main(argv: list[str] | None = None) -> int:
    """Línea de comandos: obtiene la tabla (descargándola si se pide), la filtra y la carga en la base."""
    ap = argparse.ArgumentParser(description="Puebla el banco de fagos desde la tabla de INPHARED.")
    ap.add_argument("--archivo", type=Path, default=None, help="por defecto data/raw/<nombre del archivo de la URL>")
    ap.add_argument("--descargar", action="store_true", help="descarga la tabla si el archivo no existe")
    ap.add_argument("--url", default=URL_INPHARED)
    ap.add_argument("--version", default=None, help="versión de la fuente; por defecto sale del nombre del archivo")
    ap.add_argument("--hospedador", default=None, help="filtra por texto en la columna Host, p. ej. Klebsiella")
    ap.add_argument("--limite", type=int, default=None, help="máximo de fagos a cargar")
    args = ap.parse_args(argv)

    archivo = args.archivo or Path("data/raw") / Path(args.url).name
    if not archivo.exists():
        if not args.descargar:
            print(f"No existe {archivo}. Use --descargar o indique --archivo.", file=sys.stderr)
            return 2
        descargar(args.url, archivo)

    from app.db import get_sessionmaker  # import tardío: las pruebas no necesitan la base real

    version = args.version or version_desde_nombre(archivo.name)
    if version == "desconocida":
        print("No se pudo deducir la versión del nombre del archivo; indique --version.", file=sys.stderr)
        return 2
    with abrir_tabla(archivo) as texto, get_sessionmaker()() as session:
        resumen = sembrar(
            session, leer_filas(texto), "INPHARED", version, hospedador=args.hospedador, limite=args.limite, url=args.url
        )
        session.commit()
    for campo, valor in resumen.__dict__.items():
        print(f"{campo}: {valor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
