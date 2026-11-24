// Estados de una solicitud y roles, tal como los entrega la API (backend/app/models.py y acceso.py).
// Es lo mismo que muestra la web (frontend/js/base.js): si cambia allá, se cambia acá.

// estado de la API -> [texto visible, tono]. Los tonos los colorea tema.js.
export const ESTADOS = {
  registrada: ["Registrada", "curso"],
  en_analisis: ["En análisis", "curso"],
  prediccion_lista: ["Predicción lista", "alerta"],
  en_validacion: ["En validación", "curso"],
  emitida: ["Emitida", "ok"],
  cerrada: ["Cerrada", "neutro"],
  rechazada: ["Rechazada", "error"],
  anulada: ["Anulada", "neutro"],
  error: ["Error", "error"],
};

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
export const FILTROS = [
  { clave: "todas", etiqueta: "Todas", estados: null },
  { clave: "curso", etiqueta: "En curso", estados: ["registrada", "en_analisis", "prediccion_lista", "en_validacion"] },
  { clave: "emitidas", etiqueta: "Emitidas", estados: ["emitida", "cerrada"] },
  { clave: "sin_resultado", etiqueta: "Sin resultado", estados: ["rechazada", "anulada", "error"] },
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
