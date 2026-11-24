"""Carga del banco. Los datos son SINTÉTICOS, con el formato de la tabla de INPHARED; no son fagos reales."""
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models import Base, Fago, FagoOrigen, FuenteDatos
from pipeline.seed_phage_bank import leer_filas, normalizar_ciclo, sembrar, version_desde_nombre

# Encabezados de la tabla de INPHARED (formato verificado, ver el módulo seed_phage_bank).
CABECERA = "Accession\tDescription\tGenome Length (KB)\tmolGC (%)\tGenus\tSub-family\tFamily\tHost\n"


def fila(acc, desc, kb, host, familia="Drexlerviridae", genero="Unclassified"):
    """Una fila de la tabla sintética; la accesión va envuelta en un enlace HTML, como en la fuente real."""
    enlace = f'<a href="https://www.ncbi.nlm.nih.gov/nuccore/{acc}">{acc}</a>'
    return f"{enlace}\t{desc}\t{kb}\t50\t{genero}\tUnclassified\t{familia}\t{host}\n"


# Seis filas: tres fagos de Klebsiella válidos, uno de otro hospedador, uno demasiado corto (1 KB) y una accesión repetida.
TABLA = (
    CABECERA
    + fila("SYN000001", "Klebsiella phage sintetico 1", 51, "Klebsiella")
    + fila("SYN000002", "Klebsiella phage sintetico 2", 167, "Klebsiella", familia="Unclassified")
    + fila("SYN000003", "Escherichia phage sintetico 3", 45, "Escherichia")
    + fila("SYN000004", "Klebsiella phage demasiado corto", 1, "Klebsiella")
    + fila("SYN000001", "Klebsiella phage sintetico 1 repetido", 51, "Klebsiella")
    + fila("SYN000005", "Klebsiella phage sintetico 5", 41, "Klebsiella", genero="Przondovirus")
)


@pytest.fixture()
def sesion():
    """Base SQLite en memoria con todas las tablas, nueva en cada prueba."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def filas():
    """Las filas de TABLA ya interpretadas, como las entrega `leer_filas`."""
    return leer_filas(TABLA.splitlines(keepends=True))


def test_se_limpia_el_enlace_html_y_se_convierte_kb_a_pb():
    primera = next(filas())
    assert primera["accesion"] == "SYN000001"
    assert primera["longitud_pb"] == 51_000
    assert primera["familia"] == "Drexlerviridae"
    assert primera["genero"] is None  # "Unclassified" se guarda como dato ausente


def test_filtra_por_hospedador_descarta_cortos_y_duplicados(sesion):
    r = sembrar(sesion, filas(), "INPHARED", "7Apr2026", hospedador="Klebsiella")
    assert r.leidos == 6
    assert r.filtrados_por_hospedador == 1
    assert r.descartados_por_calidad == 1
    assert r.duplicados_en_archivo == 1
    assert r.fagos_nuevos == 3
    assert sesion.scalar(select(func.count()).select_from(Fago)) == 3
    assert sesion.scalar(select(func.count()).select_from(FagoOrigen)) == 3


def test_limite_acota_la_cantidad_de_fagos(sesion):
    r = sembrar(sesion, filas(), "INPHARED", "7Apr2026", hospedador="Klebsiella", limite=2)
    assert r.fagos_nuevos == 2


def test_segunda_carga_no_duplica_nada(sesion):
    sembrar(sesion, filas(), "INPHARED", "7Apr2026", hospedador="Klebsiella")
    r = sembrar(sesion, filas(), "INPHARED", "7Apr2026", hospedador="Klebsiella")
    assert r.fagos_nuevos == 0 and r.fagos_existentes == 3 and r.origenes_nuevos == 0
    assert sesion.scalar(select(func.count()).select_from(Fago)) == 3
    assert sesion.scalar(select(func.count()).select_from(FuenteDatos)) == 1


def test_un_fago_de_otra_version_conserva_ambos_origenes(sesion):
    sembrar(sesion, filas(), "INPHARED", "7Apr2026", hospedador="Klebsiella")
    sembrar(sesion, filas(), "INPHARED", "7May2026", hospedador="Klebsiella")
    assert sesion.scalar(select(func.count()).select_from(Fago)) == 3
    assert sesion.scalar(select(func.count()).select_from(FagoOrigen)) == 6


def test_los_fagos_nuevos_quedan_pendientes_de_curaduria(sesion):
    sembrar(sesion, filas(), "INPHARED", "7Apr2026", hospedador="Klebsiella")
    estados = set(sesion.scalars(select(Fago.estado_curaduria)))
    assert estados == {"pendiente"}


def test_tabla_sin_columnas_obligatorias_falla():
    with pytest.raises(ValueError):
        list(leer_filas(["Nombre\tOtra\n", "x\ty\n"]))


def test_version_y_ciclo():
    assert version_desde_nombre("7Apr2026_millardlab_website_table.txt.gz") == "7Apr2026"
    assert version_desde_nombre("otra_cosa.tsv") == "desconocida"
    assert normalizar_ciclo("Lytic") == "litico"
    assert normalizar_ciclo("temperate") == "templado"
    assert normalizar_ciclo(None) == "desconocido"
