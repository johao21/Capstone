"""Control de calidad: N50, métricas y clasificación (aprobado, advertencia, rechazado) con umbrales pequeños."""
import pytest

from pipeline.qc import (
    ADVERTENCIA,
    APROBADO,
    RECHAZADO,
    Metricas,
    Umbrales,
    calcular_metricas,
    calcular_n50,
    clasificar,
)


def test_n50_de_un_ejemplo_conocido():
    # Total 100; ordenados 40, 30, 20, 10; 40 < 50 y 40 + 30 >= 50, así que N50 = 30.
    assert calcular_n50([10, 20, 30, 40]) == 30


def test_n50_de_un_solo_contig_y_de_lista_vacia():
    assert calcular_n50([500]) == 500
    assert calcular_n50([]) == 0


def test_metricas_de_un_genoma_pequeno(tmp_path):
    f = tmp_path / "g.fasta"
    f.write_text(">c1\nGGCC\n>c2\nAATTNN\n", encoding="utf-8")
    m = calcular_metricas(f)
    assert m.longitud == 10
    assert m.contigs == 2
    assert m.n50 == 6
    assert m.gc == 50.0  # 4 G/C sobre 8 bases no ambiguas
    assert m.prop_ambiguas == pytest.approx(0.2)


# Umbrales pequeños para probar cada caso con números fáciles de leer.
U = Umbrales(
    longitud_min_rechazo=100,
    longitud_max_rechazo=1000,
    longitud_min_advertencia=200,
    longitud_max_advertencia=800,
    contigs_max_rechazo=50,
    contigs_max_advertencia=10,
    n50_min_advertencia=50,
    ambiguas_max_rechazo=0.05,
    ambiguas_max_advertencia=0.01,
)


def metricas(**kw):
    """Métricas de un genoma sano; cada prueba cambia solo el campo que quiere probar."""
    base = dict(longitud=500, contigs=3, n50=300, gc=57.0, prop_ambiguas=0.0)
    base.update(kw)
    return Metricas(**base)


def test_genoma_dentro_de_los_umbrales_se_aprueba():
    r = clasificar(metricas(), U)
    assert r.resultado == APROBADO
    assert r.motivos == []


@pytest.mark.parametrize(
    "cambio",
    [{"longitud": 150}, {"longitud": 900}, {"contigs": 20}, {"n50": 10}, {"prop_ambiguas": 0.02}],
)
def test_desviaciones_moderadas_dan_advertencia(cambio):
    r = clasificar(metricas(**cambio), U)
    assert r.resultado == ADVERTENCIA
    assert r.motivos


@pytest.mark.parametrize(
    "cambio",
    [{"longitud": 50}, {"longitud": 2000}, {"contigs": 60}, {"prop_ambiguas": 0.2}],
)
def test_desviaciones_graves_se_rechazan(cambio):
    r = clasificar(metricas(**cambio), U)
    assert r.resultado == RECHAZADO
    assert r.motivos


def test_resultado_se_serializa_para_guardarlo():
    d = clasificar(metricas(), U).como_dict()
    assert d["resultado"] == APROBADO
    assert d["metricas"]["contigs"] == 3
