"""`crear_solicitud`: deja aislado, genoma, solicitud, historial y trabajo, y guarda el archivo con su SHA-256 como nombre (SQLite en memoria)."""
import hashlib

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models import Base, Centro, SolicitudHistorial, Trabajo, Usuario
from app.registro import crear_solicitud


@pytest.fixture()
def sesion():
    """Base SQLite en memoria con todas las tablas, nueva en cada prueba."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def fasta(tmp_path, nombre="Mi Genoma.fasta"):
    """Escribe un FASTA mínimo; el nombre lleva espacios a propósito para comprobar que no pasa a la ruta guardada."""
    ruta = tmp_path / nombre
    ruta.write_text(">c1\nACGTACGT\n", encoding="utf-8")
    return ruta


def test_crea_la_solicitud_con_su_trabajo_y_guarda_el_archivo_por_sha256(sesion, tmp_path):
    origen = fasta(tmp_path)
    destino = tmp_path / "genomas"
    sol = crear_solicitud(sesion, origen, "A", destino)
    esperado = hashlib.sha256(origen.read_bytes()).hexdigest()
    assert sol.estado == "registrada"
    archivos = list(destino.iterdir())
    assert [a.name for a in archivos] == [f"{esperado}.fasta"]  # sin espacios ni el nombre original
    trabajo = sesion.execute(select(Trabajo)).scalar_one()
    assert trabajo.tipo == "pipeline" and trabajo.solicitud_id == sol.id


def test_el_centro_y_usuario_de_demo_se_reutilizan(sesion, tmp_path):
    crear_solicitud(sesion, fasta(tmp_path), "A", tmp_path / "g")
    crear_solicitud(sesion, fasta(tmp_path), "B", tmp_path / "g")
    assert sesion.scalar(select(func.count()).select_from(Centro)) == 1
    assert sesion.scalar(select(func.count()).select_from(Usuario)) == 1


def test_la_solicitud_nace_registrada_con_su_primera_fila_de_historial(sesion, tmp_path):
    sol = crear_solicitud(sesion, fasta(tmp_path), "A", tmp_path / "g")
    historial = sesion.execute(select(SolicitudHistorial)).scalar_one()
    assert historial.solicitud_id == sol.id
    assert historial.estado_anterior is None and historial.estado_nuevo == "registrada"
