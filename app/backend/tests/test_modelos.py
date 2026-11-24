"""El esquema se crea completo y respeta sus restricciones (SQLite en memoria)."""
from datetime import date

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Aislado, Base, Centro, Fago, Genoma, Solicitud, Usuario

TABLAS_ESPERADAS = {
    "centro",
    "usuario",
    "aislado",
    "genoma",
    "solicitud",
    "solicitud_historial",
    "trabajo",
    "analisis_genomico",
    "fuente_datos",
    "fago",
    "fago_origen",
    "interaccion_conocida",
    # Migración 0002: sesiones, auditoría, alertas, predicción y recomendaciones emitidas.
    "sesion_revocada",
    "auditoria",
    "alerta",
    "modelo_prediccion",
    "prediccion",
    "prediccion_fago",
    "recomendacion_emitida",
    "recomendacion_candidato",
}


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


def crear_base(s: Session):
    """Crea lo mínimo que necesita una solicitud: centro, usuario, aislado y genoma. Devuelve (centro, usuario, aislado, genoma)."""
    centro = Centro(codigo="C1", nombre="Centro de prueba")
    s.add(centro)
    s.flush()
    usuario = Usuario(correo="t@x.cl", nombre="Tec", password_hash="x", rol="TEC", centro_id=centro.id)
    s.add(usuario)
    s.flush()
    aislado = Aislado(
        codigo_interno="A-001",
        centro_id=centro.id,
        fecha_aislamiento=date(2026, 9, 1),
        especie_declarada="Klebsiella pneumoniae",
        tipo_muestra="sangre",
        creado_por=usuario.id,
    )
    s.add(aislado)
    s.flush()
    genoma = Genoma(aislado_id=aislado.id, ruta_archivo="/data/g.fasta", sha256="a" * 64, tamano_bytes=10, nombre_original="g.fasta")
    s.add(genoma)
    s.flush()
    return centro, usuario, aislado, genoma


def test_se_crean_todas_las_tablas():
    assert set(Base.metadata.tables) == TABLAS_ESPERADAS


def test_solicitud_nace_registrada(sesion):
    centro, usuario, aislado, genoma = crear_base(sesion)
    sol = Solicitud(
        aislado_id=aislado.id, genoma_id=genoma.id, centro_id=centro.id, solicitante_id=usuario.id, creada_por=usuario.id
    )
    sesion.add(sol)
    sesion.flush()
    assert sol.estado == "registrada"


def test_estado_invalido_se_rechaza(sesion):
    """La restricción CHECK de la base impide guardar un estado que no esté en ESTADOS_SOLICITUD."""
    centro, usuario, aislado, genoma = crear_base(sesion)
    sesion.add(
        Solicitud(
            aislado_id=aislado.id,
            genoma_id=genoma.id,
            centro_id=centro.id,
            solicitante_id=usuario.id,
            creada_por=usuario.id,
            estado="inventado",
        )
    )
    with pytest.raises(IntegrityError):
        sesion.flush()


def test_rol_invalido_se_rechaza(sesion):
    centro = Centro(codigo="C2", nombre="Otro")
    sesion.add(centro)
    sesion.flush()
    sesion.add(Usuario(correo="z@x.cl", nombre="Z", password_hash="x", rol="XXX", centro_id=centro.id))
    with pytest.raises(IntegrityError):
        sesion.flush()


def test_codigo_interno_unico_por_centro(sesion):
    """El mismo código en el mismo centro viola la restricción única (la API lo informa como error 409)."""
    centro, usuario, _, _ = crear_base(sesion)
    sesion.add(
        Aislado(
            codigo_interno="A-001",
            centro_id=centro.id,
            fecha_aislamiento=date(2026, 9, 2),
            especie_declarada="Klebsiella pneumoniae",
            tipo_muestra="orina",
            creado_por=usuario.id,
        )
    )
    with pytest.raises(IntegrityError):
        sesion.flush()


def test_accesion_de_fago_es_unica(sesion):
    sesion.add(Fago(accesion="MN000001", nombre="Fago uno"))
    sesion.flush()
    sesion.add(Fago(accesion="MN000001", nombre="Fago duplicado"))
    with pytest.raises(IntegrityError):
        sesion.flush()


def test_fago_nace_pendiente_de_curaduria(sesion):
    f = Fago(accesion="MN000002", nombre="Fago dos")
    sesion.add(f)
    sesion.flush()
    assert f.estado_curaduria == "pendiente"
    assert f.ciclo_vida == "desconocido"
