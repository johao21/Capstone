"""Flujo de validación y emisión: bandeja, tomar, aprobar con descartes, rechazar, corregir, ensayos y alertas (RF-41 a RF-46, RF-17, RF-64)."""
import io
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alerta, Auditoria, RecomendacionEmitida

FASTA = b">contig1\nACGTACGTACGTACGT\n>contig2\nTTGACCA\n"


def nueva(c, codigo, **extra):
    contenido = FASTA + b">" + codigo.encode() + b"\nACGT\n"
    r = c.post("/api/v1/solicitudes", data={"codigo_interno": codigo, **extra}, files={"archivo": ("g.fasta", io.BytesIO(contenido))})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def lista_para_validar(como, prediccion_lista, codigo="V-1", cuentas=None, n=8):
    sol = nueva(como("tec"), codigo, **({"clinico_id": str(cuentas["cli"]["id"])} if cuentas else {}))
    fagos = prediccion_lista(sol, n=n)
    return sol, fagos


def url(sol, ruta=""):
    return f"/api/v1/solicitudes/{sol}{ruta}"


# ------------------------------------------------------------ predicción lista
def test_cuando_la_prediccion_queda_lista_se_avisa_a_los_microbiologos(como, prediccion_lista, engine, cuentas):
    sol, _ = lista_para_validar(como, prediccion_lista)
    with Session(engine) as s:
        alertas = s.scalars(select(Alerta).where(Alerta.tipo == "prediccion_lista")).all()
    assert {a.usuario_id for a in alertas} == {cuentas["mic"]["id"], cuentas["mic2"]["id"]}
    bandeja = como("mic").get("/api/v1/solicitudes", params={"estado": "prediccion_lista"}).json()
    assert [i["id"] for i in bandeja["items"]] == [sol]


def test_el_ranking_viene_ordenado_con_explicacion_modelo_y_aviso(como, prediccion_lista):
    sol, fagos = lista_para_validar(como, prediccion_lista)
    d = como("mic").get(url(sol, "/prediccion")).json()
    assert [i["fago_id"] for i in d["items"]] == [str(f) for f in fagos]
    assert d["items"][0]["puntaje"] > d["items"][-1]["puntaje"] and d["items"][0]["rango"] == 1
    assert d["items"][0]["explicacion"]["metodo"] == "shap"
    assert d["modelo"]["version"] == "prueba-1" and d["modelo"]["metricas"]["top5"] == 0.9
    assert "no diagnostica ni prescribe" in d["aviso"] and d["total_fagos"] == 8


def test_solo_el_microbiologo_y_el_administrador_ven_el_ranking_sin_validar(como, prediccion_lista):
    sol, _ = lista_para_validar(como, prediccion_lista)
    assert como("tec").get(url(sol, "/prediccion")).status_code == 403
    assert como("cli").get(url(sol, "/prediccion")).status_code == 403
    assert como("adm").get(url(sol, "/prediccion")).status_code == 200


# ------------------------------------------------------------------- tomar
def test_tomar_asigna_la_solicitud_y_nadie_mas_puede_tomarla(como, prediccion_lista):
    sol, _ = lista_para_validar(como, prediccion_lista)
    assert como("tec").post(url(sol, "/tomar")).status_code == 403
    assert como("mic").post(url(sol, "/tomar")).json() == {"estado": "en_validacion"}
    assert como("mic2").post(url(sol, "/tomar")).status_code == 404  # ya no es visible para otro microbiólogo
    assert como("mic2").get(url(sol)).status_code == 404
    assert como("mic").get(url(sol)).json()["asignada_a"] == "Usuario mic"


def test_liberar_devuelve_la_solicitud_a_la_bandeja(como, prediccion_lista):
    sol, _ = lista_para_validar(como, prediccion_lista)
    como("mic").post(url(sol, "/tomar"))
    assert como("mic").post(url(sol, "/liberar")).json()["estado"] == "prediccion_lista"
    assert como("mic2").post(url(sol, "/tomar")).status_code == 200


