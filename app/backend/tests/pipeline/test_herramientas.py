"""Wrappers de herramientas externas, con el programa reemplazado (no se necesita Prodigal ni Kaptive)."""
import gzip
from types import SimpleNamespace

import pytest

from pipeline import especie, genes, herramientas, locus_k
from pipeline.herramientas import ErrorHerramienta


def test_programa_inexistente_da_error_claro():
    with pytest.raises(ErrorHerramienta, match="no se encontró el programa"):
        herramientas.ejecutar(["programa-que-no-existe-sirfa"])


def test_version_de_programa_inexistente_es_desconocida():
    assert herramientas.version(["programa-que-no-existe-sirfa", "-v"]) == "desconocida"


def test_predecir_genes_cuenta_proteinas_y_descomprime_gzip(tmp_path, monkeypatch):
    genoma = tmp_path / "g.fasta.gz"
    with gzip.open(genoma, "wt", encoding="utf-8") as f:
        f.write(">c1\nACGT\n")
    visto = {}

    def falso(comando, timeout=3600):
        visto["comando"] = comando
        salida = comando[comando.index("-a") + 1]
        with open(salida, "w", encoding="utf-8") as f:
            f.write(">g1\nMKV\n>g2\nMLL\n>g3\nMAA\n")
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(genes, "ejecutar", falso)
    r = genes.predecir_genes(genoma, tmp_path / "salida")
    assert (r.n_genes, r.n_proteinas) == (3, 3)
    assert visto["comando"][0] == "prodigal"
    assert visto["comando"][2].endswith("g.fasta")  # entrada ya descomprimida


def test_leer_resultado_de_kaptive(tmp_path):
    (tmp_path / "resultado.tsv").write_text(
        "Assembly\tBest match locus\tMatch confidence\nasm1\tKL2\tGood\n", encoding="utf-8"
    )
    r = locus_k.leer_resultado(tmp_path)
    assert (r.tipo, r.confianza) == ("KL2", "Good")


def test_kaptive_sin_tabla_de_resultados_falla(tmp_path):
    with pytest.raises(ErrorHerramienta, match="ninguna tabla"):
        locus_k.leer_resultado(tmp_path)


def test_mejor_referencia_elige_la_distancia_menor():
    salida = "ref_a.fna\tg.fasta\t0.2\t0\t5/1000\nref_b.fna\tg.fasta\t0.01\t0\t900/1000\n"
    assert especie.mejor_referencia(salida) == ("ref_b.fna", 0.01)


def test_sin_sketch_la_especie_no_se_verifica():
    r = especie.identificar_especie("g.fasta", "Klebsiella pneumoniae", sketch=None, mapa=None)
    assert r.especie == "Klebsiella pneumoniae" and r.verificada is False


def test_identificar_especie_con_mash_falso(tmp_path, monkeypatch):
    sketch, mapa = tmp_path / "r.msh", tmp_path / "especies.tsv"
    sketch.write_bytes(b"x")
    mapa.write_text("ref_b.fna\tKlebsiella pneumoniae\nref_a.fna\tEscherichia coli\n", encoding="utf-8")
    monkeypatch.setattr(
        especie,
        "ejecutar",
        lambda cmd, timeout=3600: SimpleNamespace(stdout="ref_a.fna\tg\t0.2\t0\t1/1\nref_b.fna\tg\t0.01\t0\t9/9\n"),
    )
    r = especie.identificar_especie("g.fasta", "x", sketch, mapa)
    assert (r.especie, r.verificada) == ("Klebsiella pneumoniae", True)
    assert especie.es_kpneumoniae(r.especie)


def test_distancia_alta_deja_la_especie_sin_identificar(tmp_path, monkeypatch):
    sketch, mapa = tmp_path / "r.msh", tmp_path / "especies.tsv"
    sketch.write_bytes(b"x")
    mapa.write_text("ref_a.fna\tKlebsiella pneumoniae\n", encoding="utf-8")
    monkeypatch.setattr(
        especie, "ejecutar", lambda cmd, timeout=3600: SimpleNamespace(stdout="ref_a.fna\tg\t0.30\t0\t1/1\n")
    )
    r = especie.identificar_especie("g.fasta", "x", sketch, mapa)
    assert r.especie is None and not especie.es_kpneumoniae(r.especie)
