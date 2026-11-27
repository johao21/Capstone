"""/api/v1/salud: 200 si la base responde y 503 si falla. La comprobación real se reemplaza por una función falsa."""
from fastapi.testclient import TestClient

from app import salud
from app.main import app

cliente = TestClient(app)


def test_salud_ok_cuando_la_base_responde(monkeypatch):
    monkeypatch.setattr(salud, "comprobar_postgres", lambda: "ok")
    r = cliente.get("/api/v1/salud")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok", "postgres": "ok"}


def test_salud_degradada_responde_503_e_indica_el_motivo(monkeypatch):
    monkeypatch.setattr(salud, "comprobar_postgres", lambda: "falla: OperationalError")
    r = cliente.get("/api/v1/salud")
    assert r.status_code == 503
    assert r.json()["estado"] == "degradado"
    assert r.json()["postgres"].startswith("falla")