def test_el_administrador_puede_reasignar_a_otro_microbiologo(como, prediccion_lista, cuentas):
    sol, _ = lista_para_validar(como, prediccion_lista)
    como("mic").post(url(sol, "/tomar"))
    assert como("tec").post(url(sol, "/reasignar"), json={"usuario_id": str(cuentas["mic2"]["id"])}).status_code == 403
    assert como("adm").post(url(sol, "/reasignar"), json={"usuario_id": str(cuentas["tec"]["id"])}).status_code == 422
    assert como("adm").post(url(sol, "/reasignar"), json={"usuario_id": str(cuentas["mic2"]["id"])}).status_code == 200
    assert como("mic").get(url(sol)).status_code == 404
    assert como("mic2").get(url(sol)).status_code == 200


# ------------------------------------------------------------------ aprobar
def test_aprobar_emite_la_recomendacion_con_los_candidatos_validados(como, prediccion_lista, engine, cuentas):
    sol, fagos = lista_para_validar(como, prediccion_lista, cuentas=cuentas)
    mic = como("mic")
    mic.post(url(sol, "/tomar"))
    r = mic.post(url(sol, "/validacion/aprobar"), json={"top": 3, "descartes": [{"fago_id": str(fagos[0]), "justificacion": "ensayo previo negativo"}],
                                                         "observacion": "revisado"})
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    # Se emiten los 3 mejores no descartados (rangos 2, 3 y 4); el descartado queda con su justificación.
    aceptados = [c["rango"] for c in cuerpo["candidatos"] if not c["descartado"]]
    assert aceptados == [2, 3, 4]
    descartado = next(c for c in cuerpo["candidatos"] if c["descartado"])
    assert descartado["fago_id"] == str(fagos[0]) and descartado["justificacion"] == "ensayo previo negativo"
    assert cuerpo["version"] == 1 and cuerpo["estado"] == "vigente" and cuerpo["modelo_version"] == "prueba-1"
    assert "no diagnostica ni prescribe" in cuerpo["advertencia"]
    assert como("mic").get(url(sol)).json()["estado"] == "emitida"
    with Session(engine) as s:
        evento = s.scalars(select(Auditoria).where(Auditoria.accion == "recomendacion_emitida")).one()
    assert evento.modelo_version == "prueba-1" and evento.rol == "MIC"  # RF-49


def test_al_emitir_se_avisa_al_tecnico_y_al_clinico_solicitante(como, prediccion_lista, engine, cuentas):
    sol, _ = lista_para_validar(como, prediccion_lista, cuentas=cuentas)
    como("mic").post(url(sol, "/tomar"))
    como("mic").post(url(sol, "/validacion/aprobar"), json={})
    with Session(engine) as s:
        destinatarios = {a.usuario_id for a in s.scalars(select(Alerta).where(Alerta.tipo == "emitida"))}
    assert destinatarios == {cuentas["tec"]["id"], cuentas["cli"]["id"]}
    assert como("cli").get("/api/v1/alertas").json()["no_leidas"] == 1


def test_no_se_puede_aprobar_sin_candidatos_ni_descartando_un_fago_ajeno(como, prediccion_lista):
    sol, fagos = lista_para_validar(como, prediccion_lista, n=2)
    mic = como("mic")
    mic.post(url(sol, "/tomar"))
    todos = [{"fago_id": str(f), "justificacion": "no sirve en laboratorio"} for f in fagos]
    assert mic.post(url(sol, "/validacion/aprobar"), json={"descartes": todos}).status_code == 422
    ajeno = {"fago_id": str(uuid.uuid4()), "justificacion": "no está en el ranking"}
    assert mic.post(url(sol, "/validacion/aprobar"), json={"descartes": [ajeno]}).status_code == 422
    assert mic.post(url(sol, "/validacion/aprobar"), json={"descartes": [{"fago_id": str(fagos[0]), "justificacion": "no"}]}).status_code == 422  # justificación muy corta


