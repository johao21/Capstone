"""Simplificación a 12 tablas (solicitud de cambio SC-07): ocho tablas de detalle pasan a columnas o a JSON.

Qué se absorbe y dónde queda:

- `genoma`                  -> columnas de `aislado` (el genoma es 1:1 con el aislado).
- `analisis_genomico`       -> columnas de `solicitud` (`especie_detectada`, `locus_k_tipo`, ..., `detalle_analisis`, `analizado_en`).
- `fuente_datos`            -> `interaccion_conocida.fuente` y `fuente_version` (texto).
- `fago_origen`             -> `fago.origenes` (lista JSONB, con la fuente y su versión dentro de cada entrada).
- `modelo_prediccion`       -> `prediccion.modelo_version` y `prediccion.modelo` (copia de la ficha del modelo usado).
- `recomendacion_candidato` -> `recomendacion_emitida.candidatos` (lista JSONB).
- `sesion_revocada`         -> `usuario.sesiones_revocadas` (lista JSONB).
- `solicitud_historial`     -> se lee de `auditoria` (cada cambio de estado ya deja allí su evento `cambio_estado`);
                               la fila de creación sale de la propia solicitud.

Los datos se copian antes de borrar cada tabla. Lo que no se copia, a propósito:

- `solicitud_historial`: no se inserta nada en `auditoria` (es de solo adición y está encadenada por hashes); el historial de las
  solicitudes ya existentes se reconstruye con los eventos que la auditoría ya tiene.
- `sesion_revocada`: la tabla no sabía de qué usuario era cada sesión. Una sesión cerrada justo antes de migrar vuelve a servir
  hasta que venza su token (como mucho lo que dura una sesión, 60 minutos por defecto).
- Si un análisis se había repetido para una misma solicitud, se conserva el más reciente.

El retroceso (`downgrade`) recrea las ocho tablas con las definiciones de las instantáneas 0001 y 0002 y reconstruye sus filas a
partir de lo que dejó esta migración; el historial se reconstruye desde la auditoría y las sesiones revocadas se copian de vuelta.
"""
import re
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB
VACIO_OBJ = sa.text("'{}'::jsonb")
VACIO_LISTA = sa.text("'[]'::jsonb")

# Columnas del genoma que pasan a `aislado`: (nombre, tipo, obligatoria).
COLUMNAS_GENOMA = (
    ("ruta_archivo", sa.String(500), True),
    ("sha256", sa.String(64), True),
    ("tamano_bytes", sa.BigInteger(), True),
    ("nombre_original", sa.String(255), True),
    ("qc_longitud", sa.BigInteger(), False),
    ("qc_contigs", sa.Integer(), False),
    ("qc_n50", sa.Integer(), False),
    ("qc_gc", sa.Float(), False),
    ("qc_prop_ambiguas", sa.Float(), False),
    ("qc_resultado", sa.String(12), False),
    ("cargado_en", sa.DateTime(timezone=True), True),
)
NOMBRES_GENOMA = ", ".join(n for n, _, _ in COLUMNAS_GENOMA)

# Tablas que el retroceso recrea desde las instantáneas de DDL, en un orden que respeta las claves foráneas.
TABLAS_DE_INSTANTANEAS = (
    "sesion_revocada",
    "modelo_prediccion",
    "fuente_datos",
    "genoma",
    "solicitud_historial",
    "fago_origen",
    "recomendacion_candidato",
)


