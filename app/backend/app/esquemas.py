"""Modelos de respuesta de la API (aparecen en la documentación automática de /docs)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class SolicitudResumen(BaseModel):
    """Fila de la tabla de solicitudes; también es la base del detalle."""

    id: uuid.UUID
    codigo_interno: str
    estado: str  # uno de ESTADOS_SOLICITUD (models.py)
    etapa: str  # texto legible del estado, ya traducido para la pantalla
    motivo_estado: str | None = None
    creada_en: datetime
    actualizada_en: datetime
    # Salen del análisis genómico; son None mientras el pipeline no termina.
    especie_detectada: str | None = None
    locus_k_tipo: str | None = None
    locus_k_confianza: str | None = None


class ListaSolicitudes(BaseModel):
    """Página de resultados: `total` cuenta todas las filas, `items` solo la página pedida."""

    total: int
    items: list[SolicitudResumen]


class AisladoOut(BaseModel):
    """Datos clínicos del aislado bacteriano, tal como se declararon al registrarlo."""

    codigo_interno: str
    fecha_aislamiento: date
    especie_declarada: str
    tipo_muestra: str
    mecanismo_resistencia: str | None = None
    observaciones: str | None = None


class GenomaOut(BaseModel):
    """Archivo FASTA subido y las métricas de calidad (QC) que calcula el pipeline."""

    nombre_original: str
    sha256: str
    tamano_bytes: int
    # Las métricas de QC son None hasta que el worker procesa el genoma.
    qc_resultado: str | None = None
    qc_longitud: int | None = None
    qc_contigs: int | None = None
    qc_n50: int | None = None
    qc_gc: float | None = None
    qc_prop_ambiguas: float | None = None


class AnalisisOut(BaseModel):
    """Resultado del análisis genómico: especie, locus K y genes predichos."""

    especie_detectada: str | None = None
    distancia_especie: float | None = None  # distancia Mash al genoma de referencia más cercano
    especie_verificada: bool | None = None  # False si no había referencias y se usó la especie declarada
    especie_referencia: str | None = None
    locus_k_tipo: str | None = None
    locus_k_confianza: str | None = None
    n_genes: int | None = None
    n_proteinas: int | None = None
    versiones_herramientas: dict = Field(default_factory=dict)  # versión de Prodigal, Kaptive y Mash usadas
    creado_en: datetime


class TrabajoOut(BaseModel):
    """Un trabajo de la cola asociado a la solicitud (pipeline o, más adelante, predicción)."""

    tipo: str
    estado: str
    intentos: int
    error: str | None = None
    creado_en: datetime
    terminado_en: datetime | None = None


class HistorialOut(BaseModel):
    """Una fila del historial de cambios de estado."""

    estado_anterior: str | None = None  # None en la fila de creación
    estado_nuevo: str
    motivo: str | None = None
    creado_en: datetime


class SolicitudDetalle(SolicitudResumen):
    """Respuesta de `GET /solicitudes/{id}`: el resumen más todo lo asociado."""

    aislado: AisladoOut
    genoma: GenomaOut
    analisis: AnalisisOut | None = None
    trabajos: list[TrabajoOut]
    historial: list[HistorialOut]
    registrada_por: str | None = None  # técnico que la creó
    solicitante: str | None = None  # clínico que pide la recomendación
    asignada_a: str | None = None  # microbiólogo que la valida


class MotivoIn(BaseModel):
    """Cuerpo opcional al anular una solicitud."""

    motivo: str | None = Field(default=None, max_length=500)


class FagoOut(BaseModel):
    """Un fago del banco, con los datos que trae la fuente (INPHARED)."""

    id: uuid.UUID
    accesion: str  # identificador de NCBI, p. ej. NC_000866
    nombre: str
    familia: str | None = None
    genero: str | None = None
    ciclo_vida: str
    longitud_pb: int | None = None  # pb = pares de bases
    completitud: str | None = None
    hospedador_declarado: str | None = None
    estado_curaduria: str  # pendiente | aprobado | descartado
    curado_en: datetime | None = None


class ListaFagos(BaseModel):
    """Página de resultados del banco de fagos."""

    total: int
    items: list[FagoOut]


class CandidatoOut(BaseModel):
    """Fago con evidencia positiva conocida para el locus K del aislado."""

    fago_id: uuid.UUID
    accesion: str
    nombre: str
    interacciones_positivas: int
    interacciones_negativas: int
    tasa_positiva: float  # positivas / (positivas + negativas), entre 0 y 1
    cepas_probadas: int
    referencias: list[str]


class PerfilAislado(BaseModel):
    """Lo que se sabe del aislado y se usa para buscar evidencia."""

    especie_detectada: str | None = None
    locus_k_tipo: str | None = None
    locus_k_confianza: str | None = None


class EstadoBanco(BaseModel):
    """Conteos que muestran qué tan completo está el banco de fagos."""

    fagos_total: int
    fagos_curados: int
    fagos_con_ciclo_de_vida: int
    interacciones_conocidas: int


class Recomendacion(BaseModel):
    """Respuesta de `GET /solicitudes/{id}/recomendacion`: evidencia conocida, no predicción."""

    solicitud_id: uuid.UUID
    estado: str = Field(description="analisis_pendiente | no_aplica | sin_evidencia | evidencia_disponible")
    mensaje: str
    aviso: str  # descargo: SIRFA no diagnostica ni prescribe
    perfil: PerfilAislado | None = None
    candidatos: list[CandidatoOut]
    banco: EstadoBanco


class Resumen(BaseModel):
    """Respuesta de `GET /resumen`: conteos para la pantalla de inicio."""

    solicitudes_por_estado: dict[str, int]
    banco: EstadoBanco