def test_solo_el_microbiologo_asignado_puede_decidir(como, prediccion_lista):
    sol, _ = lista_para_validar(como, prediccion_lista)
    como("mic").post(url(sol, "/tomar"))
    assert como("tec").post(url(sol, "/validacion/aprobar"), json={}).status_code == 403
    assert como("adm").post(url(sol, "/validacion/aprobar"), json={}).status_code == 403
    assert como("mic2").post(url(sol, "/validacion/aprobar"), json={}).status_code == 404
    assert como("mic").post(url(sol, "/validacion/aprobar"), json={}).status_code == 201
    assert como("mic").post(url(sol, "/validacion/aprobar"), json={}).status_code == 409  # ya emitida


def test_aprobar_una_solicitud_que_no_se_tomo_es_conflicto(como, prediccion_lista):
    sol, _ = lista_para_validar(como, prediccion_lista)
    assert como("mic").post(url(sol, "/validacion/aprobar"), json={}).status_code == 409


# ------------------------------------------------------------------ rechazar
def test_rechazar_exige_justificacion_y_avisa_al_tecnico(como, prediccion_lista, engine, cuentas):
    sol, _ = lista_para_validar(como, prediccion_lista)
    mic = como("mic")
    mic.post(url(sol, "/tomar"))
    assert mic.post(url(sol, "/validacion/rechazar"), json={"justificacion": ""}).status_code == 422
    assert mic.post(url(sol, "/validacion/rechazar"), json={"justificacion": "genoma contaminado"}).status_code == 200
    d = como("tec").get(url(sol)).json()
    assert d["estado"] == "rechazada" and d["motivo_estado"] == "genoma contaminado"
    with Session(engine) as s:
        a = s.scalars(select(Alerta).where(Alerta.tipo == "rechazada")).one()
    assert a.usuario_id == cuentas["tec"]["id"] and "genoma contaminado" in a.mensaje


# ---------------------------------------------------- recomendación emitida
def test_quien_consulta_la_recomendacion_queda_en_la_auditoria_y_el_tecnico_no_ve_los_descartados(como, prediccion_lista, engine):
    sol, fagos = lista_para_validar(como, prediccion_lista)
    mic = como("mic")
    mic.post(url(sol, "/tomar"))
    mic.post(url(sol, "/validacion/aprobar"), json={"descartes": [{"fago_id": str(fagos[1]), "justificacion": "ya probado sin éxito"}]})
    tec = como("tec").get(url(sol, "/recomendacion-emitida")).json()
    assert all(not c["descartado"] for c in tec["candidatos"]) and len(tec["candidatos"]) == 5
    completo = como("mic").get(url(sol, "/recomendacion-emitida")).json()
    assert any(c["descartado"] for c in completo["candidatos"])
    with Session(engine) as s:
        consultas = s.scalars(select(Auditoria).where(Auditoria.accion == "recomendacion_consultada")).all()
    assert [e.rol for e in consultas] == ["TEC", "MIC"] and all(e.modelo_version == "prueba-1" for e in consultas)


def test_una_solicitud_sin_emitir_no_tiene_recomendacion(como, prediccion_lista):
    sol, _ = lista_para_validar(como, prediccion_lista)
    assert como("tec").get(url(sol, "/recomendacion-emitida")).status_code == 404


def test_un_clinico_de_otro_centro_no_puede_consultarla(como, prediccion_lista):
    sol, _ = lista_para_validar(como, prediccion_lista)
    como("mic").post(url(sol, "/tomar"))
    como("mic").post(url(sol, "/validacion/aprobar"), json={})
    assert como("cli").get(url(sol, "/recomendacion-emitida")).status_code == 200
    assert como("cli_otro").get(url(sol, "/recomendacion-emitida")).status_code == 404


