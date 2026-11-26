// Estados de una solicitud y roles, tal como los entrega la API (backend/app/models.py y acceso.py).
// Es lo mismo que muestra la web (frontend/js/base.js): si cambia allá, se cambia acá.

// estado de la API -> [texto visible, tono]. Los tonos los colorea tema.js.
export const ESTADOS = {
  registrada: ["Registrada", "curso"],
  en_analisis: ["En análisis", "curso"],
  prediccion_lista: ["Predicción lista", "alerta"],
  en_validacion: ["En validación", "validacion"],
  emitida: ["Emitida", "ok"],
  cerrada: ["Cerrada", "neutro"],
  rechazada: ["Rechazada", "error"],
  anulada: ["Anulada", "neutro"],
  error: ["Error", "error"],
};

// Íconos de MaterialCommunityIcons. Cada estado tiene el suyo, para reconocerlo sin leer.
export const ICONOS_ESTADO = {
  registrada: "clipboard-text-outline",
  en_analisis: "dna",
  prediccion_lista: "chart-box-outline",
  en_validacion: "microscope",
  emitida: "check-circle",
  cerrada: "archive-outline",
  rechazada: "close-circle",
  anulada: "cancel",
  error: "alert",
};

// Nombre corto (una palabra, para que quepa bajo cada círculo) e ícono de cada etapa del recorrido.
export const ETAPAS = { registrada: "Registro", en_analisis: "Análisis", prediccion_lista: "Predicción", en_validacion: "Validación", emitida: "Emisión" };
export const ICONOS_PASO = { ...ICONOS_ESTADO, emitida: "flag-checkered" };

// El camino feliz de una solicitud, en orden. «cerrada» es la misma meta que «emitida», ya archivada.
export const PASOS = ["registrada", "en_analisis", "prediccion_lista", "en_validacion", "emitida"];

/**
 * Dibujo del avance de una solicitud: una lista de pasos, cada uno «hecho», «actual» o «pendiente».
 * Las solicitudes que se detuvieron (rechazada, anulada, error) no están en el camino: `detenido` es verdadero
 * y no hay pasos que dibujar, porque con solo el estado no se sabe hasta dónde llegaron.
 */
export function progreso(estado) {
  const terminada = estado === "emitida" || estado === "cerrada";
  const indice = terminada ? PASOS.length - 1 : PASOS.indexOf(estado);
  if (indice < 0) {
    return { pasos: [], actual: -1, total: PASOS.length, detenido: ESTADOS_CON_MOTIVO.includes(estado), resumen: null };
  }
  const pasos = PASOS.map((clave, i) => ({
    clave,
    texto: ETAPAS[clave],
    icono: ICONOS_PASO[clave],
    situacion: terminada || i < indice ? "hecho" : i === indice ? "actual" : "pendiente",
  }));
  const resumen = estado === "cerrada" ? "Las 5 etapas están completas · solicitud cerrada" : estado === "emitida" ? "Las 5 etapas están completas" : `Etapa ${indice + 1} de ${PASOS.length}: ${ESTADOS[estado][0]}`;
  return { pasos, actual: indice, total: PASOS.length, detenido: false, resumen };
}

export const ROLES = {
  TEC: "Técnico de laboratorio",
  MIC: "Microbiólogo",
  CLI: "Clínico solicitante",
  EPI: "Epidemiólogo",
  ADM: "Administrador",
};

// Estados con recomendación emitida: solo en ellos existe /recomendacion-emitida (en los demás responde 404).
export const ESTADOS_CON_RECOMENDACION = ["emitida", "cerrada"];

// Estados en los que `motivo_estado` explica por qué la solicitud no avanza.
export const ESTADOS_CON_MOTIVO = ["rechazada", "anulada", "error"];

// Resultado del ensayo de laboratorio de un candidato -> [texto, tono].
export const ENSAYOS = {
  infecta: ["Ensayo: infecta", "ok"],
  no_infecta: ["Ensayo: no infecta", "error"],
  no_ensayado: ["Sin ensayar", "neutro"],
};

// Advertencia obligatoria (RF-45). La API la envía con cada recomendación; esta copia solo se usa si faltara.
export const ADVERTENCIA =
  "SIRFA no diagnostica ni prescribe. Toda recomendación es una hipótesis priorizada que debe ensayarse en laboratorio antes de cualquier uso clínico; apoya la decisión de un profesional, no la reemplaza.";

