"""Identificación de especie por distancia Mash contra genomas de referencia (RF-20, RN-03).

Cada genoma se compara con las referencias de `referencias.tsv` (ver `pipeline.referencias`). La especie es la
de la referencia más cercana, siempre que:

- la distancia no supere `UMBRAL_DISTANCIA` (≈ 95 % de identidad, el límite habitual de especie), y
- ninguna referencia de OTRA especie quede a menos de `MARGEN_AMBIGUEDAD`: dentro del complejo de
  *K. pneumoniae* las especies son muy cercanas y un empate no debe resolverse a favor de ninguna.

Si no hay sketch de referencia, la especie NO se verifica: se devuelve la declarada con `verificada=False`,
para que el pipeline no finja una verificación.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .herramientas import ErrorHerramienta, ejecutar

ESPECIE_OBJETIVO = "klebsiella pneumoniae"
UMBRAL_DISTANCIA = 0.05  # distancia Mash máxima para aceptar la especie; 0 = genomas idénticos
MARGEN_AMBIGUEDAD = 0.005  # si otra especie queda a menos de esto de la mejor, el resultado es ambiguo


@dataclass(frozen=True)
class ResultadoEspecie:
    """Resultado de la identificación. `especie` es None cuando no se pudo decidir (ver `motivo`)."""

    especie: str | None
    distancia: float | None
    verificada: bool  # False si no se pudo comparar y se usó la especie declarada
    referencia: str | None = None  # archivo de la referencia más cercana
    segunda_especie: str | None = None  # mejor coincidencia de una especie distinta; sirve para detectar ambigüedad
    segunda_distancia: float | None = None
    motivo: str | None = None  # por qué no se decidió la especie


def es_kpneumoniae(nombre: str | None) -> bool:
    """True si el nombre es exactamente la especie objetivo del MVP (sin distinguir mayúsculas)."""
    return nombre is not None and nombre.strip().lower() == ESPECIE_OBJETIVO


def rutas_referencias() -> tuple[Path, Path]:
    """Sketch y mapa de especies: de MASH_SKETCH y MASH_MAPA, o de REFERENCIAS_DIR (por defecto data/referencias)."""
    carpeta = Path(os.environ.get("REFERENCIAS_DIR", "data/referencias"))
    sketch = Path(os.environ.get("MASH_SKETCH") or carpeta / "referencias.msh")
    mapa = Path(os.environ.get("MASH_MAPA") or carpeta / "especies.tsv")
    return sketch, mapa


def leer_mapa(ruta: Path) -> dict[str, str]:
    """TSV de dos columnas: nombre del archivo de referencia y especie."""
    mapa: dict[str, str] = {}
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            partes = linea.rstrip("\n").split("\t")
            if len(partes) >= 2 and partes[0]:
                # Solo el nombre del archivo (sin carpeta): así coincide con lo que devuelve `ordenar_referencias`.
                mapa[Path(partes[0]).name] = partes[1].strip()
    return mapa


def ordenar_referencias(salida_mash: str) -> list[tuple[float, str]]:
    """De la salida de `mash dist` (ref, consulta, distancia, ...) devuelve (distancia, referencia) de menor a mayor."""
    pares: list[tuple[float, str]] = []
    for linea in salida_mash.splitlines():
        columnas = linea.split("\t")
        if len(columnas) >= 3:
            try:
                pares.append((float(columnas[2]), Path(columnas[0]).name))
            except ValueError:
                continue  # línea con una distancia que no es número: se ignora
    if not pares:
        raise ErrorHerramienta("Mash no devolvió distancias")
    return sorted(pares)


def mejor_referencia(salida_mash: str) -> tuple[str, float]:
    """La referencia más cercana y su distancia."""
    distancia, referencia = ordenar_referencias(salida_mash)[0]
    return referencia, distancia


def decidir(
    pares: list[tuple[float, str]],
    mapa: dict[str, str],
    umbral: float = UMBRAL_DISTANCIA,
    margen: float = MARGEN_AMBIGUEDAD,
) -> ResultadoEspecie:
    """Aplica las reglas del módulo a la lista ordenada de (distancia, referencia).

    Devuelve siempre `verificada=True`; si ninguna regla permite decidir, `especie` queda en None con su motivo.
    """
    distancia, referencia = pares[0]
    especie = mapa.get(referencia)
    # Primera referencia (en orden de cercanía) que pertenezca a una especie distinta de la mejor.
    segunda = next(((d, mapa.get(r)) for d, r in pares[1:] if mapa.get(r) != especie), None)
    segunda_distancia, segunda_especie = segunda if segunda else (None, None)
    # Campos que lleva cualquier resultado, decida o no.
    comun = dict(
        distancia=distancia, verificada=True, referencia=referencia,
        segunda_especie=segunda_especie, segunda_distancia=segunda_distancia,
    )
    if especie is None:
        return ResultadoEspecie(especie=None, motivo=f"la referencia {referencia} no está en el mapa de especies", **comun)
    if distancia > umbral:
        return ResultadoEspecie(especie=None, motivo=f"distancia {distancia:.4f} mayor que el umbral {umbral}", **comun)
    if segunda_especie is not None and segunda_distancia - distancia < margen:
        return ResultadoEspecie(
            especie=None,
            motivo=f"ambigua entre {especie} ({distancia:.4f}) y {segunda_especie} ({segunda_distancia:.4f})",
            **comun,
        )
    return ResultadoEspecie(especie=especie, **comun)


def identificar_especie(
    ruta_genoma: str | Path,
    declarada: str,
    sketch: Path | None = None,
    mapa: Path | None = None,
    umbral: float = UMBRAL_DISTANCIA,
    margen: float = MARGEN_AMBIGUEDAD,
) -> ResultadoEspecie:
    """Compara el genoma con las referencias usando Mash; sin referencias, devuelve la especie declarada sin verificar."""
    if sketch is None or mapa is None or not Path(sketch).exists() or not Path(mapa).exists():
        return ResultadoEspecie(especie=declarada, distancia=None, verificada=False)
    # `mash dist` compara la consulta (el genoma) contra todas las referencias del sketch.
    salida = ejecutar(["mash", "dist", str(sketch), str(ruta_genoma)]).stdout
    return decidir(ordenar_referencias(salida), leer_mapa(Path(mapa)), umbral, margen)
