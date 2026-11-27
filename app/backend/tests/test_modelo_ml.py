"""El modelo de predicción de punta a punta con un conjunto sintético pequeño: entrenar, guardar, cargar, buscar el locus con BLAST,
predecir y explicar con SHAP. No mide la calidad del modelo real (eso lo hace `python -m ml.entrenar`); comprueba que las piezas encajan."""
import random
import shutil

import numpy as np
import pytest

from ml import modelo
from ml.datos import ConjuntoPHL

pytestmark = pytest.mark.skipif(shutil.which("blastp") is None or shutil.which("makeblastdb") is None, reason="BLAST+ no está instalado")

AMINOACIDOS = "ACDEFGHIKLMNPQRSTVWY"


def proteina(rng, largo=140):
    return "".join(rng.choice(AMINOACIDOS) for _ in range(largo))


@pytest.fixture(scope="module")
def conjunto():
    rng = random.Random(3)
    nrng = np.random.default_rng(3)
    cepas = [f"S{i}" for i in range(8)]
    fagos = ["F0", "F1", "F2", "F3"]
    rbp_fago = ["F0", "F1", "F1", "F2", "F3", "F3"]
    emb_locus = nrng.normal(size=(8, 16)).astype(np.float32)
    rbp_emb = nrng.normal(size=(6, 16)).astype(np.float32)
    # El fago F_j infecta a las cepas pares si j es par y a las impares si j es impar: una regla sencilla que el modelo puede aprender.
    etiquetas = np.array([[1.0 if (i % 2) == (j % 2) else 0.0 for j in range(4)] for i in range(8)], dtype=np.float32)
    etiquetas[0, 3] = np.nan  # un par no ensayado
    sim = np.eye(8, dtype=np.float32)
    return ConjuntoPHL(
        cepas=cepas, emb_locus=emb_locus, sim_locus=sim, proteinas_locus={c: [proteina(rng) for _ in range(8)] for c in cepas}, fagos=fagos,
        rbp_ids=[f"{f}_gp{i}" for i, f in enumerate(rbp_fago)], rbp_fago=rbp_fago, rbp_emb=rbp_emb, etiquetas=etiquetas,
    )


@pytest.fixture(scope="module")
def predictor(conjunto, tmp_path_factory):
    modelo.PARAMETROS_XGB.update(n_estimators=30, max_depth=2, n_jobs=1)
    final, _ = modelo.entrenar_final(conjunto)
    carpeta = tmp_path_factory.mktemp("modelo")
    modelo.guardar(carpeta, conjunto, final, {"top5": 1.0}, {"version": "sintetico"})
    return modelo.Predictor(carpeta)


def escribir_faa(ruta, proteinas):
    ruta.write_text("".join(f">p{i}\n{p}\n" for i, p in enumerate(proteinas)), encoding="utf-8")
    return ruta


def test_un_aislado_con_el_locus_de_una_cepa_conocida_se_parece_a_esa_cepa(conjunto, predictor, tmp_path):
    rng = random.Random(11)
    faa = escribir_faa(tmp_path / "p.faa", conjunto.proteinas_locus["S3"] + [proteina(rng) for _ in range(40)])
    r = predictor.predecir(faa)
    assert r["similitud_maxima"] >= 0.99 and r["cepas_similares"][0]["cepa"] == "S3"
    assert r["baja_confianza"] is False and r["motivo_baja_confianza"] is None


def test_un_aislado_de_locus_desconocido_se_marca_de_baja_confianza(predictor, tmp_path):
    rng = random.Random(99)
    r = predictor.predecir(escribir_faa(tmp_path / "p.faa", [proteina(rng) for _ in range(60)]))
    assert r["baja_confianza"] is True and "poco fiable" in r["motivo_baja_confianza"] and r["similitud_maxima"] < modelo.UMBRAL_SIMILITUD


