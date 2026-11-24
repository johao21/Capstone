"use strict";
/* Administración: usuarios y centros, consulta de la auditoría y modelo vigente. */
import { ROLES, api, campo, datos, descargar, detenerSeguimiento, el, fecha, insignia, mensaje, numero, opciones, parametros, porcentaje, tabla, vacio, vista } from "./base.js";

const ROLES_OPCIONES = Object.entries(ROLES);

/* ---------- usuarios y centros ---------- */
export async function vistaUsuarios() {
  detenerSeguimiento();
  vista.replaceChildren(el("p", { class: "suave" }, "Cargando…"));
  try {
    const [lista, centros] = await Promise.all([api("/api/v1/usuarios?limite=500"), api("/api/v1/centros")]);
    const centroDe = Object.fromEntries(centros.map((c) => [c.id, c.codigo]));
    const salida = el("div", { "aria-live": "polite" });
    const recargar = () => vistaUsuarios();
    const intentar = (promesa) => promesa.then(recargar).catch((e) => salida.replaceChildren(mensaje("error", e.message)));

    const filas = lista.items.map((u) => {
      const rol = el("select", { "aria-label": `Rol de ${u.nombre}` }, opciones(ROLES_OPCIONES, u.rol));
      const centro = el("select", { "aria-label": `Centro de ${u.nombre}` }, opciones(centros.map((c) => [c.id, c.codigo]), u.centro_id));
      return el("tr", {},
        el("td", {}, u.nombre, el("br"), el("span", { class: "suave chico" }, u.correo)),
        el("td", {}, rol), el("td", {}, centro),
        el("td", {}, u.activo ? insignia("activo", "ok") : insignia("desactivado", "neutro"), u.bloqueado_hasta && new Date(u.bloqueado_hasta) > new Date() ? insignia("bloqueado", "alerta") : null),
        el("td", { class: "acciones-fila" },
          el("button", { type: "button", class: "secundario", onclick: () => intentar(api(`/api/v1/usuarios/${u.id}`, { method: "PATCH", json: { rol: rol.value, centro_id: centro.value } })) }, "Guardar rol y centro"),
          el("button", { type: "button", class: u.activo ? "peligro" : "secundario", onclick: () => intentar(api(`/api/v1/usuarios/${u.id}`, { method: "PATCH", json: { activo: !u.activo } })) }, u.activo ? "Desactivar" : "Reactivar"),
          el("button", { type: "button", class: "secundario", onclick: async () => {
            try {
              const r = await api(`/api/v1/usuarios/${u.id}/restablecer-password`, { method: "POST", json: {} });
              salida.replaceChildren(mensaje("ok", `Contraseña temporal de ${u.correo}: `, el("code", {}, r.password_temporal), ". Se muestra una sola vez; pídele que la cambie al ingresar."));
            } catch (e) { salida.replaceChildren(mensaje("error", e.message)); }
          } }, "Restablecer contraseña")));
    });

    const nuevo = {
      correo: el("input", { type: "text", id: "u-correo", autocomplete: "off" }), nombre: el("input", { type: "text", id: "u-nombre", autocomplete: "off" }),
      rol: el("select", { id: "u-rol" }, opciones(ROLES_OPCIONES, "TEC")), centro: el("select", { id: "u-centro" }, opciones(centros.map((c) => [c.id, `${c.codigo} · ${c.nombre}`]))),
      clave: el("input", { type: "password", id: "u-clave", autocomplete: "new-password" }),
    };
    const crear = el("form", { novalidate: true },
      el("div", { class: "fila-campos" }, campo("Correo", nuevo.correo), campo("Nombre", nuevo.nombre), campo("Rol", nuevo.rol), campo("Centro", nuevo.centro), campo("Contraseña inicial", nuevo.clave, "Al menos 10 caracteres.")),
      el("button", { type: "submit" }, "Crear usuario"));
    crear.addEventListener("submit", (e) => {
      e.preventDefault();
      intentar(api("/api/v1/usuarios", { method: "POST", json: { correo: nuevo.correo.value, nombre: nuevo.nombre.value, rol: nuevo.rol.value, centro_id: nuevo.centro.value, password: nuevo.clave.value } }));
    });

    const codigo = el("input", { type: "text", id: "c-codigo", autocomplete: "off" });
    const nombreCentro = el("input", { type: "text", id: "c-nombre", autocomplete: "off" });
    const crearCentro = el("form", { novalidate: true }, el("div", { class: "fila-campos" }, campo("Código del centro", codigo), campo("Nombre", nombreCentro)), el("button", { type: "submit", class: "secundario" }, "Crear centro"));
    crearCentro.addEventListener("submit", (e) => { e.preventDefault(); intentar(api("/api/v1/centros", { method: "POST", json: { codigo: codigo.value, nombre: nombreCentro.value } })); });

    vista.replaceChildren(
      el("h1", {}, "Usuarios"),
      el("p", { class: "suave" }, "Cada usuario tiene un único rol y un centro. Los usuarios no se eliminan: se desactivan y conservan su historial."),
      salida,
      el("section", { class: "tarjeta" }, el("h2", {}, "Nuevo usuario"), crear),
      el("section", { class: "tarjeta" }, el("h2", {}, `Usuarios (${numero(lista.total)})`),
        el("div", { class: "tabla-envoltorio" }, el("table", {}, el("thead", {}, el("tr", {}, ["Usuario", "Rol", "Centro", "Estado", "Acciones"].map((t) => el("th", { scope: "col" }, t)))), el("tbody", {}, filas)))),
      el("section", { class: "tarjeta" }, el("h2", {}, `Centros (${centros.length})`), el("p", { class: "suave chico" }, centros.map((c) => `${c.codigo} · ${c.nombre}`).join(" — ")), crearCentro),
    );
  } catch (e) {
    vista.replaceChildren(mensaje("error", e.message));
  }
}

