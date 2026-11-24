"use strict";
/* Pantallas de acceso: inicio de sesión, cambio de contraseña y bandeja de alertas. */
import { api, campo, el, fecha, guardarToken, insignia, mensaje, sesion, tabla, vista } from "./base.js";

// Pantalla de ingreso. Al entrar guarda el token y el perfil y vuelve al inicio.
export function vistaEntrar(alIngresar) {
  const salida = el("div", { "aria-live": "polite" });
  const correo = el("input", { type: "text", id: "correo", autocomplete: "username", inputmode: "email", required: true });
  const clave = el("input", { type: "password", id: "clave", autocomplete: "current-password", required: true });
  const boton = el("button", { type: "submit" }, "Ingresar");
  const form = el("form", { novalidate: true }, campo("Correo", correo), campo("Contraseña", clave), boton, salida);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    salida.replaceChildren();
    if (!correo.value.trim() || !clave.value) return salida.replaceChildren(mensaje("error", "Escribe el correo y la contraseña."));
    boton.disabled = true;
    boton.textContent = "Ingresando…";
    try {
      const r = await api("/api/v1/auth/login", { method: "POST", json: { correo: correo.value, password: clave.value } });
      guardarToken(r.access_token);
      sesion.usuario = r.usuario;
      alIngresar();
    } catch (err) {
      salida.replaceChildren(mensaje("error", err.message));
      boton.disabled = false;
      boton.textContent = "Ingresar";
      clave.value = "";
    }
  });
  vista.replaceChildren(el("section", { class: "tarjeta tarjeta--angosta" }, el("h1", {}, "Ingresar a SIRFA"),
    el("p", { class: "suave" }, "Usa la cuenta que te entregó el administrador."), form));
  correo.focus();
}

// Cambio de la contraseña propia (RF-05).
export function vistaCuenta() {
  const salida = el("div", { "aria-live": "polite" });
  const actual = el("input", { type: "password", id: "actual", autocomplete: "current-password" });
  const nueva = el("input", { type: "password", id: "nueva", autocomplete: "new-password" });
  const boton = el("button", { type: "submit" }, "Cambiar contraseña");
  const form = el("form", { novalidate: true }, campo("Contraseña actual", actual), campo("Contraseña nueva", nueva, "Al menos 10 caracteres."), boton, salida);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/api/v1/auth/cambiar-password", { method: "POST", json: { password_actual: actual.value, password_nueva: nueva.value } });
      actual.value = nueva.value = "";
      salida.replaceChildren(mensaje("ok", "Contraseña actualizada."));
    } catch (err) {
      salida.replaceChildren(mensaje("error", err.message));
    }
  });
  const u = sesion.usuario;
  vista.replaceChildren(
    el("h1", {}, "Mi cuenta"),
    el("p", { class: "suave" }, `${u.nombre} · ${u.correo} · ${u.centro_nombre}`),
    el("section", { class: "tarjeta tarjeta--angosta" }, el("h2", {}, "Cambiar la contraseña"), form),
  );
}

// Bandeja de alertas con marca de leída (RF-65).
export async function vistaAlertas(actualizarContador) {
  vista.replaceChildren(el("p", { class: "suave" }, "Cargando…"));
  try {
    const r = await api("/api/v1/alertas?limite=100");
    const marcarTodas = el("button", { type: "button", class: "secundario", disabled: r.no_leidas === 0, onclick: async () => {
      await api("/api/v1/alertas/leer-todas", { method: "POST" });
      actualizarContador();
      vistaAlertas(actualizarContador);
    } }, "Marcar todas como leídas");
    vista.replaceChildren(
      el("div", { class: "cabecera-vista" }, el("h1", {}, "Alertas"), insignia(`${r.no_leidas} sin leer`, r.no_leidas ? "alerta" : "neutro")),
      marcarTodas,
      r.items.length
        ? tabla([
            { titulo: "", celda: (a) => (a.leida ? "" : insignia("nueva", "alerta")) },
            { titulo: "Aviso", celda: (a) => a.mensaje },
            { titulo: "Cuándo", sinCortar: true, celda: (a) => fecha(a.creada_en) },
          ], r.items, { alHacerClic: async (a) => {
            if (!a.leida) await api(`/api/v1/alertas/${a.id}/leida`, { method: "POST" });
            actualizarContador();
            location.hash = `#/solicitud/${a.solicitud_id}`;
          } })
        : el("p", { class: "vacio" }, "No tienes alertas."),
    );
  } catch (e) {
    vista.replaceChildren(mensaje("error", e.message));
  }
}