def test_corregir_crea_otra_version_y_conserva_la_anterior(como, prediccion_lista, engine):
    sol, fagos = lista_para_validar(como, prediccion_lista)
    mic = como("mic")
    mic.post(url(sol, "/tomar"))
    mic.post(url(sol, "/validacion/aprobar"), json={"top": 3})
    assert mic.post(url(sol, "/recomendacion-emitida/corregir"), json={"top": 3}).status_code == 422  # falta el motivo
    r = mic.post(url(sol, "/recomendacion-emitida/corregir"), json={"top": 2, "observacion": "se quitó un candidato",
                                                                     "descartes": [{"fago_id": str(fagos[0]), "justificacion": "toxicidad reportada"}]})
    assert r.status_code == 201 and r.json()["version"] == 2 and r.json()["estado"] == "vigente"
    versiones = como("tec").get(url(sol, "/recomendacion-emitida")).json()["versiones"]
    assert [(v["version"], v["estado"]) for v in versiones] == [(2, "vigente"), (1, "reemplazada")]
    vieja = como("mic").get(url(sol, "/recomendacion-emitida"), params={"version": 1}).json()
    assert vieja["version"] == 1 and [c["rango"] for c in vieja["candidatos"]] == [1, 2, 3]  # la anterior quedó intacta


def test_registrar_ensayos_y_cerrar_la_solicitud(como, prediccion_lista):
    sol, fagos = lista_para_validar(como, prediccion_lista)
    mic = como("mic")
    mic.post(url(sol, "/tomar"))
    mic.post(url(sol, "/validacion/aprobar"), json={"top": 2})
    assert como("tec").post(url(sol, "/ensayos"), json={"resultados": [{"fago_id": str(fagos[0]), "resultado": "infecta"}]}).status_code == 403
    assert mic.post(url(sol, "/ensayos"), json={"resultados": [{"fago_id": str(fagos[0]), "resultado": "tal vez"}]}).status_code == 422
    assert mic.post(url(sol, "/ensayos"), json={"resultados": [{"fago_id": str(fagos[7]), "resultado": "infecta"}]}).status_code == 422  # no es candidato
    r = mic.post(url(sol, "/ensayos"), json={"resultados": [{"fago_id": str(fagos[0]), "resultado": "infecta"}, {"fago_id": str(fagos[1]), "resultado": "no_infecta"}],
                                              "cerrar": True})
    assert r.status_code == 200
    assert {c["rango"]: c["resultado_ensayo"] for c in r.json()["candidatos"]} == {1: "infecta", 2: "no_infecta"}
    assert como("tec").get(url(sol)).json()["estado"] == "cerrada"


def test_el_administrador_reconstruye_quien_pidio_con_que_modelo_y_quien_valido(como, prediccion_lista, cuentas):
    sol, _ = lista_para_validar(como, prediccion_lista, cuentas=cuentas)
    como("mic").post(url(sol, "/tomar"))
    como("mic").post(url(sol, "/validacion/aprobar"), json={})
    assert como("mic").get(url(sol, "/reconstruccion")).status_code == 403
    d = como("adm").get(url(sol, "/reconstruccion")).json()
    assert d["solicitada_por"]["tecnico"] == "Usuario tec" and d["solicitada_por"]["clinico"] == "Usuario cli"
    assert d["modelo"]["version"] == "prueba-1"
    assert d["recomendaciones"][0]["validada_por"] == "Usuario mic"
    assert [h["a"] for h in d["historial_estados"]][-1] == "emitida"
    assert "recomendacion_emitida" in [e["accion"] for e in d["eventos_auditoria"]]


def test_una_recomendacion_emitida_no_se_puede_modificar_por_la_api(como, prediccion_lista, engine):
    sol, _ = lista_para_validar(como, prediccion_lista)
    como("mic").post(url(sol, "/tomar"))
    como("mic").post(url(sol, "/validacion/aprobar"), json={})
    for metodo in ("put", "patch", "delete"):
        assert getattr(como("mic"), metodo)(url(sol, "/recomendacion-emitida")).status_code in (404, 405)
    with Session(engine) as s:
        emitida = s.scalars(select(RecomendacionEmitida)).one()
        assert len(emitida.candidatos) == 5  # los candidatos viven dentro de la recomendación
