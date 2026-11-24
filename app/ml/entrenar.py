"""Entrena y valida el modelo, guarda los artefactos y, si se pide, los registra en la base de datos (RF-31, RF-39, RF-40).

    python -m ml.entrenar                 # valida, entrena y escribe ml/models/
    python -m ml.entrenar --registrar     # además carga los fagos e interacciones al banco y registra el modelo vigente
    python -m ml.entrenar --registrar --sin-entrenar   # registra los artefactos que ya están en ml/models, sin volver a entrenar

Es reproducible y fuera de línea: solo lee los archivos de `data/raw/phagehostlearn/` y fija las semillas (RF-40).
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
    extra = {
        "entrenado_en": datetime.now(timezone.utc).isoformat(),
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


def registrar(d: datos.ConjuntoPHL, info: dict, n_filas: int, carpeta_datos: Path) -> None:
    """Carga los fagos y las interacciones del conjunto al banco (RF-31) y deja este modelo como el vigente."""
    from sqlalchemy import select, update

    from app.db import get_sessionmaker
    from app.models import Fago, FagoOrigen, FuenteDatos, InteraccionConocida, ModeloPrediccion

    longitudes = datos.longitudes_de_genomas(carpeta_datos)
    with get_sessionmaker()() as s:
        fuente = s.scalar(select(FuenteDatos).where(FuenteDatos.nombre == FUENTE, FuenteDatos.version == VERSION_FUENTE))
        if fuente is None:
            fuente = FuenteDatos(nombre=FUENTE, version=VERSION_FUENTE, url=URL_FUENTE)
            s.add(fuente)
            s.flush()
        ids: dict[str, object] = {}
        nuevos = 0
        for nombre in d.matriz_fagos:
            if nombre not in longitudes:  # sin genoma publicado no hay cómo incorporarlo al banco
                continue
            accesion = f"PHL-{nombre}"[:40]
            fago = s.scalar(select(Fago).where(Fago.accesion == accesion))
            if fago is None:
                fago = Fago(accesion=accesion, nombre=f"Klebsiella phage {nombre}", longitud_pb=longitudes[nombre],
                            hospedador_declarado="Klebsiella pneumoniae")
                s.add(fago)
                s.flush()
                s.add(FagoOrigen(fago_id=fago.id, fuente_id=fuente.id, id_externo=nombre, version_origen=VERSION_FUENTE))
                nuevos += 1
            ids[nombre] = fago.id
        ya = s.scalar(select(InteraccionConocida.id).where(InteraccionConocida.fuente_id == fuente.id).limit(1))
        cargadas = 0
        if ya is None:
            for i, cepa in enumerate(d.matriz_cepas):
                for j, nombre in enumerate(d.matriz_fagos):
                    valor = d.matriz[i, j]
                    if nombre in ids and not np.isnan(valor):
                        s.add(InteraccionConocida(fago_id=ids[nombre], especie_hospedador="Klebsiella pneumoniae", cepa=cepa,
                                                  resultado="infecta" if valor == 1 else "no_infecta", fuente_id=fuente.id,
                                                  referencia=modelo.REFERENCIA))
                        cargadas += 1
        base = f"phl-xgb-{datetime.now(timezone.utc):%Y%m%d}"
        version, n = base, 1
        while s.scalar(select(ModeloPrediccion.id).where(ModeloPrediccion.version == version)):
            n += 1
            version = f"{base}-{n}"
        primaria = info["validacion_por_locus"]
        s.execute(update(ModeloPrediccion).values(activo=False))
        s.add(ModeloPrediccion(
            version=version, algoritmo="XGBoost sobre embeddings ESM-2 (RBP del fago + locus K del hospedador) con explicación SHAP",
            entrenado_en=datetime.fromisoformat(info["entrenado_en"]), n_entrenamiento=n_filas,
            metricas={"top5": primaria["top5"], "top5_azar": primaria["top5_azar"], "auc": primaria["auc"], "sensibilidad": primaria["sensibilidad"],
                      "especificidad": primaria["especificidad"], "esquema": primaria["esquema"],
                      "linea_base_frecuencia_del_fago": primaria["linea_base_frecuencia_del_fago"],
                      "validacion_por_cepa": {k: info["validacion_por_cepa"][k] for k in ("auc", "top5", "top5_azar", "sensibilidad", "especificidad", "linea_base_frecuencia_del_fago")},
                      "datos": info["datos"]},
            parametros={"xgboost": info["parametros_xgboost"], "umbral_similitud_locus": info["umbral_similitud_locus"],
                        "umbral_candidato": round(float(modelo.aplicar_calibracion(info.get("calibracion"), info["validacion_por_cepa"]["umbral_sugerido"])), 4),
                        "calibracion": info.get("calibracion"), "fuente": info["fuente"]["nombre"], "versiones": info["versiones"]},
            ruta_artefacto=str(DIRECTORIO_MODELOS), activo=True))
        s.commit()
    print(f"Registrado: modelo {version} | fagos nuevos en el banco: {nuevos} | interacciones cargadas: {cargadas}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Entrena y valida el modelo de compatibilidad fago-hospedador")
    ap.add_argument("--datos", type=Path, default=datos.CARPETA_POR_DEFECTO, help="carpeta con el conjunto PhageHostLearn")
    ap.add_argument("--salida", type=Path, default=DIRECTORIO_MODELOS, help="carpeta de los artefactos del modelo")
    ap.add_argument("--registrar", action="store_true", help="carga el banco y registra el modelo en la base de datos")
    ap.add_argument("--sin-entrenar", action="store_true", help="usa los artefactos ya guardados en --salida (con --registrar)")
    args = ap.parse_args(argv)
    if args.sin_entrenar:
        if not args.registrar:
            ap.error("--sin-entrenar solo tiene sentido con --registrar")
        resultados = json.loads((args.salida / "metricas.json").read_text(encoding="utf-8"))
        info = {**resultados, **json.loads((args.salida / "entrenamiento.json").read_text(encoding="utf-8"))}
        registrar(datos.cargar(args.datos), info, resultados["datos"]["filas_de_entrenamiento"], args.datos)
        return 0
    d, info, n_filas = entrenar(args.datos, args.salida)
    if args.registrar:
        registrar(d, info, n_filas, args.datos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
