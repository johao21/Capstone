"""/api/v1/salud: 200 si ambas bases responden y 503 si alguna falla. Las comprobaciones reales se reemplazan por funciones falsas."""
from fastapi.testclient import TestClient

from app import salud
from app.main import app

cliente = TestClient(app)


def test_salud_ok_cuando_ambas_bases_responden(monkeypatch):
    monkeypatch.setattr(salud, "comprobar_postgres", lambda: "ok")
    monkeypatch.setattr(salud, "comprobar_mongo", lambda: "ok")
    r = cliente.get("/api/v1/salud")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok", "postgres": "ok", "mongo": "ok"}


def test_salud_degradada_responde_503_e_indica_cual_falla(monkeypatch):
    monkeypatch.setattr(salud, "comprobar_postgres", lambda: "ok")
    monkeypatch.setattr(salud, "comprobar_mongo", lambda: "falla: ServerSelectionTimeoutError")
    r = cliente.get("/api/v1/salud")
    assert r.status_code == 503
    assert r.json()["estado"] == "degradado"
    assert r.json()["mongo"].startswith("falla")
    assert r.json()["postgres"] == "ok"