def upgrade() -> None:
    """Agrega las columnas nuevas, copia los datos, quita las claves foráneas viejas y borra las ocho tablas."""
    # ---- usuario: sesiones revocadas
    op.add_column("usuario", sa.Column("sesiones_revocadas", JSONB(), nullable=False, server_default=VACIO_LISTA))

    # ---- aislado absorbe genoma (cada solicitud apunta a su genoma; los aislados sin solicitud toman el más reciente de los suyos)
    for nombre, tipo, _ in COLUMNAS_GENOMA:
        op.add_column("aislado", sa.Column(nombre, tipo, nullable=True))
    asignar = ", ".join(f"{n} = g.{n}" for n, _, _ in COLUMNAS_GENOMA)
    op.execute(f"UPDATE aislado a SET {asignar} FROM solicitud s JOIN genoma g ON g.id = s.genoma_id WHERE s.aislado_id = a.id")
    op.execute(
        f"UPDATE aislado a SET {asignar} FROM (SELECT DISTINCT ON (aislado_id) * FROM genoma ORDER BY aislado_id, cargado_en DESC) g "
        "WHERE g.aislado_id = a.id AND a.ruta_archivo IS NULL"
    )
    for nombre, _, obligatoria in COLUMNAS_GENOMA:
        if obligatoria:
            op.alter_column("aislado", nombre, nullable=False)
    op.create_check_constraint(
        op.f("ck_aislado_qc_resultado"), "aislado", "qc_resultado IN ('aprobado', 'advertencia', 'rechazado')"
    )

    # ---- solicitud absorbe analisis_genomico (el análisis más reciente de cada solicitud)
    op.add_column("solicitud", sa.Column("especie_detectada", sa.String(120)))
    op.add_column("solicitud", sa.Column("distancia_especie", sa.Float()))
    op.add_column("solicitud", sa.Column("locus_k_tipo", sa.String(20)))
    op.add_column("solicitud", sa.Column("locus_k_confianza", sa.String(40)))
    op.add_column("solicitud", sa.Column("n_genes", sa.Integer()))
    op.add_column("solicitud", sa.Column("n_proteinas", sa.Integer()))
    op.add_column("solicitud", sa.Column("versiones_herramientas", JSONB(), nullable=False, server_default=VACIO_OBJ))
    op.add_column("solicitud", sa.Column("parametros_analisis", JSONB(), nullable=False, server_default=VACIO_OBJ))
    op.add_column("solicitud", sa.Column("detalle_analisis", JSONB(), nullable=False, server_default=VACIO_OBJ))
    op.add_column("solicitud", sa.Column("analizado_en", sa.DateTime(timezone=True)))
    op.execute(
        """
        UPDATE solicitud s SET especie_detectada = a.especie_detectada, distancia_especie = a.distancia_especie,
               locus_k_tipo = a.locus_k_tipo, locus_k_confianza = a.locus_k_confianza, n_genes = a.n_genes,
               n_proteinas = a.n_proteinas, versiones_herramientas = a.versiones_herramientas,
               parametros_analisis = a.parametros, detalle_analisis = a.detalle, analizado_en = a.creado_en
        FROM (SELECT DISTINCT ON (solicitud_id) * FROM analisis_genomico ORDER BY solicitud_id, creado_en DESC) a
        WHERE a.solicitud_id = s.id
        """
    )
    op.drop_column("solicitud", "genoma_id")

    # ---- fago absorbe fago_origen y fuente_datos
    op.add_column("fago", sa.Column("origenes", JSONB(), nullable=False, server_default=VACIO_LISTA))
    op.execute(
        """
        UPDATE fago f SET origenes = o.lista FROM (
            SELECT fo.fago_id, jsonb_agg(jsonb_build_object('fuente', fd.nombre, 'version', fd.version, 'url', fd.url,
                   'id_externo', fo.id_externo, 'descargado_en', fo.descargado_en) ORDER BY fo.descargado_en) AS lista
            FROM fago_origen fo JOIN fuente_datos fd ON fd.id = fo.fuente_id GROUP BY fo.fago_id
        ) o WHERE o.fago_id = f.id
        """
    )

    # ---- interaccion_conocida: la fuente pasa a texto
    op.add_column("interaccion_conocida", sa.Column("fuente", sa.String(120)))
    op.add_column("interaccion_conocida", sa.Column("fuente_version", sa.String(80)))
    op.execute("UPDATE interaccion_conocida i SET fuente = fd.nombre, fuente_version = fd.version FROM fuente_datos fd WHERE fd.id = i.fuente_id")
    op.alter_column("interaccion_conocida", "fuente", nullable=False)
    op.alter_column("interaccion_conocida", "fuente_version", nullable=False)
    op.drop_column("interaccion_conocida", "fuente_id")

    # ---- prediccion: la ficha del modelo viaja con cada predicción
    op.add_column("prediccion", sa.Column("modelo_version", sa.String(40)))
    op.add_column("prediccion", sa.Column("modelo", JSONB(), nullable=False, server_default=VACIO_OBJ))
    op.execute(
        """
        UPDATE prediccion p SET modelo_version = m.version,
               modelo = jsonb_build_object('version', m.version, 'algoritmo', m.algoritmo, 'entrenado_en', m.entrenado_en,
                                           'n_entrenamiento', m.n_entrenamiento, 'metricas', m.metricas, 'parametros', m.parametros)
        FROM modelo_prediccion m WHERE m.id = p.modelo_id
        """
    )
    op.alter_column("prediccion", "modelo_version", nullable=False)
    op.drop_column("prediccion", "modelo_id")

    # ---- recomendacion_emitida absorbe recomendacion_candidato
    op.add_column("recomendacion_emitida", sa.Column("candidatos", JSONB(), nullable=False, server_default=VACIO_LISTA))
    op.execute(
        """
        UPDATE recomendacion_emitida r SET candidatos = c.lista FROM (
            SELECT recomendacion_id, jsonb_agg(jsonb_build_object('fago_id', fago_id::text, 'rango', rango, 'puntaje', puntaje,
                   'descartado', descartado, 'justificacion', justificacion, 'resultado_ensayo', resultado_ensayo) ORDER BY rango) AS lista
            FROM recomendacion_candidato GROUP BY recomendacion_id
        ) c WHERE c.recomendacion_id = r.id
        """
    )

    # ---- las ocho tablas ya no hacen falta (primero las que tienen claves foráneas hacia otras)
    for tabla in (
        "recomendacion_candidato",
        "solicitud_historial",
        "analisis_genomico",
        "fago_origen",
        "genoma",
        "fuente_datos",
        "modelo_prediccion",
        "sesion_revocada",
    ):
        op.drop_table(tabla)


