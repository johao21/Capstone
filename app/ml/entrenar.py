"""Entrena y valida el modelo, guarda los artefactos y, si se pide, carga el banco de fagos en la base de datos (RF-31, RF-39, RF-40).

    python -m ml.entrenar                 # valida, entrena y escribe ml/models/
    python -m ml.entrenar --registrar     # además carga los fagos e interacciones conocidas al banco
    python -m ml.entrenar --registrar --sin-entrenar   # solo carga el banco, sin volver a entrenar

El modelo vigente son los artefactos de ml/models/ (no hay una tabla de modelos): `modelo.describir` arma su ficha y cada
predicción guarda una copia de la que usó (RF-39).

Es reproducible y fuera de línea: solo lee los archivos de `data/raw/phagehostlearn/` y fija las semillas (RF-40).
"""
from __future__ import annotations

import argparse
import hashlib
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import datos, modelo

DIRECTORIO_MODELOS = Path("ml/models")
FUENTE = "PhageHostLearn (Boeckaerts et al., 2024)"
VERSION_FUENTE = "Zenodo 11061100, v2"
URL_FUENTE = "https://doi.org/10.5281/zenodo.11061100"


def _coherencia_de_similitud(d: datos.ConjuntoPHL) -> float:
    """Comprueba que la matriz de similitud de loci sigue el orden de los embeddings.

    Los pares de loci casi idénticos (similitud ≥ 0,99) deben tener embeddings casi iguales; si la matriz estuviera en otro orden
    no ocurriría. Devuelve el menor coseno entre esos pares."""
    e = d.emb_locus / np.linalg.norm(d.emb_locus, axis=1, keepdims=True)
    coseno = e @ e.T
    iu = np.triu_indices(len(e), k=1)
    identicos = d.sim_locus[iu] >= 0.99
    return float(coseno[iu][identicos].min())


def _huella(carpeta: Path) -> dict[str, str]:
    return {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in sorted(carpeta.iterdir()) if p.is_file()}


def entrenar(carpeta_datos: Path, salida: Path) -> tuple[datos.ConjuntoPHL, dict, int]:
    inicio = time.time()
    d = datos.cargar(carpeta_datos)
    r = _coherencia_de_similitud(d)
    print(f"Cepas con locus: {len(d.cepas)} | fagos con RBP: {len(d.fagos)} | RBP: {len(d.rbp_ids)}")
    ensayados = d.etiquetas[~np.isnan(d.etiquetas)]
    print(f"Pares cepa-fago ensayados: {len(ensayados)} ({int(ensayados.sum())} positivos) | coseno mínimo entre loci idénticos: {r:.4f}")
    if r < 0.99:
        raise SystemExit("La matriz de similitud no sigue el orden de los embeddings: no se puede validar por tipo de locus K")

    print("Validación cruzada agrupada por tipo de locus K (aislado de un tipo K no visto)...")
    por_locus, _ = modelo.validar(d, por="locus")
    print("  ", {k: por_locus[k] for k in ("auc", "top5", "top5_azar", "sensibilidad", "especificidad")})
    print("Validación cruzada agrupada por cepa (el mismo tipo K puede estar en entrenamiento)...")
    por_cepa, oof_cepa = modelo.validar(d, por="cepa")
    calibracion = modelo.calibrar(d, oof_cepa)
    print("   calibración:", {k: calibracion[k] for k in ("frecuencia_observada", "probabilidad_media_calibrada")})
    print("  ", {k: por_cepa[k] for k in ("auc", "top5", "top5_azar", "sensibilidad", "especificidad")})

    print("Entrenando el modelo final...")
    final, n_filas = modelo.entrenar_final(d)
    import shap
    import sklearn
    import xgboost

    resultados = {"validacion_por_locus": por_locus, "validacion_por_cepa": por_cepa,
                  "datos": {"cepas": len(d.cepas), "fagos": len(d.fagos), "rbp": len(d.rbp_ids), "pares_ensayados": int(len(ensayados)),
                              "pares_positivos": int(ensayados.sum()), "filas_de_entrenamiento": n_filas}}
    entrenado_en = datetime.now(timezone.utc)
    extra = {
        "entrenado_en": entrenado_en.isoformat(),
        "version": f"phl-xgb-{entrenado_en:%Y%m%d-%H%M}",
        "algoritmo": modelo.ALGORITMO,
        "segundos": round(time.time() - inicio, 1),
        "fuente": {"nombre": FUENTE, "version": VERSION_FUENTE, "url": URL_FUENTE, "md5": _huella(carpeta_datos)},
        "parametros_xgboost": modelo.PARAMETROS_XGB,
        "calibracion": calibracion,
        "umbral_similitud_locus": modelo.UMBRAL_SIMILITUD,
        "versiones": {"python": platform.python_version(), "xgboost": xgboost.__version__, "shap": shap.__version__,
                      "scikit-learn": sklearn.__version__, "numpy": np.__version__},
    }
    modelo.guardar(salida, d, final, resultados, extra)
    print(f"Artefactos en {salida}")
    return d, {**resultados, **extra}, n_filas


