"""Registro de auditoría de solo adición con encadenamiento de hashes (RF-48 a RF-52, RF-54, RNF-08).

Cada evento guarda el hash del anterior y el suyo propio, calculado sobre sus campos. Si una fila se altera
o desaparece, `verificar` encuentra el primer punto donde la cadena deja de cuadrar. Además, en PostgreSQL un
disparador (migración 0002) impide UPDATE, DELETE y TRUNCATE sobre la tabla.

`registrar` solo deja el evento en cola dentro de la sesión; el evento se encadena y se inserta justo antes del
commit (evento `before_commit` de más abajo), en la misma transacción que la acción que describe, así que ambos
se guardan o se revierten juntos. Encadenar tan tarde importa: el candado de la cadena se toma recién ahí y dura
milisegundos, no lo que tarde el análisis de un genoma (el worker mantiene su transacción abierta ~20 s).
Los eventos que deben sobrevivir a un rechazo (inicio de sesión fallido, acceso denegado) se guardan con un commit
propio antes de responder el error.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from .models import Auditoria, Usuario

HASH_INICIAL = "0" * 64
# Número cualquiera que identifica el candado de la cadena (pg_advisory_xact_lock): dos transacciones que registran
# eventos a la vez se turnan, de modo que el orden de `seq` coincide con el orden de la cadena.
CANDADO_CADENA = 7402
ROL_SISTEMA = "SIS"  # eventos que no hace una persona (el worker, p. ej.)


def _canonico(datos: dict) -> str:
    """JSON determinista (claves ordenadas, sin espacios): lo que se hashea."""
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _texto_ts(ts: datetime) -> str:
    """Fecha en UTC con microsegundos. SQLite devuelve fechas sin zona horaria: se interpretan como UTC."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _campos_hash(e: Auditoria) -> dict:
    return {
        "ts": _texto_ts(e.ts),
        "usuario_id": str(e.usuario_id) if e.usuario_id else None,
        "correo": e.correo,
        "rol": e.rol,
        "accion": e.accion,
        "entidad": e.entidad,
        "entidad_id": e.entidad_id,
        "resultado": e.resultado,
        "origen": e.origen,
        "modelo_version": e.modelo_version,
        "detalle": e.detalle,
    }


def calcular_hash(hash_previo: str, e: Auditoria) -> str:
    return hashlib.sha256(f"{hash_previo}|{_canonico(_campos_hash(e))}".encode("utf-8")).hexdigest()


def _cortar(texto: str | None, largo: int) -> str | None:
    return texto[:largo] if texto else texto


def registrar(
    session: Session,
    accion: str,
    *,
    usuario: Usuario | None = None,
    usuario_id=None,
    correo: str | None = None,
    entidad: str | None = None,
    entidad_id=None,
    resultado: str = "ok",
    origen: str | None = None,
    modelo_version: str | None = None,
    detalle: dict | None = None,
) -> None:
    """Deja un evento en cola; se inserta y se encadena al hacer commit. Sin `usuario` ni `usuario_id` el actor es el sistema (rol `SIS`)."""
    if usuario is None and usuario_id is not None:
        usuario = session.get(Usuario, usuario_id)
    if usuario is not None:
        usuario_id, correo, rol = usuario.id, usuario.correo, usuario.rol
    else:
        rol = ROL_SISTEMA if correo is None else None  # un intento con un correo desconocido no tiene rol
    # Cada texto se recorta al largo de su columna: PostgreSQL rechaza un valor más largo (SQLite, que usan las pruebas, no).
    campos = dict(
        ts=datetime.now(timezone.utc),
        usuario_id=usuario_id,
        correo=_cortar(correo, 254),
        rol=rol,
        accion=accion[:60],
        entidad=_cortar(entidad, 60),
        entidad_id=_cortar(str(entidad_id) if entidad_id is not None else None, 64),
        resultado=resultado,
        origen=_cortar(origen, 64),
        modelo_version=_cortar(modelo_version, 40),
        # Se pasa por JSON para que el valor guardado sea idéntico al que se hashea (UUID y fechas pasan a texto).
        detalle=json.loads(_canonico(detalle or {})),
    )
    # `tx` es la transacción (o savepoint) activa: si se revierte, el evento se descarta junto con la acción.
    # `connection()` inicia la transacción si todavía no existe (autobegin), para que haya una a la cual etiquetar el evento.
    session.connection()
    # `get_nested_transaction` es el savepoint más interno (None si no hay); `get_transaction`, la transacción raíz.
    session.info.setdefault(_COLA, []).append({"tx": session.get_nested_transaction() or session.get_transaction(), "campos": campos})