def _recrear_desde_instantaneas(tablas) -> None:
    """Crea `tablas` (y sus índices) con el DDL de las instantáneas 0001 y 0002, en el orden dado."""
    sentencias: list[str] = []
    for archivo in ("0001_esquema_inicial.sql", "0002_acceso_auditoria_prediccion.sql"):
        sql = (Path(__file__).with_name(archivo)).read_text(encoding="utf-8")
        sentencias += [s.strip().rstrip(";") for s in sql.split(";\n\n") if s.strip()]
    conexion = op.get_bind()
    for tabla in tablas:
        for s in sentencias:
            if re.match(rf"CREATE TABLE {tabla} \(", s) or re.match(rf"CREATE (UNIQUE )?INDEX \S+ ON {tabla} ", s):
                conexion.exec_driver_sql(s)


def downgrade() -> None:
    """Recrea las ocho tablas, reconstruye sus filas y quita las columnas que agregó la migración."""
    _recrear_desde_instantaneas(("sesion_revocada", "modelo_prediccion", "fuente_datos", "genoma", "solicitud_historial"))

    # ---- sesion_revocada <- usuario.sesiones_revocadas
    op.execute(
        """
        INSERT INTO sesion_revocada (sid, expira_en)
        SELECT e->>'sid', (e->>'expira_en')::timestamptz FROM usuario u CROSS JOIN LATERAL jsonb_array_elements(u.sesiones_revocadas) AS e
        ON CONFLICT DO NOTHING
        """
    )
    op.drop_column("usuario", "sesiones_revocadas")

    # ---- modelo_prediccion <- prediccion.modelo (una fila por versión; la más reciente queda activa)
    op.execute(
        """
        INSERT INTO modelo_prediccion (id, version, algoritmo, entrenado_en, n_entrenamiento, metricas, parametros, activo)
        SELECT gen_random_uuid(), v.modelo_version, coalesce(v.modelo->>'algoritmo', ''),
               coalesce((v.modelo->>'entrenado_en')::timestamptz, v.generada_en), (v.modelo->>'n_entrenamiento')::int,
               coalesce(v.modelo->'metricas', '{}'::jsonb), coalesce(v.modelo->'parametros', '{}'::jsonb), false
        FROM (SELECT DISTINCT ON (modelo_version) modelo_version, modelo, generada_en FROM prediccion
              ORDER BY modelo_version, generada_en DESC) v
        """
    )
    op.execute("UPDATE modelo_prediccion SET activo = true WHERE id = (SELECT id FROM modelo_prediccion ORDER BY entrenado_en DESC LIMIT 1)")
    op.add_column("prediccion", sa.Column("modelo_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE prediccion p SET modelo_id = m.id FROM modelo_prediccion m WHERE m.version = p.modelo_version")
    op.alter_column("prediccion", "modelo_id", nullable=False)
    op.create_foreign_key(op.f("fk_prediccion_modelo_id_modelo_prediccion"), "prediccion", "modelo_prediccion", ["modelo_id"], ["id"], ondelete="RESTRICT")
    op.drop_column("prediccion", "modelo")
    op.drop_column("prediccion", "modelo_version")

    # ---- fuente_datos <- fago.origenes e interaccion_conocida.fuente
    op.execute(
        """
        INSERT INTO fuente_datos (id, nombre, version, url, descargado_en)
        SELECT gen_random_uuid(), s.nombre, s.version, s.url, now() FROM (
            SELECT DISTINCT ON (nombre, version) nombre, version, url FROM (
                SELECT o->>'fuente' AS nombre, o->>'version' AS version, o->>'url' AS url
                FROM fago CROSS JOIN LATERAL jsonb_array_elements(fago.origenes) AS o
                UNION ALL SELECT fuente, fuente_version, NULL FROM interaccion_conocida
            ) t ORDER BY nombre, version, url NULLS LAST
        ) s
        """
    )
    op.add_column("interaccion_conocida", sa.Column("fuente_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE interaccion_conocida i SET fuente_id = fd.id FROM fuente_datos fd WHERE fd.nombre = i.fuente AND fd.version = i.fuente_version")
    op.alter_column("interaccion_conocida", "fuente_id", nullable=False)
    op.create_foreign_key(op.f("fk_interaccion_conocida_fuente_id_fuente_datos"), "interaccion_conocida", "fuente_datos", ["fuente_id"], ["id"], ondelete="RESTRICT")
    op.drop_column("interaccion_conocida", "fuente_version")
    op.drop_column("interaccion_conocida", "fuente")

    # ---- fago_origen <- fago.origenes
    _recrear_desde_instantaneas(("fago_origen",))
    op.execute(
        """
        INSERT INTO fago_origen (fago_id, fuente_id, id_externo, version_origen, descargado_en)
        SELECT f.id, fd.id, o->>'id_externo', o->>'version', coalesce((o->>'descargado_en')::timestamptz, now())
        FROM fago f CROSS JOIN LATERAL jsonb_array_elements(f.origenes) AS o
        JOIN fuente_datos fd ON fd.nombre = o->>'fuente' AND fd.version = o->>'version'
        ON CONFLICT DO NOTHING
        """
    )
    op.drop_column("fago", "origenes")

    # ---- genoma <- aislado (una fila por aislado)
    op.execute(
        f"INSERT INTO genoma (id, aislado_id, {NOMBRES_GENOMA}) SELECT gen_random_uuid(), id, {NOMBRES_GENOMA} FROM aislado"
    )
    op.add_column("solicitud", sa.Column("genoma_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE solicitud s SET genoma_id = g.id FROM genoma g WHERE g.aislado_id = s.aislado_id")
    op.alter_column("solicitud", "genoma_id", nullable=False)
    op.create_foreign_key(op.f("fk_solicitud_genoma_id_genoma"), "solicitud", "genoma", ["genoma_id"], ["id"], ondelete="RESTRICT")
    op.drop_constraint(op.f("ck_aislado_qc_resultado"), "aislado", type_="check")
    for nombre, _, _ in COLUMNAS_GENOMA:
        op.drop_column("aislado", nombre)

    # ---- analisis_genomico <- solicitud (las solicitudes ya analizadas)
    op.create_table(
        "analisis_genomico",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("solicitud_id", sa.Uuid(), nullable=False),
        sa.Column("especie_detectada", sa.String(120)),
        sa.Column("distancia_especie", sa.Float()),
        sa.Column("locus_k_tipo", sa.String(20)),
        sa.Column("locus_k_confianza", sa.String(40)),
        sa.Column("n_genes", sa.Integer()),
        sa.Column("n_proteinas", sa.Integer()),
        sa.Column("versiones_herramientas", JSONB(), nullable=False),
        sa.Column("parametros", JSONB(), nullable=False),
        sa.Column("detalle", JSONB(), nullable=False, server_default=VACIO_OBJ),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analisis_genomico")),
        sa.ForeignKeyConstraint(["solicitud_id"], ["solicitud.id"], name=op.f("fk_analisis_genomico_solicitud_id_solicitud"), ondelete="RESTRICT"),
    )
    op.create_index(op.f("ix_analisis_genomico_solicitud_id"), "analisis_genomico", ["solicitud_id"])
    op.execute(
        """
        INSERT INTO analisis_genomico (id, solicitud_id, especie_detectada, distancia_especie, locus_k_tipo, locus_k_confianza,
                                       n_genes, n_proteinas, versiones_herramientas, parametros, detalle, creado_en)
        SELECT gen_random_uuid(), id, especie_detectada, distancia_especie, locus_k_tipo, locus_k_confianza, n_genes, n_proteinas,
               versiones_herramientas, parametros_analisis, detalle_analisis, analizado_en
        FROM solicitud WHERE analizado_en IS NOT NULL
        """
    )
    for nombre in ("analizado_en", "detalle_analisis", "parametros_analisis", "versiones_herramientas", "n_proteinas", "n_genes",
                   "locus_k_confianza", "locus_k_tipo", "distancia_especie", "especie_detectada"):
        op.drop_column("solicitud", nombre)

    # ---- solicitud_historial <- fila de creación de cada solicitud + eventos `cambio_estado` de la auditoría
    op.execute(
        "INSERT INTO solicitud_historial (id, solicitud_id, estado_anterior, estado_nuevo, usuario_id, motivo, creado_en) "
        "SELECT gen_random_uuid(), id, NULL, 'registrada', creada_por, NULL, creada_en FROM solicitud"
    )
    op.execute(
        """
        WITH ev AS MATERIALIZED (
            SELECT entidad_id::uuid AS solicitud_id, usuario_id, detalle, ts FROM auditoria
            WHERE accion = 'cambio_estado' AND entidad = 'solicitud'
        )
        INSERT INTO solicitud_historial (id, solicitud_id, estado_anterior, estado_nuevo, usuario_id, motivo, creado_en)
        SELECT gen_random_uuid(), s.id, ev.detalle->>'de', ev.detalle->>'a', u.id, ev.detalle->>'motivo', ev.ts
        FROM ev JOIN solicitud s ON s.id = ev.solicitud_id LEFT JOIN usuario u ON u.id = ev.usuario_id
        """
    )

    # ---- recomendacion_candidato <- recomendacion_emitida.candidatos
    _recrear_desde_instantaneas(("recomendacion_candidato",))
    op.execute(
        """
        INSERT INTO recomendacion_candidato (recomendacion_id, fago_id, rango, puntaje, descartado, justificacion, resultado_ensayo)
        SELECT r.id, (c->>'fago_id')::uuid, (c->>'rango')::int, (c->>'puntaje')::float, (c->>'descartado')::boolean,
               c->>'justificacion', coalesce(c->>'resultado_ensayo', 'no_ensayado')
        FROM recomendacion_emitida r CROSS JOIN LATERAL jsonb_array_elements(r.candidatos) AS c
        """
    )
    op.drop_column("recomendacion_emitida", "candidatos")
