"""Pruebas de la API REST de solicitudes y del banco de fagos, con SQLite en memoria.
El análisis genómico no se ejecuta: `agregar_analisis` lo inserta directamente. Los clientes ya vienen
autenticados (ver conftest.py): `cliente` es un técnico y `como("mic")` un microbiólogo."""
import io
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnalisisGenomico, Fago, FuenteDatos, InteraccionConocida, Solicitud, Trabajo
from app.routers import solicitudes as ruta_solicitudes

# FASTA mínimo y válido: dos contigs de ADN.
FASTA = b">contig1\nACGTACGTACGTACGT\n>contig2\nTTGACCA\n"


def subir(cliente, codigo="A-001", contenido=FASTA, nombre="mi genoma.fasta", **extra):
    """Sube un FASTA a `POST /api/v1/solicitudes` como lo haría el formulario web; `extra` agrega campos del formulario."""
    datos = {"codigo_interno": codigo, **extra}
    return cliente.post("/api/v1/solicitudes", data=datos, files={"archivo": (nombre, io.BytesIO(contenido))})


def agregar_analisis(engine, solicitud_id, locus="KL52", confianza="Typeable"):
    """Inserta un análisis genómico ya hecho, para probar la API sin ejecutar el pipeline."""
    with Session(engine) as s:
        s.add(
            AnalisisGenomico(
                solicitud_id=uuid.UUID(solicitud_id),
                especie_detectada="Klebsiella pneumoniae",
                distancia_especie=0.01,
                locus_k_tipo=locus,
                locus_k_confianza=confianza,
                n_genes=5455,
                n_proteinas=5455,
                versiones_herramientas={"prodigal": "2.6.3"},
                parametros={"especie_verificada": True, "especie_referencia": "GCF_000240185.1"},
            )
        )
        s.commit()


def agregar_fago(engine, accesion="NC_000001", nombre="Klebsiella phage X", **extra):
    """Inserta un fago en el banco y devuelve su id."""
    with Session(engine) as s:
        fago = Fago(accesion=accesion, nombre=nombre, **extra)
        s.add(fago)
        s.commit()
        return fago.id


# ------------------------------------------------------------------ crear
def test_crear_registra_la_solicitud_y_encola_el_pipeline(cliente, engine, tmp_path):
    r = subir(cliente, tipo_muestra="sangre", mecanismo_resistencia="KPC")
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["estado"] == "registrada"
    assert cuerpo["etapa"] == "En cola de análisis"
    assert cuerpo["codigo_interno"] == "A-001"
    with Session(engine) as s:
        trabajo = s.execute(select(Trabajo)).scalar_one()
        assert trabajo.tipo == "pipeline" and trabajo.estado == "pendiente"
    guardados = [p.name for p in (tmp_path / "genomas").iterdir()]
    assert len(guardados) == 1 and guardados[0].endswith(".fasta") and " " not in guardados[0]  # solo el archivo por hash, sin temporales


def test_crear_rechaza_un_fasta_invalido_sin_dejar_registros(cliente, engine):
    r = subir(cliente, contenido=b"esto no es un fasta\n")
    assert r.status_code == 422
    assert "FASTA inválido" in r.json()["detail"]
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Solicitud)) == 0


@pytest.mark.parametrize(
    "extra, texto",
    [
        ({"tipo_muestra": "saliva"}, "tipo_muestra"),
        ({"mecanismo_resistencia": "magia"}, "mecanismo_resistencia"),
        ({"fecha_aislamiento": "2999-01-01"}, "futura"),
        ({"codigo": "   "}, "código interno"),
    ],
)
def test_crear_valida_los_campos(cliente, extra, texto):
    codigo = extra.pop("codigo", "A-001")
    r = subir(cliente, codigo=codigo, **extra)
    assert r.status_code == 422
    assert texto in str(r.json()["detail"])


def test_crear_rechaza_una_extension_no_admitida(cliente):
    r = subir(cliente, nombre="genoma.exe")
    assert r.status_code == 422
    assert "Formato no admitido" in r.json()["detail"]


def test_crear_rechaza_un_archivo_vacio(cliente):
    assert subir(cliente, contenido=b"").status_code == 422


def test_crear_rechaza_un_archivo_demasiado_grande(cliente, monkeypatch):
    monkeypatch.setattr(ruta_solicitudes, "TAMANO_MAXIMO", 10)
    assert subir(cliente).status_code == 413


def test_un_codigo_repetido_en_el_centro_es_conflicto(cliente):
    assert subir(cliente, codigo="DUP").status_code == 201
    # Contenido distinto con el mismo código: lo que choca es el código del aislado, no el archivo.
    r = subir(cliente, codigo="DUP", contenido=FASTA + b">otro\nGGGG\n")
    assert r.status_code == 409