/* ---------- auditoría ---------- */
export async function vistaAuditoria() {
  detenerSeguimiento();
  const filtros = { usuario: "", accion: "", entidad: "", desde: "", hasta: "" };
  const POR_PAGINA = 50;
  let pagina = 0;
  const acciones = await api("/api/v1/auditoria/acciones").catch(() => []);
  const resultado = el("div");
  const verificacion = el("div", { "aria-live": "polite" });

  async function cargar() {
    try {
      const r = await api(`/api/v1/auditoria${parametros({ ...filtros, limite: POR_PAGINA, desplazamiento: pagina * POR_PAGINA })}`);
      const paginas = Math.max(1, Math.ceil(r.total / POR_PAGINA));
      resultado.replaceChildren(
        el("p", { class: "suave chico" }, `${numero(r.total)} eventos · página ${pagina + 1} de ${paginas}`),
        tabla([
          { titulo: "#", numerica: true, celda: (e) => e.seq },
          { titulo: "Fecha (UTC)", sinCortar: true, celda: (e) => fecha(e.ts) },
          { titulo: "Usuario", celda: (e) => vacio(e.correo) }, { titulo: "Rol", celda: (e) => vacio(e.rol) },
          { titulo: "Acción", celda: (e) => e.accion },
          { titulo: "Entidad", celda: (e) => (e.entidad ? el("span", {}, e.entidad, e.entidad_id ? el("span", { class: "mono suave" }, ` ${String(e.entidad_id).slice(0, 8)}`) : null) : "—") },
          { titulo: "Resultado", celda: (e) => insignia(e.resultado, { ok: "ok", fallido: "error", denegado: "alerta" }[e.resultado] || "neutro") },
          { titulo: "Origen", celda: (e) => vacio(e.origen) },
          { titulo: "Modelo", celda: (e) => vacio(e.modelo_version) },
        ], r.items),
        el("div", { class: "paginacion" },
          el("button", { type: "button", class: "secundario", disabled: pagina === 0, onclick: () => { pagina--; cargar(); } }, "Anterior"),
          el("button", { type: "button", class: "secundario", disabled: pagina + 1 >= paginas, onclick: () => { pagina++; cargar(); } }, "Siguiente")));
    } catch (e) {
      resultado.replaceChildren(mensaje("error", e.message));
    }
  }

  const usuario = el("input", { type: "text", id: "a-usuario", placeholder: "correo@…", autocomplete: "off" });
  const accion = el("select", { id: "a-accion" }, el("option", { value: "" }, "Todas"), acciones.map((a) => el("option", { value: a }, a)));
  const entidad = el("select", { id: "a-entidad" }, el("option", { value: "" }, "Todas"), ["solicitud", "usuario", "fago", "aislado", "genoma", "centro", "auditoria", "endpoint"].map((x) => el("option", { value: x }, x)));
  const desde = el("input", { type: "date", id: "a-desde" });
  const hasta = el("input", { type: "date", id: "a-hasta" });
  const aplicar = () => {
    Object.assign(filtros, { usuario: usuario.value.trim(), accion: accion.value, entidad: entidad.value, desde: desde.value ? `${desde.value}T00:00:00` : "", hasta: hasta.value ? `${hasta.value}T23:59:59` : "" });
    pagina = 0;
    cargar();
  };
  for (const c of [usuario, accion, entidad, desde, hasta]) c.addEventListener("change", aplicar);

  vista.replaceChildren(
    el("h1", {}, "Auditoría"),
    el("p", { class: "suave" }, "Registro de solo adición: nadie puede modificar ni borrar un evento, y cada uno queda encadenado al anterior mediante un hash."),
    el("section", { class: "tarjeta" },
      el("div", { class: "fila-campos" }, campo("Usuario", usuario), campo("Acción", accion), campo("Entidad", entidad), campo("Desde", desde), campo("Hasta", hasta)),
      el("div", { class: "acciones" },
        el("button", { type: "button", class: "secundario", onclick: async () => {
          try {
            const v = await api("/api/v1/auditoria/verificar");
            verificacion.replaceChildren(v.ok ? mensaje("ok", `La cadena es íntegra: ${numero(v.eventos)} eventos verificados.`) : mensaje("error", `La cadena se rompe en el evento ${v.primer_error_seq}: ${v.motivo}.`));
          } catch (e) { verificacion.replaceChildren(mensaje("error", e.message)); }
        } }, "Verificar la cadena de hashes"),
        el("button", { type: "button", class: "secundario", onclick: () => descargar(`/api/v1/auditoria/exportar.csv${parametros(filtros)}`, "auditoria_sirfa.csv").catch((e) => alert(e.message)) }, "Exportar a CSV")),
      verificacion),
    el("section", { class: "tarjeta" }, resultado),
  );
  await cargar();
}

