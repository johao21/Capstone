"""Banco de fagos: consulta y curaduría (RF-32, RF-33, RF-37) y resumen general del sistema."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import acceso, auditoria, recomendacion
from ..db import obtener_sesion
from ..esquemas import FagoOut, ListaFagos, Resumen
from ..models import CICLOS_VIDA, ESTADOS_CURADURIA, Fago, FuenteDatos, InteraccionConocida, Solicitud, Usuario
from ..models import ahora

router = APIRouter(prefix="/api/v1", tags=["Banco de fagos"])


class InteraccionOut(BaseModel):
    cepa: str | None = None
    especie_hospedador: str
    locus_k_tipo: str | None = None
    resultado: str
    referencia: str | None = None
    fuente: str | None = None


class FagoDetalle(FagoOut):
    """Un fago con las interacciones conocidas que lo respaldan (RF-37)."""

    interacciones: list[InteraccionOut]


class FagoCambios(BaseModel):
    """Campos que el microbiólogo puede corregir (RF-33)."""

    nombre: str | None = Field(default=None, min_length=1, max_length=300)
    familia: str | None = Field(default=None, max_length=120)
    genero: str | None = Field(default=None, max_length=120)
    ciclo_vida: str | None = None
    completitud: str | None = Field(default=None, max_length=40)
    hospedador_declarado: str | None = Field(default=None, max_length=200)


class LoteIn(BaseModel):
    accion: str = Field(description="aprobar | descartar")
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


def _fago(session: Session, fago_id: uuid.UUID) -> Fago:
    fago = session.get(Fago, fago_id)
    if fago is None:
        raise HTTPException(404, "No existe el fago")
    return fago


@router.get("/fagos", response_model=ListaFagos, summary="Buscar fagos del banco")
def listar_fagos(
    q: str | None = Query(None, max_length=100, description="Texto a buscar en nombre, accesión, familia o género"),
    ciclo_vida: str | None = Query(None, description="litico | templado | desconocido"),
    estado_curaduria: str | None = Query(None, description="pendiente | aprobado | descartado"),
    hospedador: str | None = Query(None, max_length=100, description="Texto a buscar en el hospedador declarado"),
    limite: int = Query(25, ge=1, le=200),
    desplazamiento: int = Query(0, ge=0),
    _: Usuario = Depends(acceso.requiere("MIC", "ADM")),
    session: Session = Depends(obtener_sesion),
):
    """Lista paginada del banco, ordenada por nombre, con búsqueda y filtros por ciclo de vida, curaduría y hospedador."""
    if ciclo_vida is not None and ciclo_vida not in CICLOS_VIDA:
        raise HTTPException(422, f"ciclo_vida debe ser uno de: {', '.join(CICLOS_VIDA)}")
    if estado_curaduria is not None and estado_curaduria not in ESTADOS_CURADURIA:
        raise HTTPException(422, f"estado_curaduria debe ser uno de: {', '.join(ESTADOS_CURADURIA)}")
    filtro = []
    if q and q.strip():
        patron = f"%{q.strip().lower()}%"
        # Búsqueda sin distinguir mayúsculas en cuatro columnas. `coalesce` evita que un NULL
        # (familia o género sin dato) haga fallar la comparación.
        filtro.append(
            or_(
                func.lower(Fago.nombre).like(patron),
                func.lower(Fago.accesion).like(patron),
                func.lower(func.coalesce(Fago.familia, "")).like(patron),
                func.lower(func.coalesce(Fago.genero, "")).like(patron),
            )
        )
    if ciclo_vida:
        filtro.append(Fago.ciclo_vida == ciclo_vida)
    if estado_curaduria:
        filtro.append(Fago.estado_curaduria == estado_curaduria)
    if hospedador and hospedador.strip():
        filtro.append(func.lower(func.coalesce(Fago.hospedador_declarado, "")).like(f"%{hospedador.strip().lower()}%"))
    # `total` usa el mismo filtro que la página, para que el paginador de la web sepa cuántas hay en total.
    total = session.scalar(select(func.count()).select_from(Fago).where(*filtro)) or 0
    items = session.execute(select(Fago).where(*filtro).order_by(Fago.nombre).limit(limite).offset(desplazamiento)).scalars().all()
    return {"total": total, "items": items}


@router.get("/fagos/{fago_id}", response_model=FagoDetalle, summary="Detalle de un fago y sus interacciones conocidas")
def detalle_fago(fago_id: uuid.UUID, _: Usuario = Depends(acceso.requiere("MIC", "ADM")), session: Session = Depends(obtener_sesion)):
    fago = _fago(session, fago_id)
    filas = session.execute(
        select(InteraccionConocida, FuenteDatos.nombre)
        .join(FuenteDatos, FuenteDatos.id == InteraccionConocida.fuente_id)
        .where(InteraccionConocida.fago_id == fago.id)
        .order_by(InteraccionConocida.locus_k_tipo, InteraccionConocida.cepa)
        .limit(500)
    ).all()
    interacciones = [
        {"cepa": i.cepa, "especie_hospedador": i.especie_hospedador, "locus_k_tipo": i.locus_k_tipo, "resultado": i.resultado,
         "referencia": i.referencia, "fuente": fuente}
        for i, fuente in filas
    ]
    return {**{c: getattr(fago, c) for c in FagoOut.model_fields}, "interacciones": interacciones}


@router.patch("/fagos/{fago_id}", response_model=FagoOut, summary="Corregir los metadatos de un fago")
def editar_fago(fago_id: uuid.UUID, datos: FagoCambios, request: Request, mic: Usuario = Depends(acceso.requiere("MIC")),
                session: Session = Depends(obtener_sesion)):
    fago = _fago(session, fago_id)
    if datos.ciclo_vida is not None and datos.ciclo_vida not in CICLOS_VIDA:
        raise HTTPException(422, f"ciclo_vida debe ser uno de: {', '.join(CICLOS_VIDA)}")
    cambios = {}
    for campo, nuevo in datos.model_dump(exclude_unset=True).items():
        if getattr(fago, campo) != nuevo and not (campo in ("nombre", "ciclo_vida") and nuevo is None):
            cambios[campo] = {"de": getattr(fago, campo), "a": nuevo}
            setattr(fago, campo, nuevo)
    if cambios:
        auditoria.registrar(session, "fago_modificado", usuario=mic, entidad="fago", entidad_id=fago.id, origen=acceso.origen_de(request),
                            detalle={"accesion": fago.accesion, "cambios": cambios})
    session.commit()
    return fago


def _curar(session: Session, fago: Fago, mic: Usuario, nuevo: str, origen: str | None) -> None:
    """Cambia el estado de curaduría de un fago y lo deja en la auditoría."""
    if fago.estado_curaduria == nuevo:
        return
    anterior = fago.estado_curaduria
    fago.estado_curaduria, fago.curado_por, fago.curado_en = nuevo, mic.id, ahora()
    auditoria.registrar(session, f"fago_{nuevo}", usuario=mic, entidad="fago", entidad_id=fago.id, origen=origen,
                        detalle={"accesion": fago.accesion, "de": anterior})


@router.post("/fagos/lote", summary="Aprobar o descartar varios fagos a la vez")
def curar_lote(datos: LoteIn, request: Request, mic: Usuario = Depends(acceso.requiere("MIC")), session: Session = Depends(obtener_sesion)):
    if datos.accion not in ("aprobar", "descartar"):
        raise HTTPException(422, "accion debe ser 'aprobar' o 'descartar'")
    nuevo = "aprobado" if datos.accion == "aprobar" else "descartado"
    fagos = session.scalars(select(Fago).where(Fago.id.in_(datos.ids))).all()
    for fago in fagos:
        _curar(session, fago, mic, nuevo, acceso.origen_de(request))
    session.commit()
    return {"actualizados": len(fagos), "solicitados": len(datos.ids)}


@router.post("/fagos/{fago_id}/aprobar", response_model=FagoOut, summary="Aprobar un fago: desde ahora participa en las predicciones")
def aprobar(fago_id: uuid.UUID, request: Request, mic: Usuario = Depends(acceso.requiere("MIC")), session: Session = Depends(obtener_sesion)):
    fago = _fago(session, fago_id)
    _curar(session, fago, mic, "aprobado", acceso.origen_de(request))
    session.commit()
    return fago


@router.post("/fagos/{fago_id}/descartar", response_model=FagoOut, summary="Descartar un fago del banco")
def descartar(fago_id: uuid.UUID, request: Request, mic: Usuario = Depends(acceso.requiere("MIC")), session: Session = Depends(obtener_sesion)):
    fago = _fago(session, fago_id)
    _curar(session, fago, mic, "descartado", acceso.origen_de(request))
    session.commit()
    return fago


@router.get("/resumen", response_model=Resumen, summary="Conteos generales para la pantalla de inicio")
def resumen(usuario: Usuario = Depends(acceso.usuario_actual), session: Session = Depends(obtener_sesion)):
    """Solicitudes por estado (solo las que el usuario puede ver; el epidemiólogo ve el total agregado) y estadísticas del banco."""
    filtro = [] if usuario.rol == "EPI" else acceso.solicitudes_visibles(usuario)
    filas = session.execute(select(Solicitud.estado, func.count()).where(*filtro).group_by(Solicitud.estado)).all()
    return {"solicitudes_por_estado": {estado: n for estado, n in filas}, "banco": recomendacion.estadisticas_banco(session)}