# ------------------------------------------------------ listar y detalle
def test_listar_filtra_por_estado_y_ordena_las_mas_recientes_primero(cliente):
    primera = subir(cliente, codigo="A").json()["id"]
    segunda = subir(cliente, codigo="B", contenido=FASTA + b">x\nAAAA\n").json()["id"]
    cliente.post(f"/api/v1/solicitudes/{primera}/anular")
    todas = cliente.get("/api/v1/solicitudes").json()
    assert todas["total"] == 2 and [i["id"] for i in todas["items"]] == [segunda, primera]
    anuladas = cliente.get("/api/v1/solicitudes", params={"estado": "anulada"}).json()
    assert [i["id"] for i in anuladas["items"]] == [primera]
    assert cliente.get("/api/v1/solicitudes", params={"estado": "inventado"}).status_code == 422


def test_detalle_muestra_aislado_genoma_trabajos_e_historial(cliente):
    sol = subir(cliente, tipo_muestra="orina", observaciones="  urocultivo  ").json()
    d = cliente.get(f"/api/v1/solicitudes/{sol['id']}").json()
    assert d["aislado"]["tipo_muestra"] == "orina" and d["aislado"]["observaciones"] == "urocultivo"
    assert d["genoma"]["nombre_original"] == "mi_genoma.fasta" and len(d["genoma"]["sha256"]) == 64
    assert [t["tipo"] for t in d["trabajos"]] == ["pipeline"]
    assert [h["estado_nuevo"] for h in d["historial"]] == ["registrada"]
    assert d["analisis"] is None


def test_detalle_con_analisis_indica_que_se_esta_generando_la_prediccion(cliente, engine):
    sol = subir(cliente).json()
    agregar_analisis(engine, sol["id"])
    with Session(engine) as s:
        s.get(Solicitud, uuid.UUID(sol["id"])).estado = "en_analisis"
        s.commit()
    d = cliente.get(f"/api/v1/solicitudes/{sol['id']}").json()
    assert d["analisis"]["locus_k_tipo"] == "KL52" and d["analisis"]["especie_verificada"] is True
    assert d["etapa"] == "Análisis genómico completo; generando la predicción"


def test_detalle_de_una_solicitud_inexistente_es_404(cliente):
    assert cliente.get("/api/v1/solicitudes/00000000-0000-0000-0000-000000000000").status_code == 404
    assert cliente.get("/api/v1/solicitudes/no-es-un-uuid").status_code == 422


# ------------------------------------------------------ anular y reintentar
def test_anular_cancela_el_trabajo_pendiente_y_no_se_puede_repetir(cliente, engine):
    sol = subir(cliente).json()
    r = cliente.post(f"/api/v1/solicitudes/{sol['id']}/anular", json={"motivo": "duplicada"})
    assert r.status_code == 200 and r.json()["estado"] == "anulada" and r.json()["motivo_estado"] == "duplicada"
    with Session(engine) as s:
        assert s.execute(select(Trabajo)).scalar_one().estado == "fallido"
    assert cliente.post(f"/api/v1/solicitudes/{sol['id']}/anular").status_code == 409


def test_reintentar_solo_aplica_a_solicitudes_con_error(cliente, engine):
    sol = subir(cliente).json()
    assert cliente.post(f"/api/v1/solicitudes/{sol['id']}/reintentar").status_code == 409
    with Session(engine) as s:
        s.get(Solicitud, uuid.UUID(sol["id"])).estado = "error"
        trabajo = s.execute(select(Trabajo)).scalar_one()
        trabajo.estado = "fallido"
        s.commit()
    assert cliente.post(f"/api/v1/solicitudes/{sol['id']}/reintentar").status_code == 200
    with Session(engine) as s:
        assert sorted(t.estado for t in s.execute(select(Trabajo)).scalars()) == ["fallido", "pendiente"]
    assert cliente.post(f"/api/v1/solicitudes/{sol['id']}/reintentar").status_code == 409  # ya hay uno en cola


# ----------------------------------------------------------- recomendación
def test_recomendacion_antes_del_analisis(cliente):
    sol = subir(cliente).json()
    r = cliente.get(f"/api/v1/solicitudes/{sol['id']}/recomendacion").json()
    assert r["estado"] == "analisis_pendiente" and r["candidatos"] == []
    assert "no diagnostica ni prescribe" in r["aviso"]


def test_recomendacion_sin_interacciones_cargadas_no_inventa_un_ranking(cliente, engine):
    sol = subir(cliente).json()
    agregar_analisis(engine, sol["id"])
    for i in range(3):
        agregar_fago(engine, accesion=f"NC_{i}", nombre=f"fago {i}")
    r = cliente.get(f"/api/v1/solicitudes/{sol['id']}/recomendacion").json()
    assert r["estado"] == "sin_evidencia" and r["candidatos"] == []
    assert r["banco"] == {"fagos_total": 3, "fagos_curados": 0, "fagos_con_ciclo_de_vida": 0, "interacciones_conocidas": 0}
    assert "ninguna interacción" in r["mensaje"]
    assert r["perfil"]["locus_k_tipo"] == "KL52"


