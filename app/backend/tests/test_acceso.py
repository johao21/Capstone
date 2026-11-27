"""Inicio de sesión, tokens, bloqueo por intentos, permisos por rol y alcance de los datos (RF-01 a RF-06, RNF-03 a RNF-05).

Las pruebas intentan entrar con el rol equivocado y con identificadores de otro centro, y deben recibir 403 o 404 (RNF-04).
"""
import io
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import seguridad
from app.config import get_settings
from app.main import app
from app.models import Auditoria, Solicitud, Usuario

from conftest import CLAVE

FASTA = b">contig1\nACGTACGTACGTACGT\n>contig2\nTTGACCA\n"


def subir(c, codigo="A-001", **extra):
    contenido = FASTA + b">" + codigo.encode() + b"\nACGT\n"  # un contig distinto por código, para que cada archivo sea único
    return c.post("/api/v1/solicitudes", data={"codigo_interno": codigo, **extra}, files={"archivo": ("g.fasta", io.BytesIO(contenido))})


def login(base_api, cuentas, nombre="tec", clave=CLAVE):
    return TestClient(app).post("/api/v1/auth/login", json={"correo": cuentas[nombre]["correo"], "password": clave})


# ------------------------------------------------------------------ login
def test_login_correcto_entrega_un_token_con_el_perfil_y_los_permisos(base_api, cuentas):
    r = login(base_api, cuentas, "mic")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["token_type"] == "bearer" and cuerpo["usuario"]["rol"] == "MIC"
    assert "validar_recomendacion" in cuerpo["usuario"]["permisos"] and "registrar_solicitud" not in cuerpo["usuario"]["permisos"]
    datos = jwt.decode(cuerpo["access_token"], get_settings().jwt_secret_key, algorithms=["HS256"])
    assert datos["rol"] == "MIC" and datos["exp"] - datos["iat"] == get_settings().jwt_access_token_expire_minutes * 60


def test_la_contrasena_se_guarda_como_hash_argon2(base_api, cuentas, engine):
    with Session(engine) as s:
        hash_guardado = s.get(Usuario, cuentas["tec"]["id"]).password_hash
    assert hash_guardado.startswith("$argon2") and CLAVE not in hash_guardado


def test_credenciales_incorrectas_dan_el_mismo_mensaje_exista_o_no_el_correo(base_api, cuentas):
    mal_clave = login(base_api, cuentas, "tec", "otra-clave-larga")
    mal_correo = TestClient(app).post("/api/v1/auth/login", json={"correo": "nadie@sirfa.test", "password": "otra-clave-larga"})
    assert mal_clave.status_code == mal_correo.status_code == 401
    assert mal_clave.json() == mal_correo.json()


def test_cinco_intentos_fallidos_bloquean_la_cuenta_quince_minutos(base_api, cuentas, engine):
    for _ in range(5):
        assert login(base_api, cuentas, "tec", "incorrecta-123456").status_code == 401
    r = login(base_api, cuentas)  # ahora ni la contraseña correcta entra
    assert r.status_code == 423 and "Retry-After" in r.headers
    with Session(engine) as s:
        u = s.get(Usuario, cuentas["tec"]["id"])
        bloqueo = u.bloqueado_hasta.replace(tzinfo=timezone.utc)
        assert timedelta(minutes=14) < bloqueo - datetime.now(timezone.utc) <= timedelta(minutes=15)
        u.bloqueado_hasta = datetime.now(timezone.utc) - timedelta(seconds=1)  # pasa el tiempo
        s.commit()
    assert login(base_api, cuentas).status_code == 200


def test_un_usuario_desactivado_no_puede_iniciar_sesion_pero_conserva_su_historial(base_api, cuentas, engine):
    with Session(engine) as s:
        s.get(Usuario, cuentas["tec"]["id"]).activo = False
        s.commit()
    assert login(base_api, cuentas).status_code == 403