def test_el_ranking_trae_todos_los_fagos_ordenados_con_explicacion_shap(conjunto, predictor, tmp_path):
    faa = escribir_faa(tmp_path / "p.faa", conjunto.proteinas_locus["S1"])
    ranking = predictor.predecir(faa)["ranking"]
    assert sorted(r["fago"] for r in ranking) == ["F0", "F1", "F2", "F3"]
    assert [r["rango"] for r in ranking] == [1, 2, 3, 4]
    assert all(a["puntaje"] >= b["puntaje"] for a, b in zip(ranking, ranking[1:]))
    e = ranking[0]["explicacion"]
    assert e["metodo"] == "shap" and set(e["bloques"]) == {"rbp_fago", "locus_k_hospedador"} and len(e["caracteristicas"]) == 6
    assert e["rbp"].startswith(ranking[0]["fago"])
    # El modelo aprendió la regla: S1 es impar, así que los fagos impares (F1 y F3) deben quedar arriba.
    assert {r["fago"] for r in ranking[:2]} == {"F1", "F3"}


def test_la_evidencia_cuenta_las_interacciones_de_las_cepas_de_locus_parecido(conjunto, predictor, tmp_path):
    ranking = predictor.predecir(escribir_faa(tmp_path / "p.faa", conjunto.proteinas_locus["S2"]))["ranking"]
    f0 = next(r for r in ranking if r["fago"] == "F0")
    assert f0["evidencia"] == {"interacciones_positivas": 1, "interacciones_negativas": 0, "cepas_probadas": 1, "referencias": [modelo.REFERENCIA]}


def test_los_grupos_por_locus_juntan_las_cepas_casi_identicas():
    sim = np.eye(5)
    sim[0, 1] = sim[1, 0] = 0.97
    sim[3, 4] = sim[4, 3] = 0.92
    grupos = modelo.grupos_por_locus(sim)
    assert grupos[0] == grupos[1] and grupos[3] == grupos[4] and len({grupos[0], grupos[2], grupos[3]}) == 3


def test_las_metricas_de_un_ranking_perfecto_y_uno_al_reves(conjunto):
    pares = {(i, j): conjunto.etiquetas[i, j] for i in range(8) for j in range(4) if not np.isnan(conjunto.etiquetas[i, j])}
    perfecto = modelo.metricas(conjunto, dict(pares))
    assert perfecto["auc"] == 1.0
    al_reves = modelo.metricas(conjunto, {k: 1.0 - v for k, v in pares.items()})
    assert al_reves["auc"] == 0.0


def test_la_calibracion_acerca_la_probabilidad_a_la_frecuencia_observada(conjunto):
    # Puntajes crudos inflados (como los de un modelo con scale_pos_weight): casi todos altos, aunque solo ~25 % de los pares son positivos.
    rng = np.random.default_rng(5)
    pares = [(i, j) for i in range(8) for j in range(4) if not np.isnan(conjunto.etiquetas[i, j])]
    crudos = {p: float(np.clip(0.55 + 0.4 * conjunto.etiquetas[p] + rng.normal(0, 0.05), 0.01, 0.99)) for p in pares}
    cal = modelo.calibrar(conjunto, crudos)
    frecuencia = float(np.mean([conjunto.etiquetas[p] for p in pares]))
    assert abs(cal["probabilidad_media_calibrada"] - frecuencia) < 0.05  # la media calibrada coincide con la frecuencia real
    calibrado = modelo.aplicar_calibracion(cal, np.array([0.2, 0.5, 0.9]))
    assert list(calibrado) == sorted(calibrado)  # no cambia el orden del ranking
    assert list(modelo.aplicar_calibracion(None, np.array([0.2, 0.9]))) == [0.2, 0.9]  # sin calibración, igual


def test_la_ficha_del_modelo_sale_de_sus_archivos(predictor, tmp_path):
    """RF-39: versión, algoritmo y métricas se leen de ml/models; cada predicción guarda una copia (ver pipeline/prediccion.py)."""
    assert predictor.ficha["version"] == "sintetico"
    assert modelo.leer_ficha(predictor.directorio)["version"] == "sintetico"
    assert modelo.leer_ficha(tmp_path / "no_hay_modelo") is None
    # Un modelo guardado antes de que `entrenamiento.json` trajera `version` recibe una derivada de su fecha de entrenamiento.
    ficha = modelo.describir({}, {"entrenado_en": "2026-11-02T03:57:55.607859+00:00"})
    assert ficha["version"] == "phl-xgb-20261102-0357" and ficha["algoritmo"] == modelo.ALGORITMO
