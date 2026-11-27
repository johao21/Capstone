"""Entrenamiento, validación y predicción del modelo de compatibilidad fago–hospedador (RF-34 a RF-40).

Cómo funciona, de punta a punta:

1. Cada fago se representa con los embeddings ESM-2 de sus proteínas de unión al receptor (RBP); cada hospedador, con el
   embedding ESM-2 de las proteínas de su locus K (los embeddings vienen precalculados en el conjunto PhageHostLearn).
2. XGBoost aprende, para un par (RBP, hospedador), la probabilidad de que el fago infecte a la cepa. La probabilidad de
   un fago sobre una cepa es la mayor de sus RBP (basta una RBP que reconozca la cápsula).
3. Un aislado nuevo no trae embeddings: se busca con BLAST a qué cepas de entrenamiento se parece el locus K de sus
   proteínas y se usa el embedding de esas cepas. Si ninguna se parece lo suficiente, el resultado se marca de baja
   confianza (RF-38).
4. SHAP explica cada candidato mostrado: qué características (RBP o locus K) empujaron el puntaje (RF-36).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .datos import ConjuntoPHL

# Un locus "está representado" si se parece al de alguna cepa de entrenamiento al menos en esta proporción (0 a 1).
UMBRAL_SIMILITUD = 0.90
# Para el embedding del hospedador se promedian las cepas más parecidas: las que quedan a este margen de la mejor, hasta MAX_VECINOS.
MARGEN_VECINOS = 0.02
MAX_VECINOS = 5

PARAMETROS_XGB = dict(
    n_estimators=300,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.3,
    min_child_weight=1,
    reg_lambda=1.0,
    tree_method="hist",
    n_jobs=4,
    random_state=7,
    eval_metric="logloss",
)
REFERENCIA = "Boeckaerts et al. (2024), Nature Communications, 10.1038/s41467-024-48675-6"


# --------------------------------------------------------------------------- entrenamiento
def _xgb(y: np.ndarray):
    from xgboost import XGBClassifier

    # Hay muchos más negativos que positivos (≈3 %): scale_pos_weight compensa el desbalance.
    peso = float((y == 0).sum()) / max(1.0, float((y == 1).sum()))
    return XGBClassifier(scale_pos_weight=peso, **PARAMETROS_XGB)


def filas(d: ConjuntoPHL, cepas: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Una fila por (cepa, RBP) cuyo fago fue ensayado con esa cepa. Devuelve (X, y, índice de cepa, índice de fago)."""
    j_de = {f: j for j, f in enumerate(d.fagos)}
    j_rbp = np.array([j_de[f] for f in d.rbp_fago])
    ks, ci, fj, y = [], [], [], []
    for i in cepas:
        etiqueta = d.etiquetas[i, j_rbp]
        k = np.nonzero(~np.isnan(etiqueta))[0]
        ks.append(k)
        ci.append(np.full(len(k), i))
        fj.append(j_rbp[k])
        y.append(etiqueta[k])
    ks, ci, fj, y = (np.concatenate(a) for a in (ks, ci, fj, y))
    X = np.hstack([d.rbp_emb[ks], d.emb_locus[ci]]).astype(np.float32)
    return X, y.astype(np.int8), ci, fj


def _maximo_por_par(ci: np.ndarray, fj: np.ndarray, puntaje: np.ndarray) -> dict[tuple[int, int], float]:
    mejor: dict[tuple[int, int], float] = {}
    for i, j, p in zip(ci.tolist(), fj.tolist(), puntaje.tolist()):
        if p > mejor.get((i, j), -1.0):
            mejor[(i, j)] = p
    return mejor


