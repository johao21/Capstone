"""Modelos SQLAlchemy de SIRFA: 12 tablas (Documento de Diseño, sección 3, simplificado por la solicitud de cambio SC-07).

Acceso (`centro`, `usuario`), solicitudes (`aislado`, `solicitud`, `trabajo`), banco de fagos (`fago`,
`interaccion_conocida`), predicción y recomendación (`prediccion`, `prediccion_fago`, `recomendacion_emitida`),
auditoría de solo adición (`auditoria`) y alertas (`alerta`).

Lo que antes eran tablas de detalle quedó como columnas o como JSON dentro de la tabla a la que pertenece:
el genoma, en `aislado`; el análisis genómico, en `solicitud`; el origen de cada fago, en `fago.origenes`;
la versión del modelo, en `prediccion.modelo`; los candidatos emitidos, en `recomendacion_emitida.candidatos`;
las sesiones cerradas, en `usuario.sesiones_revocadas`, y el historial de estados se lee de `auditoria`.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Plantillas de nombre para índices y restricciones. Con nombres predecibles, las migraciones de
# Alembic pueden referirse a ellos sin adivinar el nombre que les puso la base de datos.
CONVENCION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# JSON portable: JSONB en PostgreSQL, JSON en el resto (las pruebas usan SQLite).
TipoJSON = JSON().with_variant(JSONB(), "postgresql")

# Valores permitidos de las columnas de texto con dominio cerrado. Cada tupla alimenta una
# restricción CHECK (ver `restriccion`) y también la validación de la API.
ROLES = ("TEC", "MIC", "CLI", "EPI", "ADM")
TIPOS_MUESTRA = ("sangre", "orina", "respiratoria", "herida", "otra")
MECANISMOS = ("KPC", "NDM", "OXA-48", "VIM", "IMP", "otro", "ninguno", "desconocido")
RESULTADOS_QC = ("aprobado", "advertencia", "rechazado")
ESTADOS_SOLICITUD = (
    "registrada",
    "en_analisis",
    "prediccion_lista",
    "en_validacion",
    "emitida",
    "cerrada",
    "rechazada",
    "anulada",
    "error",
)
TIPOS_TRABAJO = ("pipeline", "prediccion", "ingesta")
ESTADOS_TRABAJO = ("pendiente", "en_curso", "ok", "fallido")
CICLOS_VIDA = ("litico", "templado", "desconocido")
ESTADOS_CURADURIA = ("pendiente", "aprobado", "descartado")
RESULTADOS_INTERACCION = ("infecta", "no_infecta")
TIPOS_ALERTA = ("emitida", "rechazada", "prediccion_lista")
RESULTADOS_ENSAYO = ("infecta", "no_infecta", "no_ensayado")
ESTADOS_RECOMENDACION = ("vigente", "reemplazada")


def ahora() -> datetime:
    """Fecha y hora actual en UTC, con zona horaria; es el valor por defecto de las columnas `*_en`."""
    return datetime.now(timezone.utc)


def restriccion(columna: str, valores: tuple[str, ...], nombre: str) -> CheckConstraint:
    """CHECK que obliga a que `columna` sea uno de `valores`, p. ej. `rol IN ('TEC', 'MIC', ...)`."""
    lista = ", ".join(f"'{v}'" for v in valores)
    return CheckConstraint(f"{columna} IN ({lista})", name=nombre)


class Base(DeclarativeBase):
    """Base común de todas las tablas; aplica la convención de nombres."""

    metadata = MetaData(naming_convention=CONVENCION)


def pk() -> Mapped[uuid.UUID]:
    """Clave primaria UUID generada en Python (no depende de una secuencia de la base de datos)."""
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


# En todas las claves foráneas, ondelete="RESTRICT" impide borrar una fila que otra todavía usa:
# el sistema conserva la trazabilidad, no se borra en cascada.

# --------------------------------------------------------------------- acceso
class Centro(Base):
    """Centro de salud o laboratorio que registra aislados."""

    __tablename__ = "centro"
    id: Mapped[uuid.UUID] = pk()
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


class Usuario(Base):
    """Persona que usa el sistema: un único rol y un único centro (SRS 2.3). No se borra, solo se desactiva."""

    __tablename__ = "usuario"
    __table_args__ = (restriccion("rol", ROLES, "rol"),)
    id: Mapped[uuid.UUID] = pk()
    correo: Mapped[str] = mapped_column(String(254), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(3))
    centro_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("centro.id", ondelete="RESTRICT"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Bloqueo por intentos fallidos de inicio de sesión (RNF-05): 5 intentos y 15 minutos.
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Sesiones cerradas con "Cerrar sesión" (RF-02): lista de {"sid": ..., "expira_en": ...}. Los tokens JWT de una sesión llevan su
    # `sid`; si está aquí, se rechazan. Cada entrada se descarta sola cuando vence el último token de esa sesión.
    sesiones_revocadas: Mapped[list] = mapped_column(TipoJSON, default=list)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


# ---------------------------------------------------------------- solicitudes
class Aislado(Base):
    """Muestra bacteriana aislada de un paciente, con sus datos de contexto y su genoma (archivo FASTA y métricas de calidad)."""

    __tablename__ = "aislado"
    __table_args__ = (
        # Un centro no puede repetir un código de aislado; la API lo informa como error 409.
        UniqueConstraint("centro_id", "codigo_interno", name="uq_aislado_centro_codigo"),
        restriccion("tipo_muestra", TIPOS_MUESTRA, "tipo_muestra"),
        restriccion("mecanismo_resistencia", MECANISMOS, "mecanismo_resistencia"),
        restriccion("qc_resultado", RESULTADOS_QC, "qc_resultado"),
    )
    id: Mapped[uuid.UUID] = pk()
    codigo_interno: Mapped[str] = mapped_column(String(80))
    centro_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("centro.id", ondelete="RESTRICT"))
    fecha_aislamiento: Mapped[date] = mapped_column(Date)
    especie_declarada: Mapped[str] = mapped_column(String(120))
    tipo_muestra: Mapped[str] = mapped_column(String(20))
    mecanismo_resistencia: Mapped[str | None] = mapped_column(String(20))
    observaciones: Mapped[str | None] = mapped_column(Text)
    creado_por: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    # Genoma del aislado: el FASTA se guarda en disco con su SHA-256 como nombre; aquí quedan la ruta y las métricas de calidad.
    ruta_archivo: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    tamano_bytes: Mapped[int] = mapped_column(BigInteger)
    nombre_original: Mapped[str] = mapped_column(String(255))
    # Métricas de calidad (QC): quedan en None hasta que el worker procesa el genoma.
    qc_longitud: Mapped[int | None] = mapped_column(BigInteger)
    qc_contigs: Mapped[int | None] = mapped_column(Integer)
    qc_n50: Mapped[int | None] = mapped_column(Integer)
    qc_gc: Mapped[float | None] = mapped_column(Float)
    qc_prop_ambiguas: Mapped[float | None] = mapped_column(Float)
    qc_resultado: Mapped[str | None] = mapped_column(String(12))
    cargado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


class Solicitud(Base):
    """Pedido de análisis de un aislado, con el resultado de su análisis genómico. Su `estado` sigue la máquina de estados de estados.py."""

    __tablename__ = "solicitud"
    __table_args__ = (
        restriccion("estado", ESTADOS_SOLICITUD, "estado"),
        # Índices para las consultas de listado: por centro y estado, y por responsable asignado.
        Index("ix_solicitud_centro_estado", "centro_id", "estado", "creada_en"),
        Index("ix_solicitud_asignada_estado", "asignada_a", "estado"),
    )
    id: Mapped[uuid.UUID] = pk()
    aislado_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("aislado.id", ondelete="RESTRICT"))
    centro_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("centro.id", ondelete="RESTRICT"))
    solicitante_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    creada_por: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    asignada_a: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(20), default="registrada")
    motivo_estado: Mapped[str | None] = mapped_column(Text)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    # onupdate: se refresca sola cada vez que SQLAlchemy actualiza la fila.
    actualizada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora, onupdate=ahora)
    # Análisis genómico (lo escribe el worker al terminar el pipeline). Mientras `analizado_en` es None, el análisis no existe.
    especie_detectada: Mapped[str | None] = mapped_column(String(120))
    distancia_especie: Mapped[float | None] = mapped_column(Float)
    locus_k_tipo: Mapped[str | None] = mapped_column(String(20))
    locus_k_confianza: Mapped[str | None] = mapped_column(String(40))
    n_genes: Mapped[int | None] = mapped_column(Integer)
    n_proteinas: Mapped[int | None] = mapped_column(Integer)
    # Versiones de las herramientas y parámetros usados, para poder reproducir el análisis.
    versiones_herramientas: Mapped[dict] = mapped_column(TipoJSON, default=dict)
    parametros_analisis: Mapped[dict] = mapped_column(TipoJSON, default=dict)
    # Resultado completo y voluminoso del pipeline (QC, especie, locus K, genes y herramientas), tal como salió.
    detalle_analisis: Mapped[dict] = mapped_column(TipoJSON, default=dict)
    analizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Trabajo(Base):
    """Cola de trabajos consumida por los workers con FOR UPDATE SKIP LOCKED (decisión D-02)."""

    __tablename__ = "trabajo"
    __table_args__ = (
        restriccion("tipo", TIPOS_TRABAJO, "tipo"),
        restriccion("estado", ESTADOS_TRABAJO, "estado"),
        # Índice parcial: solo cubre los trabajos pendientes, que son los que los workers consultan
        # todo el tiempo; los terminados no lo agrandan. (Solo PostgreSQL lo aplica.)
        Index(
            "ix_trabajo_pendientes",
            "tipo",
            "siguiente_intento_en",
            postgresql_where=text("estado = 'pendiente'"),
        ),
    )
    id: Mapped[uuid.UUID] = pk()
    tipo: Mapped[str] = mapped_column(String(12))
    solicitud_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("solicitud.id", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(12), default="pendiente")
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    # Hasta cuándo esperar antes de reintentar; None significa "ya puede tomarse".
    siguiente_intento_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Identificador del worker que lo reclamó (nombre del equipo + PID).
    bloqueado_por: Mapped[str | None] = mapped_column(String(120))
    error: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    terminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------- banco
class Fago(Base):
    """Fago (virus que infecta bacterias) del banco. Nace `pendiente` hasta que alguien lo cura."""

    __tablename__ = "fago"
    __table_args__ = (
        restriccion("ciclo_vida", CICLOS_VIDA, "ciclo_vida"),
        restriccion("estado_curaduria", ESTADOS_CURADURIA, "estado_curaduria"),
        Index("ix_fago_nombre", "nombre"),
    )
    id: Mapped[uuid.UUID] = pk()
    accesion: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(300))
    familia: Mapped[str | None] = mapped_column(String(120))
    genero: Mapped[str | None] = mapped_column(String(120))
    ciclo_vida: Mapped[str] = mapped_column(String(12), default="desconocido")
    longitud_pb: Mapped[int | None] = mapped_column(Integer)
    completitud: Mapped[str | None] = mapped_column(String(40))
    hospedador_declarado: Mapped[str | None] = mapped_column(String(200))
    estado_curaduria: Mapped[str] = mapped_column(String(12), default="pendiente")
    curado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    curado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Procedencia: una entrada por fuente y versión de la que salió el fago (un fago puede venir de varias):
    # {"fuente": "INPHARED", "version": "7Apr2026", "url": ..., "id_externo": ..., "descargado_en": ...}.
    origenes: Mapped[list] = mapped_column(TipoJSON, default=list)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


class InteraccionConocida(Base):
    """Resultado experimental publicado de un fago frente a una cepa. Es la evidencia que usa recomendacion.py."""

    __tablename__ = "interaccion_conocida"
    __table_args__ = (restriccion("resultado", RESULTADOS_INTERACCION, "resultado"),)
    id: Mapped[uuid.UUID] = pk()
    fago_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fago.id", ondelete="RESTRICT"), index=True)
    especie_hospedador: Mapped[str] = mapped_column(String(120))
    cepa: Mapped[str | None] = mapped_column(String(120))
    locus_k_tipo: Mapped[str | None] = mapped_column(String(20), index=True)
    resultado: Mapped[str] = mapped_column(String(12))
    # Base de datos externa de la que se importó (p. ej. PhageHostLearn) y su versión.
    fuente: Mapped[str] = mapped_column(String(120))
    fuente_version: Mapped[str] = mapped_column(String(80))
    referencia: Mapped[str | None] = mapped_column(String(300))


# ---------------------------------------------------------------------- auditoría
class Auditoria(Base):
    """Registro de solo adición de lo que ocurre en el sistema (RF-48 a RF-51).

    Cada fila guarda el hash de la anterior (`hash_previo`) y el suyo propio: si alguien altera o borra una fila, la
    cadena deja de cuadrar y `auditoria.verificar` lo detecta. En PostgreSQL, además, un disparador (migración 0002)
    rechaza cualquier UPDATE, DELETE o TRUNCATE de esta tabla.
    """

    __tablename__ = "auditoria"
    __table_args__ = (
        Index("ix_auditoria_ts", "ts"),
        Index("ix_auditoria_accion", "accion"),
        Index("ix_auditoria_usuario_id", "usuario_id"),
    )
    # El orden de la cadena lo da `seq`. En SQLite (pruebas) una columna INTEGER PRIMARY KEY se autoincrementa sola.
    seq: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    # Sin clave foránea a propósito: el evento debe sobrevivir al usuario y también registra intentos con un correo inexistente.
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    correo: Mapped[str | None] = mapped_column(String(254))
    rol: Mapped[str | None] = mapped_column(String(3))
    accion: Mapped[str] = mapped_column(String(60))
    entidad: Mapped[str | None] = mapped_column(String(60))
    entidad_id: Mapped[str | None] = mapped_column(String(64))
    resultado: Mapped[str] = mapped_column(String(10), default="ok")  # ok | fallido | denegado
    origen: Mapped[str | None] = mapped_column(String(64))  # dirección IP de la conexión
    modelo_version: Mapped[str | None] = mapped_column(String(40))
    detalle: Mapped[dict] = mapped_column(TipoJSON, default=dict)
    hash_previo: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Alerta(Base):
    """Aviso para un usuario (RF-64, RF-65): una solicitud quedó emitida o rechazada, o hay una predicción por validar."""

    __tablename__ = "alerta"
    __table_args__ = (restriccion("tipo", TIPOS_ALERTA, "tipo"), Index("ix_alerta_usuario_leida", "usuario_id", "leida"))
    id: Mapped[uuid.UUID] = pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    solicitud_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("solicitud.id", ondelete="RESTRICT"))
    tipo: Mapped[str] = mapped_column(String(20))
    mensaje: Mapped[str] = mapped_column(Text)
    leida: Mapped[bool] = mapped_column(Boolean, default=False)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


# ------------------------------------------------------------------ predicción
class Prediccion(Base):
    """Ranking de fagos generado para una solicitud con una versión del modelo (RF-34, RF-35, RF-39)."""

    __tablename__ = "prediccion"
    id: Mapped[uuid.UUID] = pk()
    solicitud_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("solicitud.id", ondelete="RESTRICT"), index=True)
    # Versión del modelo que la generó, y una copia de su ficha (algoritmo, fecha de entrenamiento, datos y métricas) tal como
    # estaba en ese momento: así la predicción se puede reconstruir aunque el modelo se vuelva a entrenar (RF-53).
    modelo_version: Mapped[str] = mapped_column(String(40))
    modelo: Mapped[dict] = mapped_column(TipoJSON, default=dict)
    locus_k_tipo: Mapped[str | None] = mapped_column(String(20))
    # RF-38: el locus K del aislado casi no aparece en los datos de entrenamiento.
    baja_confianza: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_baja_confianza: Mapped[str | None] = mapped_column(Text)
    # Con qué cepas de entrenamiento se comparó el locus del aislado y cuántos fagos entraron al ranking.
    detalle: Mapped[dict] = mapped_column(TipoJSON, default=dict)
    generada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


class PrediccionFago(Base):
    """Un fago dentro del ranking: su puntaje, su posición y las características que más pesaron (SHAP, RF-36)."""

    __tablename__ = "prediccion_fago"
    prediccion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediccion.id", ondelete="RESTRICT"), primary_key=True)
    fago_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fago.id", ondelete="RESTRICT"), primary_key=True)
    puntaje: Mapped[float] = mapped_column(Float)
    rango: Mapped[int] = mapped_column(Integer)
    explicacion: Mapped[dict] = mapped_column(TipoJSON, default=dict)


# ------------------------------------------------------------ recomendación emitida
class RecomendacionEmitida(Base):
    """Recomendación que un microbiólogo validó y emitió (RF-44). No se modifica: una corrección crea otra versión (RF-46)."""

    __tablename__ = "recomendacion_emitida"
    __table_args__ = (
        UniqueConstraint("solicitud_id", "version", name="uq_recomendacion_solicitud_version"),
        restriccion("estado", ESTADOS_RECOMENDACION, "estado"),
    )
    id: Mapped[uuid.UUID] = pk()
    solicitud_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("solicitud.id", ondelete="RESTRICT"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    prediccion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediccion.id", ondelete="RESTRICT"))
    validador_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(12), default="vigente")
    observacion: Mapped[str | None] = mapped_column(Text)
    advertencia: Mapped[str] = mapped_column(Text)
    # Candidatos de la versión, incluidos los descartados con su justificación. Una entrada por fago:
    # {"fago_id", "rango", "puntaje", "descartado", "justificacion", "resultado_ensayo"}. Lo único que cambia después de la emisión
    # es `resultado_ensayo` (RF-17): el microbiólogo lo anota cuando tiene el resultado del laboratorio.
    candidatos: Mapped[list] = mapped_column(TipoJSON, default=list)
    emitida_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
