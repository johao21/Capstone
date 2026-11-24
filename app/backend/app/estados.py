"""Máquina de estados de la solicitud (SRS sección 7.2, RF-12)."""
from sqlalchemy.orm import Session

from . import alertas, auditoria
from .models import Solicitud, SolicitudHistorial

# Para cada estado, a cuáles puede pasar. Cualquier otro salto es inválido (ver `cambiar_estado`).
# Camino normal: registrada -> en_analisis -> prediccion_lista -> en_validacion -> emitida -> cerrada.
# En este corte solo se recorre hasta `en_analisis`: la predicción (OE3) aún no existe.
TRANSICIONES: dict[str, set[str]] = {
    "registrada": {"en_analisis", "anulada"},
    "en_analisis": {"prediccion_lista", "rechazada", "error", "anulada"},
    # `error` admite volver a `en_analisis`: es lo que hace el botón "Reintentar".
    "error": {"en_analisis", "anulada"},
    "prediccion_lista": {"en_validacion", "anulada"},
    "en_validacion": {"emitida", "rechazada", "prediccion_lista", "anulada"},
    "emitida": {"cerrada"},
    # Los estados finales no tienen salida.
    "rechazada": set(),
    "anulada": set(),
    "cerrada": set(),
}

ESTADOS_FINALES = {"rechazada", "anulada", "cerrada"}


class TransicionInvalida(ValueError):
    """Se intentó una transición que no está en el diagrama de estados."""


def cambiar_estado(
    session: Session,
    solicitud: Solicitud,
    nuevo: str,
    usuario_id=None,
    motivo: str | None = None,
) -> None:
    """Cambia el estado y deja la fila de historial en la misma transacción."""
    actual = solicitud.estado
    # `.get(actual, set())`: un estado desconocido no tiene salidas, así que también se rechaza.
    if nuevo not in TRANSICIONES.get(actual, set()):
        raise TransicionInvalida(f"{actual} -> {nuevo}")
    solicitud.estado = nuevo
    solicitud.motivo_estado = motivo
    # El historial se agrega a la misma sesión: si la transacción se revierte, no queda un cambio sin registrar.
    session.add(
        SolicitudHistorial(
            solicitud_id=solicitud.id,
            estado_anterior=actual,
            estado_nuevo=nuevo,
            usuario_id=usuario_id,
            motivo=motivo,
        )
    )
    # Cada cambio de estado deja un evento de auditoría (RF-48) y, si corresponde, avisa a los interesados (RF-64).
    # Sin `usuario_id` el cambio lo hizo el sistema (el worker).
    auditoria.registrar(
        session, "cambio_estado", usuario_id=usuario_id, entidad="solicitud", entidad_id=solicitud.id,
        detalle={"de": actual, "a": nuevo, "motivo": motivo},
    )
    alertas.por_cambio_estado(session, solicitud, nuevo, motivo)