def registrar(d: datos.ConjuntoPHL, carpeta_datos: Path) -> None:
    """Carga los fagos y las interacciones del conjunto al banco (RF-31). El modelo no se registra: son los artefactos de ml/models."""
    from sqlalchemy import select

    from app.db import get_sessionmaker
    from app.models import Fago, InteraccionConocida

    longitudes = datos.longitudes_de_genomas(carpeta_datos)
    descargado_en = datetime.now(timezone.utc).isoformat()
    with get_sessionmaker()() as s:
        ids: dict[str, object] = {}
        nuevos = 0
        for nombre in d.matriz_fagos:
            if nombre not in longitudes:  # sin genoma publicado no hay cómo incorporarlo al banco
                continue
            accesion = f"PHL-{nombre}"[:40]
            fago = s.scalar(select(Fago).where(Fago.accesion == accesion))
            if fago is None:
                fago = Fago(accesion=accesion, nombre=f"Klebsiella phage {nombre}", longitud_pb=longitudes[nombre],
                            hospedador_declarado="Klebsiella pneumoniae",
                            origenes=[{"fuente": FUENTE, "version": VERSION_FUENTE, "url": URL_FUENTE, "id_externo": nombre,
                                       "descargado_en": descargado_en}])
                s.add(fago)
                s.flush()
                nuevos += 1
            ids[nombre] = fago.id
        ya = s.scalar(select(InteraccionConocida.id).where(InteraccionConocida.fuente == FUENTE, InteraccionConocida.fuente_version == VERSION_FUENTE).limit(1))
        cargadas = 0
        if ya is None:
            for i, cepa in enumerate(d.matriz_cepas):
                for j, nombre in enumerate(d.matriz_fagos):
                    valor = d.matriz[i, j]
                    if nombre in ids and not np.isnan(valor):
                        s.add(InteraccionConocida(fago_id=ids[nombre], especie_hospedador="Klebsiella pneumoniae", cepa=cepa,
                                                  resultado="infecta" if valor == 1 else "no_infecta", fuente=FUENTE,
                                                  fuente_version=VERSION_FUENTE, referencia=modelo.REFERENCIA))
                        cargadas += 1
        s.commit()
    print(f"Banco cargado | fagos nuevos: {nuevos} | interacciones cargadas: {cargadas}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Entrena y valida el modelo de compatibilidad fago-hospedador")
    ap.add_argument("--datos", type=Path, default=datos.CARPETA_POR_DEFECTO, help="carpeta con el conjunto PhageHostLearn")
    ap.add_argument("--salida", type=Path, default=DIRECTORIO_MODELOS, help="carpeta de los artefactos del modelo")
    ap.add_argument("--registrar", action="store_true", help="carga los fagos y las interacciones conocidas en la base de datos")
    ap.add_argument("--sin-entrenar", action="store_true", help="no entrena: solo carga el banco (con --registrar)")
    args = ap.parse_args(argv)
    if args.sin_entrenar:
        if not args.registrar:
            ap.error("--sin-entrenar solo tiene sentido con --registrar")
        registrar(datos.cargar(args.datos), args.datos)
        return 0
    d, _, _ = entrenar(args.datos, args.salida)
    if args.registrar:
        registrar(d, args.datos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
