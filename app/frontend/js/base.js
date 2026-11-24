"use strict";
/* Utilidades comunes de la web: DOM, formatos, llamadas a la API y sesión.
   Todo texto que viene de la API se inserta con textContent (vía `el`): nunca como HTML. */

export const vista = document.getElementById("vista");

// Estado de la API -> [texto visible, tipo de insignia (color)].
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
export const ROLES = { TEC: "Técnico de laboratorio", MIC: "Microbiólogo", CLI: "Clínico", EPI: "Epidemiólogo", ADM: "Administrador" };
// Valores que deben coincidir con backend/app/models.py (TIPOS_MUESTRA, MECANISMOS).
export const TIPOS_MUESTRA = [["otra", "Otra"], ["sangre", "Sangre"], ["orina", "Orina"], ["respiratoria", "Respiratoria"], ["herida", "Herida"]];
export const MECANISMOS = [["desconocido", "Desconocido"], ["KPC", "KPC"], ["NDM", "NDM"], ["OXA-48", "OXA-48"], ["VIM", "VIM"], ["IMP", "IMP"], ["otro", "Otro"], ["ninguno", "Ninguno"]];
export const ADVERTENCIA = "SIRFA no diagnostica ni prescribe. Toda recomendación es una hipótesis priorizada que debe ensayarse en laboratorio antes de cualquier uso clínico.";

/* ---------- DOM ---------- */
// Crea un elemento. `atributos`: "class" asigna la clase, los que empiezan con "on" son eventos; null, undefined y false se omiten.
// `hijos`: nodos o texto (el texto entra como nodo de texto, nunca como HTML).
export function el(tag, atributos, ...hijos) {
  const nodo = document.createElement(tag);
  for (const [clave, valor] of Object.entries(atributos || {})) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (clave === "class") nodo.className = valor;
    else if (clave.startsWith("on")) nodo.addEventListener(clave.slice(2), valor);
    else if (clave === "value") nodo.value = valor;
    else nodo.setAttribute(clave, valor === true ? "" : valor);
  }
  for (const hijo of hijos.flat(Infinity)) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    nodo.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return nodo;
}

