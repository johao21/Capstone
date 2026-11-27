"""Usuarios, auditoría encadenada, alertas, curaduría del banco y modelo (RF-03, RF-32, RF-33, RF-48 a RF-54, RF-65, RF-39)."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from app import auditoria
from app.main import app
from app.models import Auditoria, Fago, Usuario
from app.routers import modelo as ruta_modelo

from conftest import CLAVE


# -------------------------------------------------------------- usuarios
def test_el_administrador_crea_un_usuario_que_puede_iniciar_sesion(como, cuentas, base_api):
    adm = como("adm")
    datos = {"correo": "Nueva.Persona@Sirfa.test", "nombre": "Nueva Persona", "rol": "MIC", "centro_id": str(cuentas["tec"]["centro_id"]),
             "password": "Clave-nueva-2026"}
    r = adm.post("/api/v1/usuarios", json=datos)
    assert r.status_code == 201 and r.json()["correo"] == "nueva.persona@sirfa.test" and r.json()["activo"] is True
    assert "password" not in r.json() and "password_hash" not in r.json()
    entrada = TestClient(app).post("/api/v1/auth/login", json={"correo": "nueva.persona@sirfa.test", "password": "Clave-nueva-2026"})
    assert entrada.status_code == 200 and entrada.json()["usuario"]["rol"] == "MIC"


def test_crear_usuario_valida_rol_centro_contrasena_y_correo_repetido(como, cuentas):
    adm = como("adm")
    base = {"correo": "x@sirfa.test", "nombre": "X", "rol": "TEC", "centro_id": str(cuentas["tec"]["centro_id"]), "password": "Clave-larga-123"}
    assert adm.post("/api/v1/usuarios", json={**base, "rol": "SUPER"}).status_code == 422
    assert adm.post("/api/v1/usuarios", json={**base, "centro_id": str(uuid.uuid4())}).status_code == 422
    assert adm.post("/api/v1/usuarios", json={**base, "password": "corta"}).status_code == 422
    assert adm.post("/api/v1/usuarios", json={**base, "correo": "no-es-correo"}).status_code == 422
    assert adm.post("/api/v1/usuarios", json=base).status_code == 201
    assert adm.post("/api/v1/usuarios", json={**base, "correo": "X@SIRFA.TEST"}).status_code == 409


def test_desactivar_y_reactivar_conserva_al_usuario_y_su_historial(como, cuentas, base_api, engine):
    adm = como("adm")
    uid = str(cuentas["tec"]["id"])
    assert adm.patch(f"/api/v1/usuarios/{uid}", json={"activo": False}).json()["activo"] is False
    assert TestClient(app).post("/api/v1/auth/login", json={"correo": cuentas["tec"]["correo"], "password": CLAVE}).status_code == 403
    assert adm.patch(f"/api/v1/usuarios/{uid}", json={"activo": True}).json()["activo"] is True
    assert TestClient(app).post("/api/v1/auth/login", json={"correo": cuentas["tec"]["correo"], "password": CLAVE}).status_code == 200
    with Session(engine) as s:
        assert s.get(Usuario, cuentas["tec"]["id"]) is not None  # los usuarios no se eliminan
    assert adm.delete(f"/api/v1/usuarios/{uid}").status_code == 405


def test_un_usuario_desactivado_pierde_el_acceso_aunque_tenga_un_token_vigente(como, cuentas):
    tec = como("tec")
    assert tec.get("/api/v1/auth/yo").status_code == 200
    como("adm").patch(f"/api/v1/usuarios/{cuentas['tec']['id']}", json={"activo": False})
    assert tec.get("/api/v1/auth/yo").status_code == 401


def test_cambiar_el_rol_rige_de_inmediato_y_el_administrador_no_puede_quitarse_el_acceso(como, cuentas):
    tec = como("tec")
    assert tec.get("/api/v1/solicitudes").status_code == 200
    como("adm").patch(f"/api/v1/usuarios/{cuentas['tec']['id']}", json={"rol": "EPI"})
    assert tec.get("/api/v1/solicitudes").status_code == 403  # el token dice TEC, pero manda el rol guardado
    adm = como("adm")
    assert adm.patch(f"/api/v1/usuarios/{cuentas['adm']['id']}", json={"activo": False}).status_code == 409
    assert adm.patch(f"/api/v1/usuarios/{cuentas['adm']['id']}", json={"rol": "TEC"}).status_code == 409


def test_restablecer_la_contrasena_genera_una_temporal_que_funciona(como, cuentas, base_api):
    r = como("adm").post(f"/api/v1/usuarios/{cuentas['tec']['id']}/restablecer-password", json={})
    temporal = r.json()["password_temporal"]
    assert r.status_code == 200 and len(temporal) >= 10
    assert TestClient(app).post("/api/v1/auth/login", json={"correo": cuentas["tec"]["correo"], "password": CLAVE}).status_code == 401
    assert TestClient(app).post("/api/v1/auth/login", json={"correo": cuentas["tec"]["correo"], "password": temporal}).status_code == 200
    assert como("mic").post(f"/api/v1/usuarios/{cuentas['tec']['id']}/restablecer-password", json={}).status_code == 403


def test_el_tecnico_elige_el_clinico_solicitante_solo_entre_los_de_su_centro(como, cuentas):
    nombres = [c["nombre"] for c in como("tec").get("/api/v1/usuarios/clinicos").json()]
    assert nombres == ["Usuario cli"]
    assert como("mic").get("/api/v1/usuarios/clinicos").status_code == 403


def test_crear_centro_y_rechazar_un_codigo_repetido(como):
    adm = como("adm")
    assert adm.post("/api/v1/centros", json={"codigo": "hospital-1", "nombre": "Hospital 1"}).json()["codigo"] == "HOSPITAL-1"
    assert adm.post("/api/v1/centros", json={"codigo": "HOSPITAL-1", "nombre": "Otro"}).status_code == 409


# -------------------------------------------------------------- auditoría
def test_la_cadena_de_hashes_cuadra_y_detecta_una_fila_alterada(como, engine):
    como("tec").get("/api/v1/solicitudes")
    como("adm").get("/api/v1/usuarios")
    with Session(engine) as s:
        assert auditoria.verificar(s)["ok"] is True
    adm = como("adm")
    assert adm.get("/api/v1/auditoria/verificar").json()["ok"] is True
    # Se altera una fila por fuera de la aplicación (SQLite no tiene el disparador de PostgreSQL).
    with Session(engine) as s:
        s.execute(update(Auditoria).where(Auditoria.seq == 1).values(accion="otra_cosa"))
        s.commit()
    r = adm.get("/api/v1/auditoria/verificar").json()
    assert r["ok"] is False and r["primer_error_seq"] == 1


def test_borrar_una_fila_del_medio_rompe_la_cadena(como, engine):
    for _ in range(3):
        como("tec")  # cada inicio de sesión agrega un evento
    with Session(engine) as s:
        s.execute(delete(Auditoria).where(Auditoria.seq == 2))
        s.commit()
        r = auditoria.verificar(s)
    assert r["ok"] is False and r["primer_error_seq"] == 3 and "anterior" in r["motivo"]


def test_un_evento_de_una_transaccion_revertida_no_se_guarda(engine):
    with Session(engine) as s:
        auditoria.registrar(s, "descartado_por_rollback")
        s.rollback()
        auditoria.registrar(s, "guardado")
        s.commit()
        savepoint = s.begin_nested()
        auditoria.registrar(s, "descartado_por_savepoint")
        savepoint.rollback()
        auditoria.registrar(s, "guardado_despues")
        s.commit()
        assert [e.accion for e in s.scalars(select(Auditoria).order_by(Auditoria.seq))] == ["guardado", "guardado_despues"]
        assert auditoria.verificar(s)["ok"] is True


def test_el_evento_registra_fecha_usuario_rol_accion_entidad_resultado_y_origen(como, engine, cuentas):
    como("tec")
    with Session(engine) as s:
        e = s.scalars(select(Auditoria).where(Auditoria.accion == "inicio_sesion")).one()
    assert e.ts is not None and e.usuario_id == cuentas["tec"]["id"] and e.rol == "TEC" and e.resultado == "ok"
    assert e.origen == "testclient" and len(e.hash) == 64 and len(e.hash_previo) == 64


def test_consultar_la_auditoria_con_filtros_y_solo_el_administrador(como, cuentas):
    como("tec").get("/api/v1/usuarios")  # genera un acceso_denegado
    adm = como("adm")
    todos = adm.get("/api/v1/auditoria").json()
    assert todos["total"] >= 3
    solo = adm.get("/api/v1/auditoria", params={"accion": "acceso_denegado"}).json()
    assert solo["total"] == 1 and solo["items"][0]["usuario_id"] == str(cuentas["tec"]["id"])
    assert adm.get("/api/v1/auditoria", params={"usuario": cuentas["tec"]["correo"]}).json()["total"] >= 2
    assert adm.get("/api/v1/auditoria", params={"entidad": "endpoint"}).json()["total"] == 1
    assert adm.get("/api/v1/auditoria", params={"desde": "2999-01-01T00:00:00"}).json()["total"] == 0
    assert "acceso_denegado" in adm.get("/api/v1/auditoria/acciones").json()
    assert como("mic").get("/api/v1/auditoria").status_code == 403


def test_exportar_la_auditoria_a_csv_neutraliza_formulas(como, engine):
    with Session(engine) as s:
        auditoria.registrar(s, "=cmd|' /C calc'!A0", correo="x@y.cl")
        s.commit()
    r = como("adm").get("/api/v1/auditoria/exportar.csv", params={"usuario": "x@y.cl"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lineas = r.text.strip().splitlines()
    assert lineas[0].startswith("seq,fecha_utc,usuario,rol,accion") and len(lineas) == 2
    assert "'=cmd" in lineas[1] and ",=cmd" not in lineas[1]


# ---------------------------------------------------------------- alertas
def test_las_alertas_se_leen_y_se_marcan_como_leidas(como, prediccion_lista, cuentas):
    import io
    tec = como("tec")
    sol = tec.post("/api/v1/solicitudes", data={"codigo_interno": "AL-1"}, files={"archivo": ("g.fasta", io.BytesIO(b">c\nACGTACGT\n"))}).json()["id"]
    prediccion_lista(sol)
    mic = como("mic")
    lista = mic.get("/api/v1/alertas").json()
    assert lista["no_leidas"] == 1 and lista["items"][0]["tipo"] == "prediccion_lista"
    alerta_id = lista["items"][0]["id"]
    assert como("mic2").post(f"/api/v1/alertas/{alerta_id}/leida").status_code == 404  # no es suya
    assert mic.post(f"/api/v1/alertas/{alerta_id}/leida").status_code == 204
    assert mic.get("/api/v1/alertas").json()["no_leidas"] == 0
    assert mic.get("/api/v1/alertas", params={"solo_no_leidas": True}).json()["items"] == []
    assert como("mic2").post("/api/v1/alertas/leer-todas").status_code == 204
    assert como("mic2").get("/api/v1/alertas").json()["no_leidas"] == 0


# ---------------------------------------------------------- banco de fagos
def _fagos(engine, n=3):
    with Session(engine) as s:
        ids = []
        for i in range(n):
            f = Fago(accesion=f"NC_{i}", nombre=f"Klebsiella phage {i}", hospedador_declarado="Klebsiella pneumoniae")
            s.add(f)
            s.flush()
            ids.append(f.id)
        s.commit()
        return ids


def test_solo_el_microbiologo_cura_el_banco_y_el_administrador_solo_lo_consulta(como, engine):
    f1, f2, _ = _fagos(engine)
    adm, mic = como("adm"), como("mic")
    assert adm.get("/api/v1/fagos").json()["total"] == 3
    assert adm.post(f"/api/v1/fagos/{f1}/aprobar").status_code == 403
    assert adm.patch(f"/api/v1/fagos/{f1}", json={"nombre": "x"}).status_code == 403
    assert mic.post(f"/api/v1/fagos/{f1}/aprobar").json()["estado_curaduria"] == "aprobado"
    assert mic.post(f"/api/v1/fagos/{f2}/descartar").json()["estado_curaduria"] == "descartado"
    assert mic.get("/api/v1/fagos", params={"estado_curaduria": "aprobado"}).json()["total"] == 1
    assert mic.get("/api/v1/fagos", params={"estado_curaduria": "raro"}).status_code == 422


def test_editar_metadatos_y_filtrar_por_ciclo_de_vida_y_hospedador(como, engine):
    f1, *_ = _fagos(engine)
    mic = como("mic")
    r = mic.patch(f"/api/v1/fagos/{f1}", json={"ciclo_vida": "litico", "familia": "Autographiviridae"})
    assert r.status_code == 200 and r.json()["ciclo_vida"] == "litico"
    assert mic.patch(f"/api/v1/fagos/{f1}", json={"ciclo_vida": "magico"}).status_code == 422
    assert mic.get("/api/v1/fagos", params={"ciclo_vida": "litico"}).json()["total"] == 1
    assert mic.get("/api/v1/fagos", params={"hospedador": "pneumoniae"}).json()["total"] == 3
    assert mic.get("/api/v1/fagos", params={"hospedador": "coli"}).json()["total"] == 0


def test_aprobar_en_lote_y_toda_curaduria_queda_en_la_auditoria(como, engine):
    ids = _fagos(engine)
    mic = como("mic")
    r = mic.post("/api/v1/fagos/lote", json={"accion": "aprobar", "ids": [str(i) for i in ids]})
    assert r.json() == {"actualizados": 3, "solicitados": 3}
    assert mic.post("/api/v1/fagos/lote", json={"accion": "borrar", "ids": [str(ids[0])]}).status_code == 422
    mic.patch(f"/api/v1/fagos/{ids[0]}", json={"familia": "X"})
    with Session(engine) as s:
        acciones = [e.accion for e in s.scalars(select(Auditoria).where(Auditoria.entidad == "fago"))]
        curado = s.get(Fago, ids[0])
        assert curado.curado_por is not None and curado.curado_en is not None
    assert acciones.count("fago_aprobado") == 3 and acciones.count("fago_modificado") == 1


def test_el_detalle_del_fago_trae_sus_interacciones_conocidas(como, engine):
    from app.models import InteraccionConocida
    f1, *_ = _fagos(engine)
    with Session(engine) as s:
        s.add(InteraccionConocida(fago_id=f1, especie_hospedador="Klebsiella pneumoniae", cepa="K1", locus_k_tipo="KL2", resultado="infecta",
                                  fuente="prueba", fuente_version="1", referencia="ref"))
        s.commit()
    d = como("mic").get(f"/api/v1/fagos/{f1}").json()
    assert d["interacciones"][0]["locus_k_tipo"] == "KL2" and d["interacciones"][0]["fuente"] == "prueba"


# ------------------------------------------------------------------ modelo
def test_el_modelo_vigente_muestra_version_fecha_y_metricas(como, monkeypatch):
    # El modelo vigente son los archivos de ml/models: aquí se simula que `leer_ficha` no los encuentra y luego que sí.
    mic = como("mic")
    monkeypatch.setattr(ruta_modelo, "leer_ficha", lambda carpeta: None)
    sin = mic.get("/api/v1/modelo").json()
    assert sin["disponible"] is False and "Todavía no hay un modelo" in sin["mensaje"]
    monkeypatch.setattr(ruta_modelo, "leer_ficha", lambda carpeta: {
        "version": "v1", "algoritmo": "XGBoost", "entrenado_en": "2026-11-01T00:00:00+00:00", "n_entrenamiento": 500,
        "metricas": {"top5": 0.8, "auc": 0.77}, "parametros": {}})
    con = como("adm").get("/api/v1/modelo").json()
    assert con["disponible"] is True and con["version"] == "v1" and con["metricas"]["auc"] == 0.77 and con["entrenado_en"]
    assert como("tec").get("/api/v1/modelo").status_code == 403
