"""Alta de una solicitud: aislado, genoma y trabajo de pipeline (RF-01, RF-09).

Lo usa la API (`POST /api/v1/solicitudes`), que pasa el técnico autenticado. Sin técnico (herramientas de
consola y pruebas) se atribuye a un centro y un usuario de demostración que no pueden iniciar sesión.
"""
from __future__ import annotations

import hashlib
import shutil
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Aislado, Centro, Genoma, Solicitud, SolicitudHistorial, Trabajo, Usuario

CODIGO_CENTRO = "DEMO"
CORREO_DEMO = "demo.tecnico@sirfa.local"


def sha256_de(ruta: Path) -> str:
    """Huella SHA-256 del archivo, leído por bloques de 1 MiB para no cargar el genoma entero en memoria."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        # iter(callable, centinela): sigue llamando a f.read hasta que devuelve b"" (fin del archivo).
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def usuario_demo(session: Session) -> Usuario:
    """Devuelve el técnico de demostración, creando él y su centro la primera vez."""
    centro = session.execute(select(Centro).where(Centro.codigo == CODIGO_CENTRO)).scalar_one_or_none()
    if centro is None:
        centro = Centro(codigo=CODIGO_CENTRO, nombre="Centro de demostración")
        session.add(centro)
        session.flush()  # flush para obtener centro.id antes de crear el usuario
    usuario = session.execute(select(Usuario).where(Usuario.correo == CORREO_DEMO)).scalar_one_or_none()
    if usuario is None:
        # El hash no corresponde a ninguna contraseña: la cuenta existe solo para atribuir la solicitud.
        usuario = Usuario(
            correo=CORREO_DEMO, nombre="Técnico de demostración", password_hash="!sin-acceso", rol="TEC", centro_id=centro.id
        )
        session.add(usuario)
        session.flush()
    return usuario


def crear_solicitud(
    session: Session,
    fasta: Path,
    codigo: str,
    genomas_dir: Path,
    *,
    especie_declarada: str = "Klebsiella pneumoniae",
    tipo_muestra: str = "otra",
    mecanismo_resistencia: str | None = "desconocido",
    fecha_aislamiento: date | None = None,
    observaciones: str | None = None,
    codigo_unico: bool = True,
    nombre_original: str | None = None,
    usuario: Usuario | None = None,
    solicitante_id: uuid.UUID | None = None,
) -> Solicitud:
    """Deja un aislado, su genoma y una solicitud Registrada con un trabajo `pipeline` pendiente.

    Con `codigo_unico` se agrega un sufijo aleatorio al código interno (útil en la demo por consola);
    la API lo desactiva para que un código repetido en el centro se informe como conflicto.

    `usuario` es quien registra (su centro es el del aislado); `solicitante_id`, el clínico que pide la
    recomendación (RF-11). Sin ellos, ambos son el técnico de demostración.

    No hace `commit`: lo hace quien llama, para que todo se guarde o se revierta junto.
    """
    usuario = usuario or usuario_demo(session)
    genomas_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256_de(fasta)
    # `suffixes` conserva extensiones dobles como .fasta.gz.
    destino = genomas_dir / f"{digest}{''.join(fasta.suffixes)}"
    # Si ya existe un archivo con el mismo contenido (mismo SHA-256) no se vuelve a copiar.
    if not destino.exists():
        shutil.copyfile(fasta, destino)  # el nombre original no forma parte de la ruta (RNF-07)

    aislado = Aislado(
        codigo_interno=f"{codigo}-{uuid.uuid4().hex[:6]}" if codigo_unico else codigo,
        centro_id=usuario.centro_id,
        fecha_aislamiento=fecha_aislamiento or date.today(),
        especie_declarada=especie_declarada,
        tipo_muestra=tipo_muestra,
        mecanismo_resistencia=mecanismo_resistencia,
        observaciones=observaciones,
        creado_por=usuario.id,
    )
    session.add(aislado)
    session.flush()  # cada flush entrega el id que necesita la fila siguiente (aislado -> genoma -> solicitud)
    genoma = Genoma(
        aislado_id=aislado.id,
        ruta_archivo=str(destino),
        sha256=digest,
        tamano_bytes=destino.stat().st_size,
        nombre_original=nombre_original or fasta.name,
    )
    session.add(genoma)
    session.flush()
    solicitud = Solicitud(
        aislado_id=aislado.id,
        genoma_id=genoma.id,
        centro_id=usuario.centro_id,
        solicitante_id=solicitante_id or usuario.id,
        creada_por=usuario.id,
    )
    session.add(solicitud)
    session.flush()
    # Primera fila del historial (estado_anterior=None) y el trabajo que el worker va a reclamar.
    session.add(SolicitudHistorial(solicitud_id=solicitud.id, estado_anterior=None, estado_nuevo="registrada", usuario_id=usuario.id))
    session.add(Trabajo(tipo="pipeline", solicitud_id=solicitud.id))
    session.flush()
    return solicitud
