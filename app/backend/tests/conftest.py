"""Fixtures compartidas por las pruebas de la API: base SQLite en memoria, cuentas por rol y clientes ya autenticados."""
import uuid
from types import SimpleNamespace

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import seguridad
from app.db import obtener_sesion
from app.estados import cambiar_estado
from app.main import app
from app.models import Base, Centro, Fago, ModeloPrediccion, Prediccion, PrediccionFago, Solicitud, Usuario
from app.routers import solicitudes as ruta_solicitudes

CLAVE = "Clave-de-prueba-123"


@pytest.fixture(autouse=True, scope="session")
def argon2_rapido():
    """Argon2 con parámetros mínimos: las pruebas crean muchas cuentas y no necesitan el costo de producción."""
    seguridad._hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest.fixture()
def engine():
    """SQLite en memoria. StaticPool y check_same_thread=False hacen que todas las sesiones compartan una única conexión; sin eso cada sesión vería una base vacía distinta."""
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    return motor


@pytest.fixture()
def cuentas(engine):
    """Un centro (C1) con técnico, otro técnico, clínico, microbiólogo, epidemiólogo y administrador, y un clínico de otro centro (C2).

    Devuelve {nombre: {"id": UUID, "correo": str, "centro_id": UUID}}; todas usan la contraseña `CLAVE`.
    """
    with Session(engine) as s:
        c1, c2 = Centro(codigo="C1", nombre="Centro 1"), Centro(codigo="C2", nombre="Centro 2")
        s.add_all([c1, c2])
        s.flush()
        definiciones = [("tec", "TEC", c1), ("tec2", "TEC", c1), ("cli", "CLI", c1), ("cli_otro", "CLI", c2),
                        ("mic", "MIC", c1), ("mic2", "MIC", c1), ("epi", "EPI", c1), ("adm", "ADM", c1)]
        salida = {}
        for nombre, rol, centro in definiciones:
            u = Usuario(correo=f"{nombre}@sirfa.test", nombre=f"Usuario {nombre}", rol=rol, centro_id=centro.id,
                        password_hash=seguridad.hash_password(CLAVE))
            s.add(u)
            s.flush()
            salida[nombre] = {"id": u.id, "correo": u.correo, "centro_id": centro.id}
        s.commit()
    return salida


@pytest.fixture()
def base_api(engine, tmp_path, monkeypatch):
    """Cambia la sesión de la API por una sobre SQLite y la carpeta de genomas por una temporal."""
    def sesion():
        with Session(engine, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[obtener_sesion] = sesion
    monkeypatch.setattr(ruta_solicitudes, "get_settings", lambda: SimpleNamespace(genomas_dir=str(tmp_path / "genomas")))
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def como(base_api, cuentas):
    """`como("mic")` devuelve un cliente HTTP que ya inició sesión con la cuenta indicada."""
    def entrar(nombre: str) -> TestClient:
        c = TestClient(app)
        r = c.post("/api/v1/auth/login", json={"correo": cuentas[nombre]["correo"], "password": CLAVE})
        assert r.status_code == 200, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        return c

    return entrar


@pytest.fixture()
def cliente(como):
    """Cliente autenticado como técnico: el que usan las pruebas de solicitudes."""
    return como("tec")


@pytest.fixture()
def prediccion_lista(engine):
    """Fábrica: lleva una solicitud ya creada hasta `prediccion_lista` con un ranking de `n` fagos aprobados. Devuelve los ids de los fagos, del mejor al peor."""
    def fabricar(solicitud_id: str, n: int = 8, locus: str = "KL2") -> list[uuid.UUID]:
        with Session(engine) as s:
            sol = s.get(Solicitud, uuid.UUID(solicitud_id))
            modelo = s.query(ModeloPrediccion).filter_by(version="prueba-1").first()
            if modelo is None:
                modelo = ModeloPrediccion(version="prueba-1", algoritmo="XGBoost (prueba)", n_entrenamiento=100,
                                          metricas={"top5": 0.9, "auc": 0.8}, activo=True)
                s.add(modelo)
                s.flush()
            cambiar_estado(s, sol, "en_analisis")
            pred = Prediccion(solicitud_id=sol.id, modelo_id=modelo.id, locus_k_tipo=locus)
            s.add(pred)
            s.flush()
            ids = []
            for i in range(n):
                fago = Fago(accesion=f"NC_{solicitud_id[:4]}{i}", nombre=f"Klebsiella phage {i}", estado_curaduria="aprobado")
                s.add(fago)
                s.flush()
                s.add(PrediccionFago(prediccion_id=pred.id, fago_id=fago.id, puntaje=round(0.95 - 0.1 * i, 2), rango=i + 1,
                                     explicacion={"metodo": "shap", "caracteristicas": [{"nombre": "x", "contribucion": 0.1}]}))
                ids.append(fago.id)
            cambiar_estado(s, sol, "prediccion_lista")
            s.commit()
            return ids

    return fabricar
