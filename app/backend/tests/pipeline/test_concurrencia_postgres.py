"""Concurrencia de la cola de trabajos contra PostgreSQL real (`FOR UPDATE SKIP LOCKED`).

Las demás pruebas usan SQLite en memoria, que ignora `SKIP LOCKED`; esta es la que demuestra que varios
workers simultáneos no toman el mismo trabajo. Se salta sola si no se indica una base de prueba:

    SIRFA_TEST_POSTGRES_DB=sirfa_test   # base vacía y desechable, en el mismo servidor que usa la app

El servidor, el usuario y la clave salen de la configuración normal (variables POSTGRES_*). Las tablas se crean
y se borran dentro de esa base, así que nunca se toca la base real de SIRFA.
"""
import os
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.engine import URL

from app.config import get_settings
from app.models import Base, Trabajo
from pipeline.trabajos import reclamar

BASE_PRUEBA = os.environ.get("SIRFA_TEST_POSTGRES_DB")

pytestmark = pytest.mark.skipif(not BASE_PRUEBA, reason="define SIRFA_TEST_POSTGRES_DB para probar contra PostgreSQL")

N_TRABAJOS = 60
N_WORKERS = 8


@pytest.fixture()
def engine_pg():
    """Motor hacia la base de prueba, con las tablas recién creadas y borradas al terminar."""
    ajustes = get_settings()
    url = URL.create(
        "postgresql+psycopg",
        username=ajustes.postgres_user,
        password=ajustes.postgres_password,
        host=ajustes.postgres_host,
        port=ajustes.postgres_port,
        database=BASE_PRUEBA,
    )
    engine = create_engine(url, pool_size=N_WORKERS + 2)
    assert BASE_PRUEBA != ajustes.postgres_db, "la base de prueba no puede ser la base real"
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_varios_workers_no_toman_el_mismo_trabajo(engine_pg):
    with Session(engine_pg) as s:
        s.add_all([Trabajo(tipo="pipeline") for _ in range(N_TRABAJOS)])
        s.commit()

    tomados: list[uuid.UUID] = []
    candado = threading.Lock()
    errores: list[BaseException] = []

    def worker(numero: int) -> None:
        try:
            while True:
                # Una sesión (y una transacción) por trabajo, igual que en pipeline/worker.py.
                with Session(engine_pg) as session:
                    trabajo = reclamar(session, "pipeline", f"w{numero}")
                    if trabajo is None:
                        session.rollback()
                        return
                    # Mantiene la fila bloqueada un momento: es cuando otro worker intentaría tomarla.
                    time.sleep(0.01)
                    identificador = trabajo.id
                    session.commit()
                with candado:
                    tomados.append(identificador)
        except BaseException as exc:  # noqa: BLE001 - se informa en el hilo principal
            errores.append(exc)

    hilos = [threading.Thread(target=worker, args=(n,)) for n in range(N_WORKERS)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)

    assert not errores, errores
    assert not any(h.is_alive() for h in hilos), "algún worker no terminó"
    assert len(tomados) == N_TRABAJOS, "faltaron trabajos por tomar"
    assert len(set(tomados)) == N_TRABAJOS, "un mismo trabajo lo tomaron dos workers"

    with Session(engine_pg) as s:
        assert s.scalar(select(func.count()).select_from(Trabajo).where(Trabajo.estado == "en_curso")) == N_TRABAJOS
        # Cada trabajo se reclamó exactamente una vez.
        assert s.scalar(select(func.count()).select_from(Trabajo).where(Trabajo.intentos != 1)) == 0
