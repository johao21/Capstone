"""Lectura y validación de archivos FASTA de nucleótidos (RF-09, RF-10)."""
from __future__ import annotations

import gzip
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Alfabeto IUPAC de nucleótidos (ADN), en mayúsculas.
ALFABETO_ADN = set("ACGTNRYKMSWBDHV")
BASES_NO_AMBIGUAS = set("ACGT")


@dataclass
class ResultadoFasta:
    """Resultado de validar un FASTA: si es válido, cuánto contiene y, si no, qué errores tiene."""

    valido: bool
    registros: int = 0  # cantidad de secuencias (contigs) del archivo
    longitud_total: int = 0
    errores: list[str] = field(default_factory=list)


def abrir_texto(ruta: str | Path):
    """Abre un FASTA plano o comprimido con gzip como texto."""
    ruta = Path(ruta)
    # errors="replace": un byte inválido no aborta la lectura; queda como carácter raro y lo detecta la validación.
    if ruta.suffix.lower() == ".gz":
        return gzip.open(ruta, "rt", encoding="utf-8", errors="replace")
    return open(ruta, "rt", encoding="utf-8", errors="replace")


def leer_fasta(ruta: str | Path) -> Iterator[tuple[str, str]]:
    """Entrega (identificador, secuencia en mayúsculas) de cada registro."""
    identificador: str | None = None
    partes: list[str] = []  # las líneas de la secuencia actual; se unen al llegar al siguiente encabezado
    with abrir_texto(ruta) as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            if linea.startswith(">"):
                # Un encabezado nuevo cierra el registro anterior (si hubo uno).
                if identificador is not None:
                    yield identificador, "".join(partes).upper()
                # El identificador es la primera palabra del encabezado; el resto es descripción.
                identificador = linea[1:].split()[0] if len(linea) > 1 else ""
                partes = []
            else:
                partes.append(linea)
    # El último registro no tiene encabezado siguiente que lo cierre.
    if identificador is not None:
        yield identificador, "".join(partes).upper()


def validar_fasta(ruta: str | Path, max_errores: int = 5) -> ResultadoFasta:
    """Valida que el archivo sea un FASTA de nucleótidos bien formado.

    Lee en flujo, sin cargar el archivo completo en memoria. Se detiene al
    acumular `max_errores` para no devolver miles de mensajes.
    """
    res = ResultadoFasta(valido=False)
    en_registro = False
    largo_registro = 0
    registro_invalido = False  # ya se informó un error en este registro: no se suma "sin secuencia"
    vistos: set[str] = set()

    def error(msg: str) -> bool:
        """Anota el error; devuelve True cuando ya se llegó al máximo y conviene dejar de leer."""
        res.errores.append(msg)
        return len(res.errores) >= max_errores

    def cerrar_registro(numero_linea: int) -> bool:
        """Al terminar un registro, avisa si quedó sin secuencia (usa las variables de la función externa)."""
        if en_registro and largo_registro == 0 and not registro_invalido:
            return error(f"línea {numero_linea}: el registro no tiene secuencia")
        return False

    try:
        with abrir_texto(ruta) as f:
            numero = 0
            for numero, linea in enumerate(f, start=1):
                linea = linea.strip()
                if not linea:
                    continue
                if linea.startswith(">"):
                    # Encabezado: primero se cierra (y se revisa) el registro anterior.
                    if cerrar_registro(numero):
                        return res
                    nombre = linea[1:].split()[0] if len(linea) > 1 else ""
                    if not nombre:
                        if error(f"línea {numero}: encabezado sin identificador"):
                            return res
                    elif nombre in vistos:
                        if error(f"línea {numero}: identificador repetido '{nombre}'"):
                            return res
                    vistos.add(nombre)
                    res.registros += 1
                    en_registro, largo_registro, registro_invalido = True, 0, False
                    continue
                if not en_registro:
                    if error(f"línea {numero}: hay secuencia antes del primer encabezado '>'"):
                        return res
                    continue
                # Línea de secuencia: todos sus caracteres deben pertenecer al alfabeto de ADN.
                secuencia = linea.upper()
                invalidos = set(secuencia) - ALFABETO_ADN
                if invalidos:
                    muestra = "".join(sorted(invalidos))[:5]
                    registro_invalido = True
                    if error(f"línea {numero}: caracteres no válidos para ADN ({muestra})"):
                        return res
                    continue
                largo_registro += len(secuencia)
                res.longitud_total += len(secuencia)
            # Fin del archivo: se revisa también el último registro.
            if cerrar_registro(numero):
                return res
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        res.errores.append(f"no se pudo leer el archivo: {exc}")
        return res

    if res.registros == 0:
        res.errores.append("el archivo no contiene registros FASTA")
    res.valido = not res.errores
    return res