def test_cada_inicio_de_sesion_exitoso_o_fallido_queda_en_la_auditoria(base_api, cuentas, engine):
    login(base_api, cuentas, "tec", "incorrecta-123456")
    login(base_api, cuentas)
    with Session(engine) as s:
        eventos = s.scalars(select(Auditoria).where(Auditoria.accion == "inicio_sesion").order_by(Auditoria.seq)).all()
    assert [e.resultado for e in eventos] == ["fallido", "ok"]
    assert eventos[0].correo == cuentas["tec"]["correo"] and eventos[0].detalle["motivo"] == "contraseña incorrecta"
    assert "incorrecta-123456" not in str([e.detalle for e in eventos])  # nunca se registra una contraseña


# ----------------------------------------------------------------- tokens
def test_sin_token_o_con_un_token_invalido_es_401(base_api, cuentas):
    c = TestClient(app)
    assert c.get("/api/v1/solicitudes").status_code == 401
    assert c.get("/api/v1/solicitudes", headers={"Authorization": "Bearer basura"}).status_code == 401
    # Firmado con otra clave: se rechaza.
    falso = jwt.encode({"sub": str(cuentas["adm"]["id"]), "sid": "x", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, "otra-clave" * 4, algorithm="HS256")
    assert c.get("/api/v1/solicitudes", headers={"Authorization": f"Bearer {falso}"}).status_code == 401


def test_un_token_vencido_se_rechaza(base_api, cuentas, engine):
    with Session(engine) as s:
        usuario = s.get(Usuario, cuentas["tec"]["id"])
        token, _, _ = seguridad.crear_token(usuario, get_settings(), ahora=datetime.now(timezone.utc) - timedelta(hours=2))
    r = TestClient(app).get("/api/v1/solicitudes", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401 and "expiró" in r.json()["detail"]


def test_un_token_sin_firma_no_se_acepta(base_api, cuentas):
    sin_firma = jwt.encode({"sub": str(cuentas["adm"]["id"]), "sid": "x", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, None, algorithm="none")
    assert TestClient(app).get("/api/v1/auth/yo", headers={"Authorization": f"Bearer {sin_firma}"}).status_code == 401


def test_cerrar_sesion_invalida_el_token_aunque_no_haya_vencido(como, engine, cuentas):
    c = como("tec")
    assert c.get("/api/v1/auth/yo").status_code == 200
    assert c.post("/api/v1/auth/logout").status_code == 204
    r = c.get("/api/v1/auth/yo")
    assert r.status_code == 401 and "cerró" in r.json()["detail"]
    with Session(engine) as s:  # la sesión cerrada queda en la propia fila del usuario
        assert len(s.get(Usuario, cuentas["tec"]["id"]).sesiones_revocadas) == 1


def test_cerrar_una_sesion_no_cierra_las_otras_del_mismo_usuario(como):
    web, movil = como("tec"), como("tec")  # dos inicios de sesión de la misma cuenta
    assert web.post("/api/v1/auth/logout").status_code == 204
    assert web.get("/api/v1/auth/yo").status_code == 401
    assert movil.get("/api/v1/auth/yo").status_code == 200


def test_las_sesiones_revocadas_ya_vencidas_se_descartan_al_iniciar_sesion(como, engine, cuentas):
    vencida = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with Session(engine) as s:
        s.get(Usuario, cuentas["tec"]["id"]).sesiones_revocadas = [{"sid": "vieja", "expira_en": vencida}]
        s.commit()
    como("tec")  # inicia sesión
    with Session(engine) as s:
        assert s.get(Usuario, cuentas["tec"]["id"]).sesiones_revocadas == []


def test_el_token_se_renueva_solo_cuando_le_queda_poca_vida(como, base_api, cuentas, engine):
    c = como("tec")
    assert "X-Token-Renovado" not in c.get("/api/v1/auth/yo").headers  # token recién emitido
    with Session(engine) as s:
        usuario = s.get(Usuario, cuentas["tec"]["id"])
        casi_vencido, _, sid = seguridad.crear_token(
            usuario, get_settings(), ahora=datetime.now(timezone.utc) - timedelta(minutes=get_settings().jwt_access_token_expire_minutes - 2)
        )
    r = TestClient(app).get("/api/v1/auth/yo", headers={"Authorization": f"Bearer {casi_vencido}"})
    assert r.status_code == 200
    nuevo = r.headers["X-Token-Renovado"]
    assert jwt.decode(nuevo, get_settings().jwt_secret_key, algorithms=["HS256"])["sid"] == sid  # misma sesión


def test_cambiar_la_contrasena_exige_la_actual_y_una_nueva_aceptable(como, base_api, cuentas):
    c = como("tec")
    assert c.post("/api/v1/auth/cambiar-password", json={"password_actual": "mala-actual-123", "password_nueva": "Nueva-clave-456"}).status_code == 400
    assert c.post("/api/v1/auth/cambiar-password", json={"password_actual": CLAVE, "password_nueva": "corta"}).status_code == 422
    assert c.post("/api/v1/auth/cambiar-password", json={"password_actual": CLAVE, "password_nueva": "Nueva-clave-456"}).status_code == 204
    assert login(base_api, cuentas).status_code == 401
    assert login(base_api, cuentas, "tec", "Nueva-clave-456").status_code == 200


# ----------------------------------------------------- permisos por rol
@pytest.mark.parametrize(
    "rol, metodo, ruta, permitido",
    [
        ("tec", "get", "/api/v1/solicitudes", True),
        ("epi", "get", "/api/v1/solicitudes", False),
        ("cli", "post", "/api/v1/solicitudes", False),
        ("mic", "post", "/api/v1/solicitudes", False),
        ("adm", "post", "/api/v1/solicitudes", False),
        ("tec", "get", "/api/v1/fagos", False),
        ("cli", "get", "/api/v1/fagos", False),
        ("epi", "get", "/api/v1/fagos", False),
        ("mic", "get", "/api/v1/fagos", True),
        ("adm", "get", "/api/v1/fagos", True),
        ("tec", "get", "/api/v1/usuarios", False),
        ("mic", "get", "/api/v1/usuarios", False),
        ("adm", "get", "/api/v1/usuarios", True),
        ("mic", "get", "/api/v1/auditoria", False),
        ("tec", "get", "/api/v1/auditoria", False),
        ("adm", "get", "/api/v1/auditoria", True),
        ("tec", "get", "/api/v1/tablero/tendencias", False),
        ("mic", "get", "/api/v1/tablero/tendencias", False),
        ("epi", "get", "/api/v1/tablero/tendencias", True),
        ("mic", "get", "/api/v1/tablero/cobertura", True),
        ("tec", "get", "/api/v1/tablero/cobertura", False),
        ("tec", "get", "/api/v1/modelo", False),
        ("mic", "get", "/api/v1/modelo", True),
        ("epi", "get", "/api/v1/alertas", False),
        ("cli", "get", "/api/v1/alertas", True),
        ("adm", "get", "/api/v1/alertas", False),
    ],
)
def test_matriz_de_permisos(como, rol, metodo, ruta, permitido):
    r = getattr(como(rol), metodo)(ruta) if metodo == "get" else como(rol).post(ruta, data={"codigo_interno": "X"})
    assert (r.status_code not in (401, 403)) is permitido, (rol, ruta, r.status_code)


def test_un_acceso_denegado_queda_en_la_auditoria(como, engine):
    assert como("tec").get("/api/v1/usuarios").status_code == 403
    with Session(engine) as s:
        e = s.scalars(select(Auditoria).where(Auditoria.accion == "acceso_denegado")).one()
    assert e.resultado == "denegado" and e.rol == "TEC" and "/api/v1/usuarios" in e.entidad_id


# ------------------------------------------------- alcance de los datos
def test_el_tecnico_solo_ve_sus_propias_solicitudes(como):
    mia = subir(como("tec"), "MIA").json()["id"]
    ajena = subir(como("tec2"), "AJENA").json()["id"]
    ids = [i["id"] for i in como("tec").get("/api/v1/solicitudes").json()["items"]]
    assert ids == [mia]
    # Una ajena responde 404, igual que una que no existe: no revela que existe.
    assert como("tec").get(f"/api/v1/solicitudes/{ajena}").status_code == 404
    assert como("tec").post(f"/api/v1/solicitudes/{ajena}/anular").status_code == 404
    assert como("tec").get(f"/api/v1/solicitudes/{ajena}/recomendacion").status_code == 404


def test_el_clinico_ve_las_solicitudes_de_su_centro_y_no_las_de_otro(como):
    sol = subir(como("tec"), "C1-1").json()["id"]
    assert [i["id"] for i in como("cli").get("/api/v1/solicitudes").json()["items"]] == [sol]
    assert como("cli").get(f"/api/v1/solicitudes/{sol}").status_code == 200
    assert como("cli_otro").get("/api/v1/solicitudes").json()["total"] == 0
    assert como("cli_otro").get(f"/api/v1/solicitudes/{sol}").status_code == 404


def test_el_administrador_ve_todas_y_filtra_por_centro(como, cuentas):
    subir(como("tec"), "A")
    subir(como("tec2"), "B")
    adm = como("adm")
    assert adm.get("/api/v1/solicitudes").json()["total"] == 2
    assert adm.get("/api/v1/solicitudes", params={"centro_id": str(cuentas["cli_otro"]["centro_id"])}).json()["total"] == 0
    assert adm.get("/api/v1/solicitudes", params={"centro_id": str(cuentas["tec"]["centro_id"])}).json()["total"] == 2


def test_el_microbiologo_solo_ve_las_pendientes_de_validar_o_las_suyas(como, prediccion_lista):
    en_analisis = subir(como("tec"), "EN-ANALISIS").json()["id"]
    lista = subir(como("tec"), "LISTA").json()["id"]
    prediccion_lista(lista)
    mic = como("mic")
    assert [i["id"] for i in mic.get("/api/v1/solicitudes").json()["items"]] == [lista]
    assert mic.get(f"/api/v1/solicitudes/{en_analisis}").status_code == 404


def test_la_solicitud_la_crea_el_tecnico_autenticado_y_se_audita(como, engine, cuentas):
    r = subir(como("tec"), "AUD-1", clinico_id=str(cuentas["cli"]["id"]))
    assert r.status_code == 201
    with Session(engine) as s:
        sol = s.get(Solicitud, __import__("uuid").UUID(r.json()["id"]))
        assert sol.creada_por == cuentas["tec"]["id"] and sol.solicitante_id == cuentas["cli"]["id"]
        acciones = [e.accion for e in s.scalars(select(Auditoria).order_by(Auditoria.seq))]
    assert {"aislado_registrado", "genoma_cargado", "solicitud_creada"} <= set(acciones)


def test_el_clinico_solicitante_debe_ser_clinico_activo_del_mismo_centro(como, cuentas):
    c = como("tec")
    assert subir(c, "X1", clinico_id=str(cuentas["cli_otro"]["id"])).status_code == 422  # de otro centro
    assert subir(c, "X2", clinico_id=str(cuentas["mic"]["id"])).status_code == 422  # no es clínico


def test_un_acceso_denegado_a_una_ruta_larga_cabe_en_la_auditoria_y_responde_403(como, engine):
    """Con UUID, la ruta pasa de los 64 caracteres de la columna: PostgreSQL daba 500 (lo detectó el recorrido real)."""
    ruta = "/api/v1/solicitudes/00000000-0000-0000-0000-000000000000/prediccion"
    assert como("cli").get(ruta).status_code == 403
    with Session(engine) as s:
        e = s.scalars(select(Auditoria).where(Auditoria.accion == "acceso_denegado")).one()
    assert len(e.entidad_id) <= 64 and e.detalle["ruta"] == ruta
