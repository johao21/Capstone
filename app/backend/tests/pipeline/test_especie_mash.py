"""Decisión de especie y construcción de referencias, con Mash y la red reemplazados."""
from types import SimpleNamespace

import pytest

from pipeline import especie, referencias
from pipeline.especie import decidir, es_kpneumoniae, ordenar_referencias

# Mapa archivo de referencia -> especie, como `especies.tsv`; kp1 y kp2 son de la misma especie a propósito.
MAPA = {
    "kp1.fna.gz": "Klebsiella pneumoniae",
    "kp2.fna.gz": "Klebsiella pneumoniae",
    "kv.fna.gz": "Klebsiella variicola",
    "ec.fna.gz": "Escherichia coli",
}


def pares(**distancias):
    """Arma la lista ordenada (distancia, archivo) que produce `ordenar_referencias`: pares(kp1=0.01) -> [(0.01, "kp1.fna.gz")]."""
    return sorted((d, f"{nombre}.fna.gz") for nombre, d in distancias.items())


def test_ordena_de_menor_a_mayor_distancia():
    salida = "a.fna.gz\tq\t0.2\t0\t1/1\nb.fna.gz\tq\t0.01\t0\t9/9\nc.fna.gz\tq\t0.05\t0\t5/9\n"
    assert [r for _, r in ordenar_referencias(salida)] == ["b.fna.gz", "c.fna.gz", "a.fna.gz"]


def test_k_pneumoniae_clara_se_acepta():
    r = decidir(pares(kp1=0.012, kv=0.040, ec=0.15), MAPA)
    assert r.especie == "Klebsiella pneumoniae" and es_kpneumoniae(r.especie)
    assert r.verificada and r.referencia == "kp1.fna.gz"
    assert r.segunda_especie == "Klebsiella variicola"


def test_la_segunda_referencia_es_de_otra_especie_no_de_la_misma():
    # kp2 es de la misma especie que kp1: la "segunda especie" debe ser variicola, no pneumoniae.
    r = decidir(pares(kp1=0.010, kp2=0.011, kv=0.040), MAPA)
    assert r.segunda_especie == "Klebsiella variicola"
    assert r.especie == "Klebsiella pneumoniae"


def test_empate_entre_especies_cercanas_es_ambiguo_y_no_se_acepta():
    r = decidir(pares(kp1=0.030, kv=0.032), MAPA)
    assert r.especie is None and not es_kpneumoniae(r.especie)
    assert "ambigua" in r.motivo and r.verificada


def test_otra_especie_se_identifica_y_no_es_k_pneumoniae():
    r = decidir(pares(ec=0.011, kp1=0.19), MAPA)
    assert r.especie == "Escherichia coli" and not es_kpneumoniae(r.especie)


def test_distancia_sobre_el_umbral_deja_la_especie_sin_identificar():
    r = decidir(pares(kp1=0.09, ec=0.2), MAPA)
    assert r.especie is None and "umbral" in r.motivo


def test_referencia_fuera_del_mapa_no_se_acepta():
    r = decidir([(0.01, "desconocida.fna.gz")], MAPA)
    assert r.especie is None and "mapa" in r.motivo


def test_rutas_por_defecto_y_por_variables_de_entorno(monkeypatch, tmp_path):
    monkeypatch.delenv("MASH_SKETCH", raising=False)
    monkeypatch.delenv("MASH_MAPA", raising=False)
    monkeypatch.setenv("REFERENCIAS_DIR", str(tmp_path))
    sketch, mapa = especie.rutas_referencias()
    assert sketch == tmp_path / "referencias.msh" and mapa == tmp_path / "especies.tsv"
    monkeypatch.setenv("MASH_SKETCH", "/otra/ruta.msh")
    assert especie.rutas_referencias()[0].as_posix() == "/otra/ruta.msh"


# ------------------------------------------------------------- referencias
def test_url_de_ncbi_coincide_con_la_verificada():
    assert referencias.url_genoma("GCF_000240185.1", "ASM24018v2") == (
        "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/240/185/GCF_000240185.1_ASM24018v2/"
        "GCF_000240185.1_ASM24018v2_genomic.fna.gz"
    )


def test_la_lista_de_referencias_es_consistente():
    lista = referencias.leer_lista()
    assert len(lista) == 13
    assert len({r.accesion for r in lista}) == 13
    assert sum(r.especie == "Klebsiella pneumoniae" for r in lista) == 2
    for cercana in ("Klebsiella variicola", "Klebsiella quasipneumoniae", "Klebsiella oxytoca"):
        assert any(r.especie == cercana for r in lista), cercana
    # Los genomas de prueba no pueden estar entre las referencias.
    assert not {"GCF_000016305.1", "GCF_000008865.2"} & {r.accesion for r in lista}


def test_construir_descarga_lo_que_falta_y_arma_el_sketch(tmp_path, monkeypatch):
    lista = referencias.leer_lista()[:3]
    bajadas, comandos = [], []
    monkeypatch.setattr(referencias, "descargar", lambda url, destino: (bajadas.append(url), destino.write_bytes(b"x")))
    monkeypatch.setattr(
        referencias, "ejecutar", lambda cmd, timeout=3600: (comandos.append(cmd), SimpleNamespace(stdout=""))[1]
    )
    sketch = referencias.construir(tmp_path, lista)
    assert sketch == tmp_path / "referencias.msh"
    assert len(bajadas) == 3
    assert comandos[0][:7] == ["mash", "sketch", "-k", "21", "-s", "10000", "-o"]
    assert (tmp_path / "especies.tsv").read_text(encoding="utf-8").splitlines()[0] == "GCF_000240185.1.fna.gz\tKlebsiella pneumoniae"

    bajadas.clear()
    referencias.construir(tmp_path, lista)
    assert bajadas == []  # lo ya descargado no se vuelve a bajar


def test_lista_mal_formada_da_error_claro(tmp_path):
    f = tmp_path / "malo.tsv"
    f.write_text("GCF_1\tsolo dos columnas\n", encoding="utf-8")
    with pytest.raises(ValueError, match="4 columnas"):
        referencias.leer_lista(f)