// Agrupaciones del filtro de la lista: cada una reúne varios estados.
// `icono` y `tono` son los del cuadro que se dibuja en la lista.
export const FILTROS = [
  { clave: "todas", etiqueta: "Todas", estados: null, icono: "format-list-bulleted", tono: "neutro" },
  { clave: "curso", etiqueta: "En curso", estados: ["registrada", "en_analisis", "prediccion_lista", "en_validacion"], icono: "progress-clock", tono: "curso" },
  { clave: "emitidas", etiqueta: "Emitidas", estados: ["emitida", "cerrada"], icono: "check-circle-outline", tono: "ok" },
  { clave: "sin_resultado", etiqueta: "Sin resultado", estados: ["rechazada", "anulada", "error"], icono: "alert-circle-outline", tono: "alerta" },
];

/**
 * Qué decirle al usuario cuando la solicitud no tiene recomendación emitida. Depende del estado:
 * en las que ya terminaron sin emitirla nunca llegará una, y decir «te avisaremos» sería engañoso.
 */
export function mensajeSinRecomendacion(estado) {
  if (estado === "rechazada" || estado === "anulada") {
    return { titulo: "Esta solicitud no tiene recomendación", texto: "Terminó sin llegar a emitirse (ver el motivo más arriba, si lo hay)." };
  }
  if (estado === "error") {
    return { titulo: "El análisis no pudo completarse", texto: "Aún no hay recomendación. El técnico de laboratorio puede reintentar el análisis desde la plataforma web." };
  }
  return { titulo: "Todavía no hay recomendación emitida", texto: "Cuando un microbiólogo valide y emita la recomendación, la verás acá y recibirás una alerta." };
}

/** Texto y tono de un estado; un estado desconocido se muestra tal cual, en tono neutro. */
export function infoEstado(estado) {
  return ESTADOS[estado] ? { texto: ESTADOS[estado][0], tono: ESTADOS[estado][1] } : { texto: String(estado ?? "—"), tono: "neutro" };
}

/** Ícono de un estado; uno desconocido recibe un signo de interrogación. */
export function iconoEstado(estado) {
  return ICONOS_ESTADO[estado] ?? "help-circle-outline";
}

// Ícono del resultado del ensayo de laboratorio de un candidato.
export const ICONOS_ENSAYO = { infecta: "check-circle", no_infecta: "close-circle", no_ensayado: "flask-empty-outline" };

export function iconoEnsayo(resultado) {
  return ICONOS_ENSAYO[resultado] ?? ICONOS_ENSAYO.no_ensayado;
}

/** Fracción de la barra de puntaje (0 a 1). Un valor que no es número da 0; uno fuera de rango se recorta. */
export function fraccionPuntaje(valor) {
  return typeof valor === "number" && Number.isFinite(valor) ? Math.min(1, Math.max(0, valor)) : 0;
}

/** Iniciales para el círculo de la cuenta: «Ana Pérez Soto» -> «AP». */
export function iniciales(nombre) {
  const partes = String(nombre ?? "").trim().split(/\s+/).filter(Boolean);
  if (partes.length === 0) return "?";
  return (partes[0][0] + (partes.length > 1 ? partes[1][0] : "")).toUpperCase();
}

export function infoEnsayo(resultado) {
  return ENSAYOS[resultado] ? { texto: ENSAYOS[resultado][0], tono: ENSAYOS[resultado][1] } : { texto: "Sin ensayar", tono: "neutro" };
}

export function nombreRol(rol) {
  return ROLES[rol] ?? String(rol ?? "");
}

/** Filtra las solicitudes ya cargadas según la clave de FILTROS. */
export function filtrarSolicitudes(items, clave) {
  const filtro = FILTROS.find((f) => f.clave === clave);
  if (!filtro || !filtro.estados) return items;
  return items.filter((s) => filtro.estados.includes(s.estado));
}

/** Cuántas solicitudes cae en cada filtro, para mostrarlo en los botones. */
export function contarPorFiltro(items) {
  return Object.fromEntries(FILTROS.map((f) => [f.clave, filtrarSolicitudes(items, f.clave).length]));
}

/**
 * Qué puede hacer cada rol en la app. Sale de los permisos que entrega la API en `usuario.permisos`
 * (la misma matriz que usa el servidor), de modo que la app nunca decide por su cuenta.
 */
export function capacidades(usuario) {
  const permisos = new Set(usuario?.permisos ?? []);
  return { verSolicitudes: permisos.has("ver_solicitudes"), recibirAlertas: permisos.has("recibir_alertas") };
}