def grupos_por_locus(sim: np.ndarray, umbral: float = UMBRAL_SIMILITUD) -> np.ndarray:
    """Etiqueta de grupo de cada cepa: las de locus casi idéntico (similitud ≥ umbral) quedan juntas (componentes conexos).

    Sirven para validar sin filtración: un locus K nunca está a la vez en entrenamiento y en prueba."""
    n = len(sim)
    padre = list(range(n))

    def raiz(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if sim[i, j] >= umbral:
                padre[raiz(i)] = raiz(j)
    _, etiquetas = np.unique([raiz(i) for i in range(n)], return_inverse=True)
    return etiquetas


def metricas(d: ConjuntoPHL, puntajes: dict[tuple[int, int], float]) -> dict:
    """AUC, precisión media, acierto en el top-5 y sensibilidad/especificidad, sobre pares (cepa, fago) ensayados."""
    from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve

    pares = sorted(puntajes)
    y = np.array([d.etiquetas[i, j] for i, j in pares])
    s = np.array([puntajes[p] for p in pares])
    auc = float(roc_auc_score(y, s))
    fpr, tpr, umbrales = roc_curve(y, s)
    mejor = int(np.argmax(tpr - fpr))  # índice de Youden: mejor equilibrio entre sensibilidad y especificidad
    top5 = []
    azar = []
    for i in range(len(d.cepas)):
        ensayados = [j for (ii, j) in pares if ii == i]
        etiquetas = np.array([d.etiquetas[i, j] for j in ensayados])
        if len(ensayados) < 5 or etiquetas.sum() == 0:
            continue  # sin positivos no hay nada que acertar
        orden = np.argsort([-puntajes[(i, j)] for j in ensayados])[:5]
        top5.append(bool(etiquetas[orden].sum() > 0))
        n, p = len(ensayados), int(etiquetas.sum())
        azar.append(1.0 - float(np.prod([(n - p - k) / (n - k) for k in range(5)])) if n - p >= 5 else 1.0)
    return {
        "auc": round(auc, 4),
        "precision_media": round(float(average_precision_score(y, s)), 4),
        "top5": round(float(np.mean(top5)), 4) if top5 else None,
        "top5_azar": round(float(np.mean(azar)), 4) if azar else None,
        "cepas_evaluadas_top5": len(top5),
        "umbral_sugerido": round(float(umbrales[mejor]), 4),
        "sensibilidad": round(float(tpr[mejor]), 4),
        "especificidad": round(float(1 - fpr[mejor]), 4),
        "pares_evaluados": int(len(pares)),
        "pares_positivos": int(y.sum()),
    }


def validar(d: ConjuntoPHL, pliegues: int = 5, por: str = "locus") -> tuple[dict, dict[tuple[int, int], float]]:
    """Validación cruzada por grupos. `por="locus"`: ningún locus K parecido está a la vez en entrenamiento y prueba (el caso difícil,
    un aislado de un tipo K no visto); `por="cepa"`: solo se separa la cepa. También mide una línea base que ignora al hospedador.
    Devuelve (métricas, predicciones fuera de muestra por par (cepa, fago))."""
    from sklearn.model_selection import GroupKFold

    cepas = np.arange(len(d.cepas))
    grupos = grupos_por_locus(d.sim_locus) if por == "locus" else cepas
    puntajes: dict[tuple[int, int], float] = {}
    base: dict[tuple[int, int], float] = {}
    for entrenamiento, prueba in GroupKFold(n_splits=pliegues).split(cepas, groups=grupos):
        X, y, _, fj = filas(d, entrenamiento)
        modelo = _xgb(y).fit(X, y)
        Xp, _, ci_p, fj_p = filas(d, prueba)
        puntajes.update(_maximo_por_par(ci_p, fj_p, modelo.predict_proba(Xp)[:, 1]))
        # Línea base: la frecuencia con que cada fago infecta a las cepas de entrenamiento, sin mirar al hospedador.
        frecuencia = {j: float(y[fj == j].mean()) for j in np.unique(fj)}
        base.update({par: frecuencia.get(par[1], 0.0) for par in _maximo_por_par(ci_p, fj_p, np.zeros(len(ci_p)))})
    resultado = metricas(d, puntajes)
    resultado["linea_base_frecuencia_del_fago"] = {k: metricas(d, base)[k] for k in ("auc", "top5")}
    resultado["esquema"] = f"validación cruzada de {pliegues} pliegues agrupada por {'tipo de locus K (similitud ≥ %.2f)' % UMBRAL_SIMILITUD if por == 'locus' else 'cepa'}"
    return resultado, puntajes


def entrenar_final(d: ConjuntoPHL):
    """Modelo entrenado con todas las cepas y fagos."""
    X, y, _, _ = filas(d, np.arange(len(d.cepas)))
    return _xgb(y).fit(X, y), int(len(y))


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def calibrar(d: ConjuntoPHL, puntajes: dict[tuple[int, int], float]) -> dict:
    """Ajuste de Platt: convierte el puntaje del modelo en una probabilidad que coincide con la frecuencia observada.

    XGBoost se entrena con `scale_pos_weight` (los positivos pesan ~30 veces más), así que su salida cruda sobrestima la probabilidad
    real (los positivos son ≈3 %). Se ajusta una regresión logística sobre las predicciones fuera de muestra (validación por cepa)."""
    from sklearn.linear_model import LogisticRegression

    pares = sorted(puntajes)
    x = _logit([puntajes[p] for p in pares]).reshape(-1, 1)
    y = np.array([d.etiquetas[i, j] for i, j in pares])
    ajuste = LogisticRegression(C=1e6).fit(x, y)
    a, b = float(ajuste.coef_[0, 0]), float(ajuste.intercept_[0])
    calibradas = aplicar_calibracion({"a": a, "b": b}, np.array([puntajes[p] for p in pares]))
    return {"metodo": "Platt sobre predicciones fuera de muestra (validación por cepa)", "a": a, "b": b,
            "frecuencia_observada": round(float(y.mean()), 4), "probabilidad_media_calibrada": round(float(calibradas.mean()), 4)}


def aplicar_calibracion(calibracion: dict | None, puntaje):
    """Puntaje crudo -> probabilidad calibrada (sin calibración se devuelve igual)."""
    if not calibracion:
        return np.asarray(puntaje, dtype=float)
    z = calibracion["a"] * _logit(puntaje) + calibracion["b"]
    return 1.0 / (1.0 + np.exp(-z))


# ----------------------------------------------------------------------------- artefactos
ALGORITMO = "XGBoost sobre embeddings ESM-2 (RBP del fago + locus K del hospedador) con explicación SHAP"


def describir(metricas: dict, entrenamiento: dict) -> dict:
    """Ficha del modelo (RF-39): versión, algoritmo, fecha de entrenamiento, tamaño de los datos, métricas y parámetros.

    Sale de `metricas.json` y `entrenamiento.json`, los dos archivos que escribe `guardar`. Cada predicción guarda una copia de esta
    ficha, de modo que se sabe con qué modelo se hizo aunque después se entrene otra versión. Los modelos guardados antes de que
    `entrenamiento.json` trajera `version` reciben una derivada de su fecha de entrenamiento."""
    primaria = metricas.get("validacion_por_locus") or {}
    por_cepa = metricas.get("validacion_por_cepa") or {}
    entrenado_en = entrenamiento.get("entrenado_en") or datetime.now(timezone.utc).isoformat()
    calibracion = entrenamiento.get("calibracion")
    umbral = por_cepa.get("umbral_sugerido")
    return {
        "version": entrenamiento.get("version") or f"phl-xgb-{datetime.fromisoformat(entrenado_en):%Y%m%d-%H%M}",
        "algoritmo": entrenamiento.get("algoritmo") or ALGORITMO,
        "entrenado_en": entrenado_en,
        "n_entrenamiento": (metricas.get("datos") or {}).get("filas_de_entrenamiento"),
        # Métricas con el esquema de validación más exigente (aislado de un tipo K no visto) y, aparte, la validación por cepa.
        "metricas": {
            **{k: primaria.get(k) for k in ("top5", "top5_azar", "auc", "sensibilidad", "especificidad", "esquema", "linea_base_frecuencia_del_fago")},
            "validacion_por_cepa": {k: por_cepa.get(k) for k in ("auc", "top5", "top5_azar", "sensibilidad", "especificidad", "linea_base_frecuencia_del_fago")},
            "datos": metricas.get("datos"),
        },
        "parametros": {
            "xgboost": entrenamiento.get("parametros_xgboost"),
            "umbral_similitud_locus": entrenamiento.get("umbral_similitud_locus"),
            "umbral_candidato": round(float(aplicar_calibracion(calibracion, umbral)), 4) if umbral is not None else None,
            "calibracion": calibracion,
            "fuente": (entrenamiento.get("fuente") or {}).get("nombre"),
            "versiones": entrenamiento.get("versiones"),
        },
    }


def leer_ficha(directorio: Path | str) -> dict | None:
    """Ficha del modelo guardado en `directorio`, o None si todavía no hay un modelo entrenado."""
    carpeta = Path(directorio)
    try:
        metricas = json.loads((carpeta / "metricas.json").read_text(encoding="utf-8"))
        entrenamiento = json.loads((carpeta / "entrenamiento.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    return describir(metricas, entrenamiento)


def guardar(directorio: Path, d: ConjuntoPHL, modelo, resultados: dict, extra: dict) -> None:
    """Escribe el modelo y todo lo necesario para predecir sin volver a leer el conjunto original."""
    directorio.mkdir(parents=True, exist_ok=True)
    modelo.save_model(str(directorio / "modelo.json"))
    n_prot = np.array([len(d.proteinas_locus[c]) for c in d.cepas])
    np.savez_compressed(
        directorio / "representaciones.npz",
        cepas=np.array(d.cepas), emb_locus=d.emb_locus, fagos=np.array(d.fagos), rbp_ids=np.array(d.rbp_ids),
        rbp_fago=np.array(d.rbp_fago), rbp_emb=d.rbp_emb, etiquetas=d.etiquetas, n_prot=n_prot,
    )
    # Proteínas de los loci de entrenamiento: base de datos de BLAST para parecer-se-a (id: "<índice de cepa>|<n.º de proteína>").
    faa = directorio / "locus_proteinas.faa"
    with open(faa, "w", encoding="utf-8") as f:
        for i, c in enumerate(d.cepas):
            for k, secuencia in enumerate(d.proteinas_locus[c]):
                f.write(f">{i}|{k}\n{secuencia}\n")
    (directorio / "blastdb").mkdir(exist_ok=True)
    subprocess.run(["makeblastdb", "-in", str(faa), "-dbtype", "prot", "-out", str(directorio / "blastdb" / "locus")],
                   check=True, capture_output=True)
    (directorio / "metricas.json").write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    (directorio / "entrenamiento.json").write_text(json.dumps(extra, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------------------ predicción
@dataclass
class Vecindad:
    """A qué cepas de entrenamiento se parece el locus K del aislado."""

    similitud: np.ndarray  # una por cepa de entrenamiento
    mejor: float
    vecinos: list[int]  # las cepas cuyo embedding se promedia


class Predictor:
    """Modelo cargado desde `ml/models/`. Se construye una vez por proceso."""

    def __init__(self, directorio: Path | str):
        from xgboost import XGBClassifier

        self.directorio = Path(directorio)
        z = np.load(self.directorio / "representaciones.npz", allow_pickle=False)
        self.cepas = [str(c) for c in z["cepas"]]
        self.emb_locus = z["emb_locus"]
        self.fagos = [str(f) for f in z["fagos"]]
        self.rbp_ids = [str(r) for r in z["rbp_ids"]]
        self.rbp_fago = np.array([str(f) for f in z["rbp_fago"]])
        self.rbp_emb = z["rbp_emb"]
        self.etiquetas = z["etiquetas"]
        self.n_prot = z["n_prot"]
        self.modelo = XGBClassifier()
        self.modelo.load_model(str(self.directorio / "modelo.json"))
        self.metricas = json.loads((self.directorio / "metricas.json").read_text(encoding="utf-8"))
        self.entrenamiento = json.loads((self.directorio / "entrenamiento.json").read_text(encoding="utf-8"))
        self.calibracion = self.entrenamiento.get("calibracion")
        self.ficha = describir(self.metricas, self.entrenamiento)
        self._explicador = None

    # -- hospedador
    def similitud_locus(self, proteinas_faa: Path | str) -> np.ndarray:
        """Parecido (0 a 1) de las proteínas del aislado con el locus K de cada cepa de entrenamiento.

        Por cada proteína de locus se toma su mejor coincidencia en el aislado (identidad × cobertura) y se promedia por cepa;
        una proteína sin coincidencia aporta 0. Loci del mismo tipo K dan valores cercanos a 1; los de otro tipo, ≈0,5 (por los genes conservados)."""
        proceso = subprocess.run(
            ["blastp", "-query", str(proteinas_faa), "-db", str(self.directorio / "blastdb" / "locus"),
             "-outfmt", "6 sseqid pident length slen bitscore", "-evalue", "1e-5", "-max_target_seqs", "100000", "-num_threads", "2"],
            check=True, capture_output=True, text=True,
        )
        mejor: dict[str, tuple[float, float]] = {}
        for linea in proceso.stdout.splitlines():
            sseqid, pident, largo, slen, bits = linea.split("\t")
            valor = float(pident) / 100.0 * min(1.0, int(largo) / int(slen))
            if sseqid not in mejor or float(bits) > mejor[sseqid][1]:
                mejor[sseqid] = (valor, float(bits))
        suma = np.zeros(len(self.cepas))
        for sseqid, (valor, _) in mejor.items():
            suma[int(sseqid.split("|")[0])] += valor
        return suma / self.n_prot

    def vecindad(self, similitud: np.ndarray) -> Vecindad:
        mejor = float(similitud.max())
        orden = np.argsort(-similitud)[:MAX_VECINOS]
        vecinos = [int(i) for i in orden if similitud[i] >= mejor - MARGEN_VECINOS]
        return Vecindad(similitud=similitud, mejor=mejor, vecinos=vecinos)

    def vector_hospedador(self, v: Vecindad) -> np.ndarray:
        """Embedding del hospedador: promedio de las cepas más parecidas, ponderado por su similitud."""
        pesos = v.similitud[v.vecinos]
        return (pesos[:, None] * self.emb_locus[v.vecinos]).sum(axis=0) / pesos.sum()

    # -- predicción
    def _explicar(self, X: np.ndarray) -> list[dict]:
        import shap

        if self._explicador is None:
            self._explicador = shap.TreeExplainer(self.modelo)
        valores = np.asarray(self._explicador.shap_values(X))
        base = float(np.ravel(self._explicador.expected_value)[0])
        dims = self.rbp_emb.shape[1]
        salida = []
        for fila in valores:
            top = np.argsort(-np.abs(fila))[:6]
            salida.append({
                "metodo": "shap",
                "unidad": "log-odds",
                "valor_base": round(base, 4),
                "bloques": {"rbp_fago": round(float(fila[:dims].sum()), 4), "locus_k_hospedador": round(float(fila[dims:].sum()), 4)},
                "caracteristicas": [
                    {"nombre": ("RBP del fago · dim. %d" % k) if k < dims else ("Locus K · dim. %d" % (k - dims)),
                     "bloque": "rbp_fago" if k < dims else "locus_k_hospedador", "contribucion": round(float(fila[k]), 4)}
                    for k in top
                ],
            })
        return salida

    def _evidencia(self, v: Vecindad, j: int) -> dict | None:
        """Interacciones ya conocidas del fago con las cepas de entrenamiento de locus casi idéntico al del aislado."""
        parecidas = [int(i) for i in np.argsort(-v.similitud)[:20] if v.similitud[i] >= UMBRAL_SIMILITUD]
        if not parecidas:
            return None
        conocidas = self.etiquetas[parecidas, j]
        conocidas = conocidas[~np.isnan(conocidas)]
        if len(conocidas) == 0:
            return None
        return {"interacciones_positivas": int((conocidas == 1).sum()), "interacciones_negativas": int((conocidas == 0).sum()),
                "cepas_probadas": int(len(conocidas)), "referencias": [REFERENCIA]}

    def predecir(self, proteinas_faa: Path | str, n_explicados: int = 30) -> dict:
        """Ranking de todos los fagos del modelo para el aislado cuyas proteínas están en `proteinas_faa`."""
        v = self.vecindad(self.similitud_locus(proteinas_faa))
        host = self.vector_hospedador(v)
        X = np.hstack([self.rbp_emb, np.tile(host, (len(self.rbp_emb), 1))]).astype(np.float32)
        por_rbp = self.modelo.predict_proba(X)[:, 1]
        crudo = por_rbp  # el ranking y SHAP usan el puntaje crudo; el que se muestra es la probabilidad calibrada
        por_rbp = aplicar_calibracion(self.calibracion, por_rbp)
        ranking = []
        for j, fago in enumerate(self.fagos):
            filas_fago = np.nonzero(self.rbp_fago == fago)[0]
            k = int(filas_fago[np.argmax(crudo[filas_fago])])  # la RBP que mejor reconoce a este hospedador
            ranking.append({"fago": fago, "puntaje": float(por_rbp[k]), "fila": k, "j": j})
        ranking.sort(key=lambda r: -r["puntaje"])
        explicaciones = self._explicar(X[[r["fila"] for r in ranking[:n_explicados]]])
        for rango, r in enumerate(ranking, start=1):
            r["rango"] = rango
            explicacion = dict(explicaciones[rango - 1]) if rango <= n_explicados else {}
            if explicacion:
                explicacion["rbp"] = self.rbp_ids[r["fila"]]
            r["explicacion"] = explicacion
            r["evidencia"] = self._evidencia(v, r["j"])
        baja = v.mejor < UMBRAL_SIMILITUD
        return {
            "modelo": self.ficha,
            "baja_confianza": baja,
            "motivo_baja_confianza": (
                f"El locus K del aislado se parece como máximo un {v.mejor:.0%} al de las cepas de entrenamiento (se pide ≥ {UMBRAL_SIMILITUD:.0%}): "
                "su tipo K casi no está representado en los datos y el ranking es poco fiable."
            ) if baja else None,
            "similitud_maxima": round(v.mejor, 4),
            "cepas_similares": [{"cepa": self.cepas[i], "similitud": round(float(v.similitud[i]), 4)} for i in v.vecinos],
            "ranking": [{k: r[k] for k in ("fago", "puntaje", "rango", "explicacion", "evidencia")} for r in ranking],
        }