/* ---------- modelo ---------- */
export async function vistaModelo() {
  detenerSeguimiento();
  vista.replaceChildren(el("p", { class: "suave" }, "Cargando…"));
  try {
    const m = await api("/api/v1/modelo");
    if (!m.disponible) return vista.replaceChildren(el("h1", {}, "Modelo de predicción"), mensaje("alerta", m.mensaje), el("p", { class: "suave" }, `Interacciones conocidas en el banco: ${numero(m.interacciones_en_banco)}.`));
    const k = m.metricas;
    const filaMetricas = (titulo, v, base) => v && [titulo, el("span", {},
      `AUC ${v.auc} · acierto en el top-5 ${porcentaje(v.top5)} (línea base ${porcentaje(base?.top5)}, al azar ${porcentaje(v.top5_azar)}) · sensibilidad ${porcentaje(v.sensibilidad)} · especificidad ${porcentaje(v.especificidad)}`)];
    vista.replaceChildren(
      el("div", { class: "cabecera-vista" }, el("h1", {}, "Modelo de predicción"), insignia(m.version, "ok")),
      el("section", { class: "tarjeta" }, el("h2", {}, "Versión vigente"), datos([
        ["Algoritmo", m.algoritmo], ["Entrenado", fecha(m.entrenado_en)], ["Filas de entrenamiento", numero(m.n_entrenamiento)],
        ["Datos", `${numero(k.datos?.cepas)} cepas · ${numero(k.datos?.fagos)} fagos · ${numero(k.datos?.pares_ensayados)} pares ensayados (${numero(k.datos?.pares_positivos)} positivos)`],
        ["Fuente", vacio(m.parametros?.fuente)],
        m.parametros?.umbral_candidato !== undefined ? ["Umbral de mejor equilibrio", `${porcentaje(m.parametros.umbral_candidato, 1)} de probabilidad estimada (punto de la validación con mejor sensibilidad + especificidad; no es el umbral de las brechas del tablero)`] : null,
      ].filter(Boolean))),
      el("section", { class: "tarjeta" }, el("h2", {}, "Métricas de validación cruzada"),
        el("p", { class: "suave chico" }, "El acierto en el top-5 es la proporción de cepas para las que al menos uno de los 5 primeros fagos sí las infecta, entre los fagos ensayados con esa cepa. La línea base ordena los fagos solo por cuántas cepas infectan, sin mirar al hospedador."),
        datos([
          filaMetricas("Aislado de un tipo K no visto", { auc: k.auc, top5: k.top5, top5_azar: k.top5_azar, sensibilidad: k.sensibilidad, especificidad: k.especificidad }, k.linea_base_frecuencia_del_fago),
          filaMetricas("Cepa nueva con tipo K representado", k.validacion_por_cepa, k.validacion_por_cepa?.linea_base_frecuencia_del_fago),
          ["Esquema", vacio(k.esquema)],
        ].filter((x) => x && x[1]))),
      mensaje("alerta", "Con un tipo de locus K que el modelo no vio, no supera a la línea base: por eso esos resultados se marcan de baja confianza. El modelo ayuda a priorizar, no es un resultado validado: toda recomendación debe ensayarse en laboratorio."),
    );
  } catch (e) {
    vista.replaceChildren(mensaje("error", e.message));
  }
}