export const numero = (n) => (n === null || n === undefined ? "—" : Number(n).toLocaleString("es-CL"));
export const fecha = (iso) => (iso ? new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" }).format(new Date(iso)) : "—");
export const vacio = (v) => (v === null || v === undefined || v === "" ? "—" : v);
export const porcentaje = (p, decimales = 0) => (p === null || p === undefined ? "—" : `${(p * 100).toFixed(decimales)} %`);

export function insignia(texto, tipo) {
  return el("span", { class: `insignia insignia--${tipo}` }, texto);
}
export function insigniaEstado(estado) {
  const [texto, tipo] = ESTADOS[estado] || [estado, "neutro"];
  return insignia(texto, tipo);
}
// Recuadro de mensaje. Los de tipo "error" usan role="alert" para que el lector de pantalla los anuncie de inmediato.
export function mensaje(tipo, ...contenido) {
  return el("div", { class: `mensaje mensaje--${tipo}`, role: tipo === "error" ? "alert" : "status" }, ...contenido);
}
export function opciones(pares, seleccionado) {
  return pares.map(([valor, texto]) => el("option", { value: valor, selected: valor === seleccionado }, texto));
}
export function datos(pares) {
  return el("dl", { class: "datos" }, pares.map(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
}
export function campo(etiqueta, control, ayuda) {
  return el("div", { class: "campo" }, el("label", { for: control.id }, etiqueta), control, ayuda ? el("span", { class: "ayuda" }, ayuda) : null);
}

// Tabla genérica. `columnas`: [{titulo, celda(fila), numerica?, sinCortar?}]. Con `alHacerClic` cada fila se abre con mouse o Enter.
export function tabla(columnas, filas, { alHacerClic } = {}) {
  const cuerpo = el("tbody");
  for (const fila of filas) {
    const tr = el("tr", { class: alHacerClic ? "clic" : null, tabindex: alHacerClic ? "0" : null });
    if (alHacerClic) {
      tr.addEventListener("click", () => alHacerClic(fila));
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") alHacerClic(fila); });
    }
    for (const col of columnas) {
      tr.append(el("td", { class: [col.numerica && "num", col.sinCortar && "sin-cortar"].filter(Boolean).join(" ") || null }, col.celda(fila)));
    }
    cuerpo.append(tr);
  }
  const cabecera = el("tr", {}, columnas.map((c) => el("th", { class: c.numerica ? "num" : null, scope: "col" }, c.titulo)));
  return el("div", { class: "tabla-envoltorio" }, el("table", {}, el("thead", {}, cabecera), cuerpo));
}

// Barras horizontales para el tablero: `grupos` = [{grupo, n, suprimido?}].
export function barras(grupos, vacioTexto = "Sin datos") {
  if (!grupos.length) return el("p", { class: "vacio chico" }, vacioTexto);
  const maximo = Math.max(...grupos.map((g) => g.n || 0), 1);
  return el("ul", { class: "barras" }, grupos.map((g) => el("li", {},
    el("span", { class: "barras__etiqueta" }, g.grupo),
    el("span", { class: "barras__pista" }, el("span", { class: `barras__barra${g.suprimido ? " barras__barra--suprimida" : ""}`, style: `width:${Math.max(2, (100 * (g.n || 0)) / maximo)}%` })),
    el("span", { class: "barras__valor" }, numero(g.n)))));
}

/* ---------- sesión ---------- */
const CLAVE_TOKEN = "sirfa.token";
export const sesion = { token: null, usuario: null };
try { sesion.token = sessionStorage.getItem(CLAVE_TOKEN); } catch { /* almacenamiento bloqueado: la sesión vive solo en memoria */ }

export function guardarToken(token) {
  sesion.token = token;
  try { token ? sessionStorage.setItem(CLAVE_TOKEN, token) : sessionStorage.removeItem(CLAVE_TOKEN); } catch { /* ver arriba */ }
}
export function cerrarLocalmente() {
  guardarToken(null);
  sesion.usuario = null;
}
export const puede = (permiso) => Boolean(sesion.usuario && sesion.usuario.permisos.includes(permiso));

/* ---------- API ---------- */
// Llama a la API con el token de la sesión y devuelve el JSON (o null si no hay cuerpo). Cualquier fallo lanza un Error legible.
// Un 401 cierra la sesión local y lleva a la pantalla de ingreso; si el servidor trae un token renovado, lo guarda.
export async function api(ruta, opciones = {}) {
  const cabeceras = new Headers(opciones.headers || {});
  if (sesion.token) cabeceras.set("Authorization", `Bearer ${sesion.token}`);
  if (opciones.json !== undefined) {
    cabeceras.set("Content-Type", "application/json");
    opciones = { ...opciones, body: JSON.stringify(opciones.json) };
  }
  let respuesta;
  try {
    respuesta = await fetch(ruta, { ...opciones, headers: cabeceras });
  } catch {
    throw new Error("No hay conexión con la API. ¿Está levantado el servicio?");
  }
  const renovado = respuesta.headers.get("X-Token-Renovado");
  if (renovado) guardarToken(renovado);
  if (!respuesta.ok) {
    let detalle = `Error ${respuesta.status}`;
    try {
      const cuerpo = await respuesta.json();
      if (typeof cuerpo.detail === "string") detalle = cuerpo.detail;
      else if (Array.isArray(cuerpo.detail)) detalle = cuerpo.detail.map((d) => d.msg).join("; ");
    } catch { /* la respuesta no era JSON */ }
    if (respuesta.status === 401 && !ruta.includes("/auth/login")) {
      cerrarLocalmente();
      if (location.hash !== "#/entrar") location.hash = "#/entrar";
    }
    throw new Error(detalle);
  }
  if (respuesta.status === 204) return null;
  return respuesta.json();
}

// Descarga un archivo (CSV) que exige sesión: se pide con el token y se entrega como descarga del navegador.
export async function descargar(ruta, nombre) {
  const respuesta = await fetch(ruta, { headers: { Authorization: `Bearer ${sesion.token}` } });
  if (!respuesta.ok) throw new Error(`No se pudo descargar (${respuesta.status})`);
  const url = URL.createObjectURL(await respuesta.blob());
  const a = el("a", { href: url, download: nombre });
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* ---------- sondeo ---------- */
// Actualización automática: mientras la API trabaja, la pantalla vuelve a pedir los datos cada pocos segundos.
let temporizador = null;
export function detenerSeguimiento() {
  if (temporizador) clearTimeout(temporizador);
  temporizador = null;
}
// Programa UNA ejecución futura y cancela la anterior, para que nunca haya dos sondeos a la vez.
export function seguir(funcion, ms) {
  detenerSeguimiento();
  temporizador = setTimeout(funcion, ms);
}

export function parametros(obj) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(obj)) if (v !== null && v !== undefined && v !== "") p.set(k, v);
  const texto = p.toString();
  return texto ? `?${texto}` : "";
}
