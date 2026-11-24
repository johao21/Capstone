"""Procesamiento de un trabajo de predicción con un modelo falso (SQLite en memoria): ranking, filtro por fagos aprobados,
alertas, auditoría y cada camino de fallo (RF-34, RF-35, RF-33, RF-64)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.estados import cambiar_estado
from app.models import (
    Alerta,
    AnalisisGenomico,
    Auditoria,
    Fago,
    ModeloPrediccion,
    Prediccion,
    PrediccionFago,
    Trabajo,
    Usuario,
)
from app.registro import crear_solicitud
from pipeline.herramientas import ErrorHerramienta
from pipeline.prediccion import procesar_prediccion
from pipeline.trabajos import MAX_INTENTOS, reclamar

FASTA = ">c\nACGTACGTACGTACGT\n"


@pytest.fixture()
def sesion(engine):
    with Session(engine) as s:
        yield s


def solicitud_analizada(s, tmp_path, con_proteinas=True):
    """Una solicitud en `en_analisis` con su análisis genómico, su archivo de proteínas y un trabajo `prediccion` pendiente."""
    fasta = tmp_path / "g.fasta"
    fasta.write_text(FASTA, encoding="utf-8")
    sol = crear_solicitud(s, fasta, "P-1", tmp_path / "genomas")
    cambiar_estado(s, sol, "en_analisis")
    s.add(AnalisisGenomico(solicitud_id=sol.id, especie_detectada="Klebsiella pneumoniae", locus_k_tipo="KL2", locus_k_confianza="Good"))
    trabajo = Trabajo(tipo="prediccion", solicitud_id=sol.id)
    s.add(trabajo)
    s.flush()
    if con_proteinas:
        carpeta = tmp_path / "analisis" / str(sol.id) / "genes"
        carpeta.mkdir(parents=True)
        (carpeta / "proteinas.faa").write_text(">p\nMKV\n", encoding="utf-8")
    return sol, trabajo


def modelo_activo(s, version="phl-prueba"):
    m = ModeloPrediccion(version=version, algoritmo="XGBoost (prueba)", metricas={"top5": 0.9}, activo=True)
    s.add(m)
    s.flush()
    return m


def fago(s, nombre, estado="aprobado"):
    f = Fago(accesion=f"PHL-{nombre}", nombre=f"Klebsiella phage {nombre}", estado_curaduria=estado)
    s.add(f)
    s.flush()
    return f


def ranking_falso(*nombres_y_puntajes, baja=False):
    """Función `predecir` falsa: devuelve el ranking dado, sin mirar las proteínas."""
    def predecir(ruta):
        assert ruta.name == "proteinas.faa"
        return {
            "baja_confianza": baja, "motivo_baja_confianza": "locus poco representado" if baja else None, "similitud_maxima": 0.95,
            "cepas_similares": [{"cepa": "KP_1", "similitud": 0.95}],
            "ranking": [{"fago": n, "puntaje": p, "rango": i, "explicacion": {"metodo": "shap"},
                         "evidencia": {"interacciones_positivas": 2, "interacciones_negativas": 1, "cepas_probadas": 3, "referencias": ["ref"]} if n == "A" else None}
                        for i, (n, p) in enumerate(nombres_y_puntajes, start=1)],
        }
    return predecir


def correr(s, trabajo, predecir, tmp_path):
    t = reclamar(s, "prediccion", "w", ahora=datetime.now(timezone.utc) + timedelta(days=1))
    assert t is not None and t.id == trabajo.id
    procesar_prediccion(s, t, predecir, salida=tmp_path / "analisis")
    return t


def test_deja_el_ranking_solo_con_los_fagos_aprobados_y_la_solicitud_lista(sesion, tmp_path):
    sol, trabajo = solicitud_analizada(sesion, tmp_path)
    modelo = modelo_activo(sesion)
    aprobado_a, aprobado_b = fago(sesion, "A"), fago(sesion, "B")
    fago(sesion, "C", estado="pendiente")  # el modelo lo conoce, pero nadie lo aprobó
    mic = Usuario(correo="m@x.cl", nombre="M", password_hash="x", rol="MIC", centro_id=sol.centro_id)
    sesion.add(mic)
    sesion.flush()

    t = correr(sesion, trabajo, ranking_falso(("C", 0.99), ("A", 0.8), ("B", 0.4)), tmp_path)

    assert t.estado == "ok" and sol.estado == "prediccion_lista"
    pred = sesion.scalars(select(Prediccion)).one()
    assert pred.modelo_id == modelo.id and pred.locus_k_tipo == "KL2" and pred.baja_confianza is False
    assert pred.detalle["fagos_en_el_modelo"] == 3 and pred.detalle["fagos_aprobados"] == 2
    items = sesion.scalars(select(PrediccionFago).order_by(PrediccionFago.rango)).all()
    assert [(i.fago_id, i.rango) for i in items] == [(aprobado_a.id, 1), (aprobado_b.id, 2)]  # el rango se recalcula entre los aprobados
    assert items[0].explicacion["metodo"] == "shap" and items[0].explicacion["evidencia"]["interacciones_positivas"] == 2
    # RF-48: queda el evento con la versión del modelo; RF-64: se avisa a los microbiólogos.
    evento = sesion.scalars(select(Auditoria).where(Auditoria.accion == "prediccion_generada")).one()
    assert evento.modelo_version == "phl-prueba" and evento.rol == "SIS"
    sesion.commit()
    assert [a.usuario_id for a in sesion.scalars(select(Alerta).where(Alerta.tipo == "prediccion_lista"))] == [mic.id]


def test_una_prediccion_de_baja_confianza_queda_marcada(sesion, tmp_path):
    _, trabajo = solicitud_analizada(sesion, tmp_path)
    modelo_activo(sesion)
    fago(sesion, "A")
    correr(sesion, trabajo, ranking_falso(("A", 0.5), baja=True), tmp_path)
    pred = sesion.scalars(select(Prediccion)).one()
    assert pred.baja_confianza is True and pred.motivo_baja_confianza == "locus poco representado"


@pytest.mark.parametrize(
    "preparar, texto",
    [
        ("sin_modelo", "No hay un modelo entrenado"),
        ("sin_aprobados", "No hay fagos aprobados"),
        ("sin_proteinas", "No se encuentran las proteínas"),
    ],
)
def test_si_falta_algo_la_solicitud_pasa_a_error_con_el_motivo_sin_reintentos(sesion, tmp_path, preparar, texto):
    sol, trabajo = solicitud_analizada(sesion, tmp_path, con_proteinas=preparar != "sin_proteinas")
    if preparar != "sin_modelo":
        modelo_activo(sesion)
    if preparar == "sin_aprobados":
        fago(sesion, "A", estado="pendiente")
    t = correr(sesion, trabajo, ranking_falso(("A", 0.9)), tmp_path)
    assert t.estado == "fallido" and texto in t.error
    assert sol.estado == "error" and texto in sol.motivo_estado
    assert sesion.scalars(select(Prediccion)).first() is None  # no queda un ranking a medias


def test_una_herramienta_caida_se_reintenta_y_al_tercer_intento_falla(sesion, tmp_path):
    sol, _ = solicitud_analizada(sesion, tmp_path)
    modelo_activo(sesion)
    fago(sesion, "A")

    def cae(ruta):
        raise ErrorHerramienta("blastp falló")

    futuro = datetime.now(timezone.utc) + timedelta(days=1)
    for intento in range(1, MAX_INTENTOS + 1):
        t = reclamar(sesion, "prediccion", "w", ahora=futuro)
        assert t.intentos == intento
        procesar_prediccion(sesion, t, cae, salida=tmp_path / "analisis")
        if intento < MAX_INTENTOS:
            assert t.estado == "pendiente" and sol.estado == "en_analisis"
    assert t.estado == "fallido" and sol.estado == "error" and "blastp" in sol.motivo_estado


def test_un_reintento_manual_desde_error_vuelve_a_predecir(sesion, tmp_path):
    sol, trabajo = solicitud_analizada(sesion, tmp_path)
    cambiar_estado(sesion, sol, "error", motivo="falla previa")
    modelo_activo(sesion)
    fago(sesion, "A")
    correr(sesion, trabajo, ranking_falso(("A", 0.7)), tmp_path)
    assert sol.estado == "prediccion_lista"


def test_una_solicitud_anulada_no_se_predice(sesion, tmp_path):
    sol, trabajo = solicitud_analizada(sesion, tmp_path)
    cambiar_estado(sesion, sol, "anulada", motivo="duplicada")
    t = correr(sesion, trabajo, ranking_falso(("A", 0.7)), tmp_path)
    assert t.estado == "fallido" and "anulada" in t.error and sol.estado == "anulada"
    assert sesion.scalars(select(Prediccion)).first() is None