def test_recomendacion_con_locus_no_tipificado(cliente, engine):
    sol = subir(cliente).json()
    # Un locus que Kaptive no logró tipificar: no debe usarse para buscar evidencia.
    agregar_analisis(engine, sol["id"], locus="unknown (best match: KL1)", confianza="Untypeable")
    r = cliente.get(f"/api/v1/solicitudes/{sol['id']}/recomendacion").json()
    assert r["estado"] == "sin_evidencia" and "no se pudo tipificar" in r["mensaje"]


def test_recomendacion_ordena_por_tasa_positiva_y_excluye_lo_sin_evidencia_positiva(cliente, engine):
    sol = subir(cliente).json()
    agregar_analisis(engine, sol["id"], locus="KL52")
    bueno = agregar_fago(engine, accesion="NC_A", nombre="Klebsiella phage A")
    medio = agregar_fago(engine, accesion="NC_B", nombre="Klebsiella phage B")
    malo = agregar_fago(engine, accesion="NC_C", nombre="Klebsiella phage C")
    descartado = agregar_fago(engine, accesion="NC_D", nombre="Klebsiella phage D", estado_curaduria="descartado")
    with Session(engine) as s:
        fuente = FuenteDatos(nombre="prueba", version="1")
        s.add(fuente)
        s.flush()

        def inter(fago, resultado, locus="KL52", cepa="c"):
            s.add(InteraccionConocida(fago_id=fago, especie_hospedador="Klebsiella pneumoniae", cepa=cepa, locus_k_tipo=locus,
                                      resultado=resultado, fuente_id=fuente.id, referencia="ref-1"))

        inter(bueno, "infecta", cepa="c1")
        inter(bueno, "infecta", cepa="c2")
        inter(medio, "infecta", cepa="c1")
        inter(medio, "no_infecta", cepa="c2")
        inter(malo, "no_infecta")
        inter(descartado, "infecta")
        inter(bueno, "no_infecta", locus="KL1")  # otro locus: no debe contar
        s.commit()
    r = cliente.get(f"/api/v1/solicitudes/{sol['id']}/recomendacion").json()
    assert r["estado"] == "evidencia_disponible"
    assert [c["accesion"] for c in r["candidatos"]] == ["NC_A", "NC_B"]
    assert r["candidatos"][0]["tasa_positiva"] == 1.0 and r["candidatos"][1]["tasa_positiva"] == 0.5
    assert r["candidatos"][0]["referencias"] == ["ref-1"]


def test_recomendacion_de_una_solicitud_rechazada_no_aplica(cliente):
    sol = subir(cliente).json()
    cliente.post(f"/api/v1/solicitudes/{sol['id']}/anular")
    assert cliente.get(f"/api/v1/solicitudes/{sol['id']}/recomendacion").json()["estado"] == "no_aplica"


# --------------------------------------------------------- banco y resumen
def test_buscar_fagos_por_texto_y_paginar(como, engine):
    cliente = como("mic")
    agregar_fago(engine, accesion="NC_1", nombre="Klebsiella phage Alfa", genero="Przondovirus")
    agregar_fago(engine, accesion="NC_2", nombre="Klebsiella phage Beta", familia="Autographiviridae")
    agregar_fago(engine, accesion="NC_3", nombre="Klebsiella phage Gamma")
    todos = cliente.get("/api/v1/fagos", params={"limite": 2}).json()
    assert todos["total"] == 3 and len(todos["items"]) == 2
    assert cliente.get("/api/v1/fagos", params={"q": "ALFA"}).json()["total"] == 1
    assert cliente.get("/api/v1/fagos", params={"q": "autograph"}).json()["items"][0]["accesion"] == "NC_2"
    assert cliente.get("/api/v1/fagos", params={"q": "zzz"}).json()["total"] == 0


def test_resumen_cuenta_solicitudes_por_estado(cliente, engine):
    subir(cliente, codigo="A")
    anulada = subir(cliente, codigo="B", contenido=FASTA + b">x\nAAAA\n").json()["id"]
    cliente.post(f"/api/v1/solicitudes/{anulada}/anular")
    agregar_fago(engine)
    r = cliente.get("/api/v1/resumen").json()
    assert r["solicitudes_por_estado"] == {"registrada": 1, "anulada": 1}
    assert r["banco"]["fagos_total"] == 1


def test_la_web_se_sirve_desde_la_raiz_y_no_tapa_la_api(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and "SIRFA" in r.text
    assert cliente.get("/api/v1/resumen").headers["content-type"].startswith("application/json")
    for modulo in ("main", "base", "v_solicitudes"):
        r = cliente.get(f"/js/{modulo}.js")
        assert r.status_code == 200 and "javascript" in r.headers["content-type"]
