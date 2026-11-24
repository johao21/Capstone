"""Cola de trabajos y procesamiento de una solicitud, con herramientas falsas (SQLite en memoria).

Limitación: SQLite no implementa `FOR UPDATE SKIP LOCKED`, así que estas pruebas no demuestran que dos workers
simultáneos no tomen el mismo trabajo. Esa garantía depende de PostgreSQL y hoy no tiene prueba automática.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.estados import TRANSICIONES, TransicionInvalida, cambiar_estado
from app.models import (
    AnalisisGenomico,
    Aislado,
    Base,
    Centro,
    Genoma,
    Solicitud,
    SolicitudHistorial,
    Trabajo,
    Usuario,
)
from pipeline.especie import ResultadoEspecie
from pipeline.genes import ResultadoGenes
from pipeline.herramientas import ErrorHerramienta
from pipeline.locus_k import ResultadoLocusK
from pipeline.qc import Umbrales
from pipeline.trabajos import MAX_INTENTOS, Pasos, procesar_pipeline, reclamar, registrar_fallo_inesperado

# Umbrales reducidos para que los FASTA de prueba (cientos de pb) pasen el control de calidad.
UMBRALES = Umbrales(
    longitud_min_rechazo=100,
    longitud_max_rechazo=5000,
    longitud_min_advertencia=200,
    longitud_max_advertencia=4000,
    contigs_max_rechazo=50,
    contigs_max_advertencia=10,
    n50_min_advertencia=50,
)


@pytest.fixture()
def sesion():
    """Base SQLite en memoria con todas las tablas, nueva en cada prueba."""
    engine = create_engine("sqlite://")

    # SQLite solo hace cumplir las claves foráneas si se activan en cada conexión (PostgreSQL siempre lo hace).
    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def crear_solicitud(s: Session, tmp_path, contenido=">c1\n" + "ACGT" * 100 + "\n>c2\n" + "GGCC" * 50 + "\n"):
    """Deja en la base una solicitud Registrada con su trabajo `pipeline` y un FASTA en disco (2 contigs, 600 pb). Devuelve (solicitud, trabajo)."""
    ruta = tmp_path / "g.fasta"
    ruta.write_text(contenido, encoding="utf-8")
    centro = Centro(codigo="C1", nombre="Centro")
    s.add(centro)
    s.flush()
    usuario = Usuario(correo="t@x.cl", nombre="T", password_hash="x", rol="TEC", centro_id=centro.id)
    s.add(usuario)
    s.flush()
    aislado = Aislado(
        codigo_interno="A1",
        centro_id=centro.id,
        fecha_aislamiento=date(2026, 9, 1),
        especie_declarada="Klebsiella pneumoniae",
        tipo_muestra="sangre",
        creado_por=usuario.id,
    )
    s.add(aislado)
    s.flush()
    genoma = Genoma(aislado_id=aislado.id, ruta_archivo=str(ruta), sha256="b" * 64, tamano_bytes=1, nombre_original="g.fasta")
    s.add(genoma)
    s.flush()
    sol = Solicitud(
        aislado_id=aislado.id, genoma_id=genoma.id, centro_id=centro.id, solicitante_id=usuario.id, creada_por=usuario.id
    )
    s.add(sol)
    s.flush()
    trabajo = Trabajo(tipo="pipeline", solicitud_id=sol.id)
    s.add(trabajo)
    s.flush()
    return sol, trabajo


def pasos_falsos(especie="Klebsiella pneumoniae", falla_en=None):
    """Herramientas falsas con resultados fijos. `falla_en` ("especie", "locus_k" o "genes") hace que ese paso lance ErrorHerramienta; lo que se "guarda" en Mongo queda en `pasos.guardados`."""
    guardados: list[dict] = []

    def esp(ruta, declarada):
        if falla_en == "especie":
            raise ErrorHerramienta("mash no disponible")
        return ResultadoEspecie(especie=especie, distancia=0.01, verificada=True)

    def locus(ruta, carpeta):
        if falla_en == "locus_k":
            raise ErrorHerramienta("kaptive falló")
        return ResultadoLocusK(tipo="KL2", confianza="Good", detalle={"x": 1})

    def genes(ruta, carpeta):
        if falla_en == "genes":
            raise ErrorHerramienta("prodigal falló")
        return ResultadoGenes(n_genes=5100, n_proteinas=5100, ruta_proteinas="/x/proteinas.faa")

    def guardar(doc):
        guardados.append(doc)
        return "64f000000000000000000001"

    pasos = Pasos(especie=esp, locus_k=locus, genes=genes, guardar_crudo=guardar, versiones=lambda: {"prodigal": "2.6.3"})
    pasos.guardados = guardados  # type: ignore[attr-defined]
    return pasos


# ------------------------------------------------------------------ estados
def test_transiciones_permitidas_y_prohibidas(sesion, tmp_path):
    sol, _ = crear_solicitud(sesion, tmp_path)
    with pytest.raises(TransicionInvalida):
        cambiar_estado(sesion, sol, "emitida")
    cambiar_estado(sesion, sol, "en_analisis")
    assert sol.estado == "en_analisis"


def test_los_estados_finales_no_tienen_salida():
    for final in ("rechazada", "anulada", "cerrada"):
        assert TRANSICIONES[final] == set()


def test_cada_cambio_deja_historial(sesion, tmp_path):
    sol, _ = crear_solicitud(sesion, tmp_path)
    cambiar_estado(sesion, sol, "en_analisis")
    cambiar_estado(sesion, sol, "rechazada", motivo="prueba")
    sesion.flush()
    filas = sesion.execute(select(SolicitudHistorial).where(SolicitudHistorial.solicitud_id == sol.id)).scalars().all()
    assert [(f.estado_anterior, f.estado_nuevo) for f in filas] == [("registrada", "en_analisis"), ("en_analisis", "rechazada")]


# --------------------------------------------------------------------- cola
# SQLite ignora FOR UPDATE SKIP LOCKED: estas pruebas verifican la selección (orden, tipo, espera), no la exclusión entre dos
# workers simultáneos, que solo puede comprobarse con PostgreSQL.
def test_reclamar_toma_el_trabajo_y_lo_marca_en_curso(sesion, tmp_path):
    _, trabajo = crear_solicitud(sesion, tmp_path)
    tomado = reclamar(sesion, "pipeline", "worker-1")
    assert tomado.id == trabajo.id
    assert (tomado.estado, tomado.intentos, tomado.bloqueado_por) == ("en_curso", 1, "worker-1")
    # Ya no está pendiente, así que un segundo worker no lo recibe.
    assert reclamar(sesion, "pipeline", "worker-2") is None


def test_reclamar_ignora_otros_tipos_y_los_que_esperan(sesion, tmp_path):
    _, trabajo = crear_solicitud(sesion, tmp_path)
    assert reclamar(sesion, "prediccion", "w") is None
    trabajo.siguiente_intento_en = datetime.now(timezone.utc) + timedelta(hours=1)
    sesion.flush()
    assert reclamar(sesion, "pipeline", "w") is None


# --------------------------------------------------------------- pipeline
def test_caso_feliz_guarda_analisis_y_encola_prediccion(sesion, tmp_path):
    sol, _ = crear_solicitud(sesion, tmp_path)
    pasos = pasos_falsos()
    trabajo = reclamar(sesion, "pipeline", "w")
    procesar_pipeline(sesion, trabajo, pasos, UMBRALES, salida=tmp_path / "analisis")
    sesion.flush()

    assert trabajo.estado == "ok"
    assert sol.estado == "en_analisis"
    analisis = sesion.execute(select(AnalisisGenomico)).scalar_one()
    assert (analisis.especie_detectada, analisis.locus_k_tipo, analisis.n_genes) == ("Klebsiella pneumoniae", "KL2", 5100)
    assert analisis.mongo_id == "64f000000000000000000001"
    assert analisis.versiones_herramientas == {"prodigal": "2.6.3"}
    siguiente = sesion.execute(select(Trabajo).where(Trabajo.tipo == "prediccion")).scalar_one()
    assert siguiente.solicitud_id == sol.id and siguiente.estado == "pendiente"
    genoma = sesion.get(Genoma, sol.genoma_id)
    assert genoma.qc_resultado in ("aprobado", "advertencia") and genoma.qc_longitud == 600
    assert pasos.guardados[0]["locus_k"]["tipo"] == "KL2"


def test_calidad_rechazada_rechaza_la_solicitud(sesion, tmp_path):
    sol, _ = crear_solicitud(sesion, tmp_path)
    trabajo = reclamar(sesion, "pipeline", "w")
    estricto = Umbrales(longitud_min_rechazo=1_000_000)
    procesar_pipeline(sesion, trabajo, pasos_falsos(), estricto, salida=tmp_path / "a")
    assert sol.estado == "rechazada"
    assert "calidad" in sol.motivo_estado
    assert trabajo.estado == "ok"
    assert sesion.execute(select(AnalisisGenomico)).first() is None


def test_especie_distinta_rechaza_la_solicitud(sesion, tmp_path):
    sol, _ = crear_solicitud(sesion, tmp_path)
    trabajo = reclamar(sesion, "pipeline", "w")
    procesar_pipeline(sesion, trabajo, pasos_falsos(especie="Escherichia coli"), UMBRALES, salida=tmp_path / "a")
    assert sol.estado == "rechazada"
    assert "Escherichia coli" in sol.motivo_estado


def test_el_rechazo_por_especie_informa_la_distancia_y_la_referencia(sesion, tmp_path):
    sol, _ = crear_solicitud(sesion, tmp_path)
    pasos = pasos_falsos()
    pasos.especie = lambda ruta, declarada: ResultadoEspecie(
        especie="Klebsiella variicola", distancia=0.0093, verificada=True, referencia="GCF_020525545.1.fna.gz"
    )
    trabajo = reclamar(sesion, "pipeline", "w")
    procesar_pipeline(sesion, trabajo, pasos, UMBRALES, salida=tmp_path / "a")
    assert sol.estado == "rechazada"
    assert "Klebsiella variicola" in sol.motivo_estado
    assert "Mash 0.0093 a GCF_020525545.1.fna.gz" in sol.motivo_estado


def test_especie_ambigua_se_rechaza_con_el_motivo(sesion, tmp_path):
    sol, _ = crear_solicitud(sesion, tmp_path)
    pasos = pasos_falsos()
    pasos.especie = lambda ruta, declarada: ResultadoEspecie(
        especie=None, distancia=0.030, verificada=True, referencia="a.fna.gz", motivo="ambigua entre X (0.0300) y Y (0.0320)"
    )
    trabajo = reclamar(sesion, "pipeline", "w")
    procesar_pipeline(sesion, trabajo, pasos, UMBRALES, salida=tmp_path / "a")
    assert sol.estado == "rechazada" and "ambigua" in sol.motivo_estado and "no identificada" in sol.motivo_estado


def test_fasta_invalido_rechaza_la_solicitud(sesion, tmp_path):
    sol, _ = crear_solicitud(sesion, tmp_path, contenido="esto no es fasta\n")
    trabajo = reclamar(sesion, "pipeline", "w")
    procesar_pipeline(sesion, trabajo, pasos_falsos(), UMBRALES, salida=tmp_path / "a")
    assert sol.estado == "rechazada"
    assert "FASTA inválido" in sol.motivo_estado


def test_falla_de_herramienta_reintenta_y_al_tercer_intento_pasa_a_error(sesion, tmp_path):
    sol, trabajo = crear_solicitud(sesion, tmp_path)
    # Se reclama con una hora futura para saltarse la espera entre reintentos.
    futuro = datetime.now(timezone.utc) + timedelta(days=1)

    for intento in range(1, MAX_INTENTOS + 1):
        t = reclamar(sesion, "pipeline", "w", ahora=futuro)
        assert t is not None and t.intentos == intento
        procesar_pipeline(sesion, t, pasos_falsos(falla_en="genes"), UMBRALES, salida=tmp_path / "a")
        if intento < MAX_INTENTOS:
            assert t.estado == "pendiente" and "prodigal" in t.error
            assert sol.estado == "en_analisis"

    assert trabajo.estado == "fallido"
    assert sol.estado == "error"
    assert sesion.execute(select(AnalisisGenomico)).first() is None


def test_solicitud_en_error_vuelve_a_en_analisis_al_reintentar(sesion, tmp_path):
    sol, _ = crear_solicitud(sesion, tmp_path)
    cambiar_estado(sesion, sol, "en_analisis")
    cambiar_estado(sesion, sol, "error", motivo="falla previa")
    t = reclamar(sesion, "pipeline", "w")
    procesar_pipeline(sesion, t, pasos_falsos(), UMBRALES, salida=tmp_path / "a")
    assert sol.estado == "en_analisis"
    assert t.estado == "ok"


def test_fallo_inesperado_deja_la_solicitud_en_error_para_poder_reintentar(sesion, tmp_path):
    sol, trabajo = crear_solicitud(sesion, tmp_path)

    registrar_fallo_inesperado(sesion, trabajo.id, "error inesperado: mongo caído")

    assert trabajo.estado == "fallido"
    assert trabajo.error == "error inesperado: mongo caído"
    assert sol.estado == "error"  # desde `error` el botón "Reintentar" la acepta
    historial = sesion.scalars(select(SolicitudHistorial).where(SolicitudHistorial.solicitud_id == sol.id)).all()
    assert {(h.estado_anterior, h.estado_nuevo) for h in historial} == {("registrada", "en_analisis"), ("en_analisis", "error")}


def test_fallo_inesperado_no_cambia_una_solicitud_anulada(sesion, tmp_path):
    sol, trabajo = crear_solicitud(sesion, tmp_path)
    cambiar_estado(sesion, sol, "anulada")

    registrar_fallo_inesperado(sesion, trabajo.id, "error inesperado")

    assert trabajo.estado == "fallido"
    assert sol.estado == "anulada"
