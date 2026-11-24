"""Alertas internas (RF-64, RF-65).

Se generan solas cuando una solicitud cambia de estado (ver `estados.cambiar_estado`):
- Emitida o Rechazada: avisa al técnico que la creó y al clínico solicitante.
- Predicción lista: avisa a todos los microbiólogos activos, que son quienes la validan.
Las notificaciones push (RF-66) no se incluyen: se consulta la bandeja.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Aislado, Alerta, Solicitud, Usuario


def _destinatarios(session: Session, solicitud: Solicitud, nuevo: str) -> list:
    """Ids de usuario a los que corresponde la alerta de este cambio de estado, sin repetidos."""
    if nuevo == "prediccion_lista":
        return list(session.scalars(select(Usuario.id).where(Usuario.rol == "MIC", Usuario.activo.is_(True))))
    ids = {solicitud.creada_por, solicitud.solicitante_id}
    # Solo reciben alertas los roles que usan la bandeja (técnico, microbiólogo y clínico) y que siguen activos.
    return list(session.scalars(select(Usuario.id).where(Usuario.id.in_(ids), Usuario.rol.in_(("TEC", "MIC", "CLI")), Usuario.activo.is_(True))))


def por_cambio_estado(session: Session, solicitud: Solicitud, nuevo: str, motivo: str | None = None) -> None:
    """Crea las alertas que correspondan al nuevo estado; en otros estados no hace nada."""
    if nuevo not in ("emitida", "rechazada", "prediccion_lista"):
        return
    aislado = session.get(Aislado, solicitud.aislado_id)
    codigo = aislado.codigo_interno if aislado else str(solicitud.id)[:8]
    mensaje = {
        "emitida": f"La recomendación de la solicitud {codigo} fue emitida.",
        "rechazada": f"La solicitud {codigo} fue rechazada" + (f": {motivo}" if motivo else "."),
        "prediccion_lista": f"La solicitud {codigo} tiene una predicción lista para validar.",
    }[nuevo]
    for usuario_id in _destinatarios(session, solicitud, nuevo):
        session.add(Alerta(usuario_id=usuario_id, solicitud_id=solicitud.id, tipo=nuevo, mensaje=mensaje))
