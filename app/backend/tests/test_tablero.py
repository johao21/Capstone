"""Tablero: cobertura del banco, brechas terapéuticas y tendencias, siempre agregados y con supresión de grupos pequeños (RF-55 a RF-60)."""
import io
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.models import Fago, InteraccionConocida, Solicitud
from app.routers import tablero

FASTA = b">contig1\nACGTACGTACGTACGT\n>contig2\nTTGACCA\n"


@pytest.fixture()
def minimo(monkeypatch):
    """Cambia el mínimo de casos por grupo (el valor real es 5)."""
    def fijar(n, umbral=0.5):
        monkeypatch.setattr(tablero, "get_settings", lambda: SimpleNamespace(tablero_minimo_grupo=n, umbral_candidato=umbral))

    fijar(3)
    return fijar


def solicitud_con_locus(c, engine, codigo, locus, mecanismo="KPC"):
    r = c.post("/api/v1/solicitudes", data={"codigo_interno": codigo, "mecanismo_resistencia": mecanismo},
               files={"archivo": ("g.fasta", io.BytesIO(FASTA + b">" + codigo.encode() + b"\nACGT\n"))})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    from datetime import datetime, timezone

    with Session(engine) as s:
        sol = s.get(Solicitud, uuid.UUID(sid))
        sol.especie_detectada, sol.locus_k_tipo, sol.locus_k_confianza = "Klebsiella pneumoniae", locus, "Good"
        sol.analizado_en = datetime.now(timezone.utc)
        s.commit()
    return sid


def test_los_grupos_con_pocos_casos_se_suprimen_y_se_reunen_en_otros(como, engine, minimo):
    tec = como("tec")
    for i in range(3):
        solicitud_con_locus(tec, engine, f"A{i}", "KL2")
    solicitud_con_locus(tec, engine, "B0", "KL5")
    d = como("epi").get("/api/v1/tablero/tendencias").json()
    assert d["minimo_grupo"] == 3 and d["total_solicitudes"] == 4
    assert d["por_locus_k"] == [{"grupo": "KL2", "n": 3, "suprimido": False}, {"grupo": tablero.ETIQUETA_OTROS, "n": 1, "suprimido": True}]
    assert d["por_mecanismo"] == [{"grupo": "KPC", "n": 4, "suprimido": False}]


def test_con_menos_casos_que_el_minimo_no_se_muestra_ningun_dato_individual(como, engine, minimo):
    minimo(5)
    tec = como("tec")
    for i in range(3):
        solicitud_con_locus(tec, engine, f"A{i}", "KL2")
    d = como("epi").get("/api/v1/tablero/tendencias").json()
    assert d["total_solicitudes"] is None
    assert all(g["suprimido"] for g in d["por_locus_k"] + d["por_mes"] + d["por_mecanismo"] + d["por_centro"])


def test_las_tendencias_se_filtran_por_centro_especie_y_locus(como, engine, minimo, cuentas):
    minimo(1)
    tec = como("tec")
    solicitud_con_locus(tec, engine, "A", "KL2")
    solicitud_con_locus(tec, engine, "B", "KL5")
    epi = como("epi")
    assert [g["grupo"] for g in epi.get("/api/v1/tablero/tendencias", params={"locus_k": "KL5"}).json()["por_locus_k"]] == ["KL5"]
    assert epi.get("/api/v1/tablero/tendencias", params={"especie": "Escherichia coli"}).json()["por_locus_k"] == []
    otro_centro = str(cuentas["cli_otro"]["centro_id"])
    assert epi.get("/api/v1/tablero/tendencias", params={"centro_id": otro_centro}).json()["por_locus_k"] == []
    assert epi.get("/api/v1/tablero/tendencias", params={"desde": "2999-01-01"}).json()["por_locus_k"] == []


def test_una_brecha_es_un_locus_sin_fagos_con_evidencia_ni_candidatos(como, engine, minimo, prediccion_lista):
    minimo(1)
    tec = como("tec")
    solicitud_con_locus(tec, engine, "E1", "KL2")
    solicitud_con_locus(tec, engine, "S1", "KL7")  # nadie conoce un fago para KL7
    with Session(engine) as s:
        fago = Fago(accesion="NC_X", nombre="Klebsiella phage X", estado_curaduria="aprobado")
        s.add(fago)
        s.flush()
        s.add(InteraccionConocida(fago_id=fago.id, especie_hospedador="Klebsiella pneumoniae", cepa="c", locus_k_tipo="KL2", resultado="infecta",
                                  fuente="p", fuente_version="1"))
        s.commit()
    grupos = {g["locus_k"]: g for g in como("epi").get("/api/v1/tablero/brechas").json()["grupos"]}
    assert grupos["KL2"]["fagos_con_evidencia"] == 1 and grupos["KL2"]["brecha"] is False
    assert grupos["KL7"]["fagos_con_evidencia"] == 0 and grupos["KL7"]["brecha"] is True


def test_un_locus_con_candidatos_sobre_el_umbral_no_es_brecha(como, engine, minimo, prediccion_lista):
    minimo(1)
    tec = como("tec")
    sid = solicitud_con_locus(tec, engine, "P1", "KL9")
    prediccion_lista(sid, n=4, locus="KL9")  # puntajes 0.95, 0.85, 0.75 y 0.65: todos sobre 0.5
    g = como("epi").get("/api/v1/tablero/brechas").json()["grupos"][0]
    assert g["locus_k"] == "KL9" and g["fagos_candidatos"] == 4 and g["brecha"] is False
    minimo(1, umbral=0.99)  # con un umbral más exigente ya no hay candidatos
    g = como("epi").get("/api/v1/tablero/brechas").json()["grupos"][0]
    assert g["fagos_candidatos"] == 0 and g["brecha"] is True


def test_la_cobertura_cuenta_solo_los_fagos_aprobados(como, engine):
    with Session(engine) as s:
        s.add_all([
            Fago(accesion="A", nombre="a", estado_curaduria="aprobado", ciclo_vida="litico", familia="Autographiviridae"),
            Fago(accesion="B", nombre="b", estado_curaduria="aprobado", ciclo_vida="litico", familia="Autographiviridae"),
            Fago(accesion="C", nombre="c", estado_curaduria="aprobado", ciclo_vida="templado"),
            Fago(accesion="D", nombre="d", estado_curaduria="pendiente", ciclo_vida="litico"),
        ])
        s.commit()
    d = como("mic").get("/api/v1/tablero/cobertura").json()
    assert d["fagos_aprobados"] == 3 and d["fagos_total"] == 4
    assert {g["grupo"]: g["n"] for g in d["por_ciclo_vida"]} == {"litico": 2, "templado": 1}
    assert {g["grupo"]: g["n"] for g in d["por_familia"]} == {"Autographiviridae": 2, "sin dato": 1}


def test_exportar_a_csv_es_del_epidemiologo_y_trae_solo_agregados(como, engine, minimo):
    tec = como("tec")
    for i in range(3):
        solicitud_con_locus(tec, engine, f"A{i}", "KL2")
    assert como("adm").get("/api/v1/tablero/exportar.csv").status_code == 403
    r = como("epi").get("/api/v1/tablero/exportar.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    texto = r.text
    assert texto.splitlines()[0] == "indicador,grupo,casos,suprimido" and "por_locus_k,KL2,3,no" in texto
    assert "A0" not in texto and "@" not in texto  # ningún código de aislado ni correo
