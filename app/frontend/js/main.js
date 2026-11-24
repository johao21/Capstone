"use strict";
/* Punto de entrada de la web: sesión, menú según los permisos del rol, enrutador por hash y contador de alertas. */
import { ROLES, api, cerrarLocalmente, detenerSeguimiento, el, insignia, mensaje, puede, sesion, vista } from "./base.js";
import { vistaAlertas, vistaCuenta, vistaEntrar } from "./v_acceso.js";
import { vistaAuditoria, vistaModelo, vistaUsuarios } from "./v_admin.js";
import { vistaBanco, vistaFago } from "./v_banco.js";
import { vistaSolicitud, vistaSolicitudes } from "./v_solicitudes.js";
import { vistaTablero } from "./v_tablero.js";

const menu = document.getElementById("menu");
const cajaUsuario = document.getElementById("usuario");
let contadorAlertas = 0;
let relojAlertas = null;

// Pantalla de inicio de cada rol.
const inicioDe = { TEC: "#/solicitudes", CLI: "#/solicitudes", ADM: "#/solicitudes", MIC: "#/bandeja", EPI: "#/tablero" };

// Rutas: patrón del hash, permiso que exige y pantalla. El id de una solicitud o de un fago es un UUID de 36 caracteres.
const UUID = "([0-9a-f-]{36})";
const RUTAS = [
  { patron: /^#\/solicitudes$/, permiso: "ver_solicitudes", menu: "solicitudes", vista: () => vistaSolicitudes() },
  { patron: /^#\/bandeja$/, permiso: "ver_solicitudes", menu: "bandeja", vista: () => vistaSolicitudes({ bandeja: true }) },
  { patron: new RegExp(`^#/solicitud/${UUID}$`, "i"), permiso: "ver_solicitudes", menu: null, vista: (m) => vistaSolicitud(m[1].toLowerCase()) },
  { patron: /^#\/banco$/, permiso: "consultar_banco", menu: "banco", vista: () => vistaBanco() },
  { patron: new RegExp(`^#/fago/${UUID}$`, "i"), permiso: "consultar_banco", menu: "banco", vista: (m) => vistaFago(m[1].toLowerCase()) },
  { patron: /^#\/tablero$/, permiso: "ver_tablero", menu: "tablero", vista: () => vistaTablero() },
  { patron: /^#\/modelo$/, permiso: "ver_modelo", menu: "modelo", vista: () => vistaModelo() },
  { patron: /^#\/usuarios$/, permiso: "gestionar_usuarios", menu: "usuarios", vista: () => vistaUsuarios() },
  { patron: /^#\/auditoria$/, permiso: "ver_auditoria", menu: "auditoria", vista: () => vistaAuditoria() },
  { patron: /^#\/alertas$/, permiso: "recibir_alertas", menu: "alertas", vista: () => vistaAlertas(actualizarContador) },
  { patron: /^#\/cuenta$/, permiso: null, menu: null, vista: () => vistaCuenta() },
];

function pintarMenu(actual) {
  const u = sesion.usuario;
  const entradas = [
    puede("ver_solicitudes") && (u.rol === "MIC" ? ["bandeja", "#/bandeja", "Bandeja de validación"] : ["solicitudes", "#/solicitudes", "Solicitudes"]),
    puede("consultar_banco") && ["banco", "#/banco", "Banco de fagos"],
    puede("ver_tablero") && ["tablero", "#/tablero", "Tablero"],
    puede("ver_modelo") && ["modelo", "#/modelo", "Modelo"],
    puede("gestionar_usuarios") && ["usuarios", "#/usuarios", "Usuarios"],
    puede("ver_auditoria") && ["auditoria", "#/auditoria", "Auditoría"],
    puede("recibir_alertas") && ["alertas", "#/alertas", contadorAlertas ? `Alertas (${contadorAlertas})` : "Alertas"],
  ].filter(Boolean);
  menu.replaceChildren(...entradas.map(([clave, href, texto]) => el("a", { href, "aria-current": clave === actual ? "page" : null }, texto)));
}

function pintarUsuario() {
  const u = sesion.usuario;
  cajaUsuario.replaceChildren(
    el("a", { href: "#/cuenta", class: "usuario__nombre" }, u.nombre),
    insignia(ROLES[u.rol] || u.rol, "neutro"),
    el("button", { type: "button", class: "secundario", onclick: salir }, "Salir"),
  );
}

async function actualizarContador() {
  if (!sesion.usuario || !puede("recibir_alertas")) return;
  try {
    const r = await api("/api/v1/alertas?solo_no_leidas=true&limite=1");
    if (r.no_leidas !== contadorAlertas) {
      contadorAlertas = r.no_leidas;
      const actual = RUTAS.find((x) => x.patron.test(location.hash))?.menu || null;
      pintarMenu(actual);
    }
  } catch { /* si falla, se vuelve a intentar en el próximo ciclo */ }
}

async function salir() {
  try { await api("/api/v1/auth/logout", { method: "POST" }); } catch { /* aunque falle, se cierra la sesión local */ }
  cerrarLocalmente();
  iniciar();
}

function ruta() {
  detenerSeguimiento();
  const hash = location.hash || "#/";
  if (!sesion.usuario) {
    if (hash !== "#/entrar") location.hash = "#/entrar";
    return vistaEntrar(() => { location.hash = inicioDe[sesion.usuario.rol]; iniciar(); });
  }
  if (hash === "#/" || hash === "#/entrar") { location.hash = inicioDe[sesion.usuario.rol]; return; }
  for (const r of RUTAS) {
    const m = hash.match(r.patron);
    if (!m) continue;
    pintarMenu(r.menu);
    if (r.permiso && !puede(r.permiso)) return vista.replaceChildren(mensaje("error", "Tu rol no tiene acceso a esta pantalla."));
    return r.vista(m);
  }
  vista.replaceChildren(mensaje("info", "Esa pantalla no existe."), el("p", {}, el("a", { href: inicioDe[sesion.usuario.rol] }, "Ir al inicio")));
}

// Arranque: si hay un token guardado se comprueba con la API; si no sirve, se muestra el ingreso.
async function iniciar() {
  if (relojAlertas) clearInterval(relojAlertas);
  relojAlertas = null;
  if (sesion.token && !sesion.usuario) {
    try { sesion.usuario = await api("/api/v1/auth/yo"); } catch { cerrarLocalmente(); }
  }
  document.body.classList.toggle("sin-sesion", !sesion.usuario);
  if (sesion.usuario) {
    pintarUsuario();
    pintarMenu(null);
    actualizarContador();
    relojAlertas = setInterval(actualizarContador, 30000);
  } else {
    menu.replaceChildren();
    cajaUsuario.replaceChildren();
  }
  ruta();
}

// Cada cambio de hash dibuja la pantalla nueva y vuelve al inicio de la página.
window.addEventListener("hashchange", () => { ruta(); window.scrollTo(0, 0); });
iniciar();
