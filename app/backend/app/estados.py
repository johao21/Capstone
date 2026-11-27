"""Máquina de estados de la solicitud (SRS sección 7.2, RF-12)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import alertas, auditoria
from .models import Auditoria, Solicitud

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
    """Cambia el estado y deja el evento de auditoría (que es el historial) en la misma transacción."""
    actual = solicitud.estado
    # `.get(actual, set())`: un estado desconocido no tiene salidas, así que también se rechaza.
    if nuevo not in TRANSICIONES.get(actual, set()):
        raise TransicionInvalida(f"{actual} -> {nuevo}")
    solicitud.estado = nuevo
    solicitud.motivo_estado = motivo
    # Cada cambio de estado deja un evento de auditoría (RF-48) en la misma transacción: si se revierte, no queda un cambio sin
    # registrar. Ese evento es el historial de la solicitud (ver `historial_de`). Si corresponde, además avisa a los interesados (RF-64).
    # Sin `usuario_id` el cambio lo hizo el sistema (el worker).
    auditoria.registrar(
        session, "cambio_estado", usuario_id=usuario_id, entidad="solicitud", entidad_id=solicitud.id,
        detalle={"de": actual, "a": nuevo, "motivo": motivo},
    )
    alertas.por_cambio_estado(session, solicitud, nuevo, motivo)


def historial_de(session: Session, solicitud: Solicitud) -> list[dict]:
    """Cambios de estado de la solicitud, del más antiguo al más reciente (RF-14).

    No hay una tabla de historial: la primera fila (la creación) sale de la propia solicitud y las demás, de los eventos
    `cambio_estado` de la auditoría, que `cambiar_estado` deja en la misma transacción que el cambio. Los eventos se insertan
    al hacer commit: un cambio todavía sin confirmar no aparece."""
    filas = [{"estado_anterior": None, "estado_nuevo": "registrada", "usuario_id": solicitud.creada_por, "motivo": None,
              "creado_en": solicitud.creada_en}]
    eventos = session.scalars(
        select(Auditoria)
        .where(Auditoria.accion == "cambio_estado", Auditoria.entidad == "solicitud", Auditoria.entidad_id == str(solicitud.id))
        .order_by(Auditoria.seq)
    )
    for e in eventos:
        d = e.detalle or {}
        filas.append({"estado_anterior": d.get("de"), "estado_nuevo": d.get("a"), "usuario_id": e.usuario_id, "motivo": d.get("motivo"),
                      "creado_en": e.ts})
    # Las solicitudes anteriores a la auditoría (sus eventos empiezan el 2-11-2026) no tienen todos sus eventos. Si la línea de
    # tiempo no termina en el estado actual, se cierra con una fila que lo indica: así el historial no contradice a la solicitud.
    if filas[-1]["estado_nuevo"] != solicitud.estado:
        filas.append({"estado_anterior": filas[-1]["estado_nuevo"], "estado_nuevo": solicitud.estado, "usuario_id": None,
                      "motivo": solicitud.motivo_estado, "creado_en": solicitud.actualizada_en})
    return filas
