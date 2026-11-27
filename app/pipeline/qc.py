"""Control de calidad del genoma (RF-18, RF-19).

Los umbrales por defecto son valores iniciales razonables para un ensamblado de
*Klebsiella pneumoniae* (~5,0 a 5,8 Mb). Son configurables y se calibran con
genomas reales (SRS, punto abierto 4; diseño, punto 6).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .fasta import leer_fasta

APROBADO = "aprobado"
ADVERTENCIA = "advertencia"
RECHAZADO = "rechazado"


@dataclass(frozen=True)
class Metricas:
    """Medidas del ensamblado (el genoma armado a partir de los fragmentos de secuenciación)."""

    longitud: int  # suma de todos los contigs, en pares de bases (pb)
    contigs: int  # cuántos fragmentos continuos tiene el ensamblado; menos es mejor
    n50: int  # ver `calcular_n50`
    gc: float  # porcentaje de GC sobre las bases no ambiguas
    prop_ambiguas: float  # fracción de bases que no son A, C, G ni T


@dataclass(frozen=True)
class Umbrales:
    """Límites de cada métrica. Fuera de `*_rechazo` el genoma se rechaza; fuera de `*_advertencia` solo se avisa."""

    longitud_min_rechazo: int = 4_000_000
    longitud_max_rechazo: int = 7_000_000
    longitud_min_advertencia: int = 4_800_000
    longitud_max_advertencia: int = 6_200_000
    contigs_max_rechazo: int = 1_000
    contigs_max_advertencia: int = 200
    n50_min_advertencia: int = 50_000
    ambiguas_max_rechazo: float = 0.05
    ambiguas_max_advertencia: float = 0.005


@dataclass(frozen=True)
class ResultadoQC:
    """Veredicto del control de calidad: las métricas, el resultado y los motivos que lo explican."""

    metricas: Metricas
    resultado: str  # APROBADO, ADVERTENCIA o RECHAZADO
    motivos: list[str]

    def como_dict(self) -> dict:
        """Versión serializable a JSON, para guardarla en la columna JSONB `analisis_genomico.detalle`."""
        return {"metricas": asdict(self.metricas), "resultado": self.resultado, "motivos": self.motivos}


def calcular_n50(largos: list[int]) -> int:
    """N50: largo del contig a partir del cual se cubre al menos la mitad del genoma."""
    if not largos:
        return 0
    total = sum(largos)
    acumulado = 0
    # Se suman los contigs del más largo al más corto hasta cubrir la mitad del total.
    for largo in sorted(largos, reverse=True):
        acumulado += largo
        if acumulado * 2 >= total:
            return largo
    return 0  # inalcanzable: la suma siempre llega al total


def calcular_metricas(ruta: str | Path) -> Metricas:
    """Recorre el FASTA una vez y calcula longitud, contigs, N50, %GC y proporción de bases ambiguas."""
    largos: list[int] = []
    gc = at = ambiguas = 0
    for _, secuencia in leer_fasta(ruta):
        largos.append(len(secuencia))
        g, c = secuencia.count("G"), secuencia.count("C")
        a, t = secuencia.count("A"), secuencia.count("T")
        gc += g + c
        at += a + t
        # Ambigua = cualquier carácter que no sea A, C, G ni T (p. ej. N, que significa "base desconocida").
        ambiguas += len(secuencia) - (g + c + a + t)
    longitud = sum(largos)
    no_ambiguas = gc + at
    return Metricas(
        longitud=longitud,
        contigs=len(largos),
        n50=calcular_n50(largos),
        # Los `if ... else 0.0` evitan dividir por cero en un archivo sin bases.
        gc=round(100 * gc / no_ambiguas, 2) if no_ambiguas else 0.0,
        prop_ambiguas=round(ambiguas / longitud, 6) if longitud else 0.0,
    )


def clasificar(m: Metricas, u: Umbrales | None = None) -> ResultadoQC:
    """Aplica los umbrales: cualquier rechazo rechaza el genoma; si no, cualquier aviso deja una advertencia."""
    u = u or Umbrales()
    rechazos: list[str] = []
    avisos: list[str] = []

    # Cada métrica se evalúa en dos niveles: el rechazo se revisa primero (`if`) y el aviso solo si no hubo rechazo (`elif`).
    if m.longitud < u.longitud_min_rechazo or m.longitud > u.longitud_max_rechazo:
        rechazos.append(f"longitud {m.longitud} pb fuera del rango aceptable")
    elif m.longitud < u.longitud_min_advertencia or m.longitud > u.longitud_max_advertencia:
        avisos.append(f"longitud {m.longitud} pb fuera del rango esperado")

    if m.contigs > u.contigs_max_rechazo:
        rechazos.append(f"{m.contigs} contigs: ensamblado demasiado fragmentado")
    elif m.contigs > u.contigs_max_advertencia:
        avisos.append(f"{m.contigs} contigs: ensamblado fragmentado")

    # El N50 bajo solo genera aviso, nunca rechazo.
    if m.n50 < u.n50_min_advertencia:
        avisos.append(f"N50 de {m.n50} pb es bajo")

    if m.prop_ambiguas > u.ambiguas_max_rechazo:
        rechazos.append(f"{m.prop_ambiguas:.2%} de bases ambiguas")
    elif m.prop_ambiguas > u.ambiguas_max_advertencia:
        avisos.append(f"{m.prop_ambiguas:.2%} de bases ambiguas")

    if rechazos:
        # Si se rechaza, también se listan los avisos para que el usuario vea el cuadro completo.
        return ResultadoQC(m, RECHAZADO, rechazos + avisos)
    if avisos:
        return ResultadoQC(m, ADVERTENCIA, avisos)
    return ResultadoQC(m, APROBADO, [])