_COLA = "auditoria_pendiente"


def _descendiente_de(tx, base) -> bool:
    """True si `tx` es `base` o está anidada dentro de ella."""
    while tx is not None:
        if tx is base:
            return True
        tx = tx.parent
    return False


@event.listens_for(Session, "after_soft_rollback")
def _descartar_eventos_revertidos(session: Session, transaccion_revertida) -> None:
    """Una transacción o savepoint revertido se lleva consigo los eventos que se registraron dentro de él."""
    cola = session.info.get(_COLA)
    if not cola:
        return
    if transaccion_revertida.parent is None:  # se revirtió la transacción completa
        cola.clear()
    else:
        cola[:] = [e for e in cola if not _descendiente_de(e["tx"], transaccion_revertida)]


@event.listens_for(Session, "before_commit")
def _encadenar_y_guardar(session: Session) -> None:
    """Inserta los eventos en cola, encadenados a la cadena existente, dentro de la transacción que está por confirmarse."""
    cola = session.info.pop(_COLA, None)
    if not cola:
        return
    session.flush()  # primero lo que la acción escribió: si falla, ningún evento queda registrado
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": CANDADO_CADENA})
    ultimo = session.execute(select(Auditoria).order_by(Auditoria.seq.desc()).limit(1)).scalar_one_or_none()
    previo = ultimo.hash if ultimo else HASH_INICIAL
    for entrada in cola:
        evento = Auditoria(**entrada["campos"], hash_previo=previo, hash="")
        evento.hash = calcular_hash(previo, evento)
        session.add(evento)
        previo = evento.hash
    session.flush()


def verificar(session: Session) -> dict:
    """Recorre la cadena completa. `ok` es True si cada hash coincide y cada fila apunta a la anterior.

    Un borrado en el extremo final de la cadena no se detecta por sí solo (no queda ninguna fila que lo delate);
    de ahí el disparador que impide borrar.
    """
    previo = HASH_INICIAL
    n = 0
    for e in session.execute(select(Auditoria).order_by(Auditoria.seq)).scalars():
        n += 1
        if e.hash_previo != previo:
            return {"ok": False, "eventos": n, "primer_error_seq": e.seq, "motivo": "la fila no apunta al hash de la anterior"}
        if calcular_hash(previo, e) != e.hash:
            return {"ok": False, "eventos": n, "primer_error_seq": e.seq, "motivo": "el contenido de la fila no coincide con su hash"}
        previo = e.hash
    return {"ok": True, "eventos": n, "primer_error_seq": None, "motivo": None}


def consulta(usuario_id=None, correo: str | None = None, desde: datetime | None = None, hasta: datetime | None = None,
             accion: str | None = None, entidad: str | None = None):
    """Sentencia SELECT con los filtros de RF-52 (usuario, fecha, acción y entidad), del más reciente al más antiguo."""
    q = select(Auditoria)
    if usuario_id:
        q = q.where(Auditoria.usuario_id == usuario_id)
    if correo:
        q = q.where(Auditoria.correo == correo)
    if desde:
        q = q.where(Auditoria.ts >= desde)
    if hasta:
        q = q.where(Auditoria.ts <= hasta)
    if accion:
        q = q.where(Auditoria.accion == accion)
    if entidad:
        q = q.where(Auditoria.entidad == entidad)
    return q.order_by(Auditoria.seq.desc())


def a_csv(eventos) -> str:
    """CSV de los eventos (RF-54). Las celdas que empiezan con =, +, - o @ se prefijan con ' para que una hoja de cálculo no las trate como fórmula."""
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow(["seq", "fecha_utc", "usuario", "rol", "accion", "entidad", "entidad_id", "resultado", "origen", "modelo_version", "detalle"])
    for e in eventos:
        fila = [e.seq, _texto_ts(e.ts), e.correo or "", e.rol or "", e.accion, e.entidad or "", e.entidad_id or "",
                e.resultado, e.origen or "", e.modelo_version or "", _canonico(e.detalle)]
        w.writerow([("'" + c) if isinstance(c, str) and c[:1] in ("=", "+", "-", "@") else c for c in fila])
    return salida.getvalue()
