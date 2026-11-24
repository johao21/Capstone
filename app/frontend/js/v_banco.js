"use strict";
/* Banco de fagos: consulta para el microbiólogo y el administrador; la curaduría (editar, aprobar, descartar) es solo del microbiólogo. */
import { api, campo, datos, detenerSeguimiento, el, fecha, insignia, mensaje, numero, opciones, parametros, puede, tabla, vacio, vista } from "./base.js";

const POR_PAGINA = 25;
const CICLOS = [["litico", "Lítico"], ["templado", "Templado"], ["desconocido", "Desconocido"]];
const CURADURIA = [["pendiente", "Pendiente"], ["aprobado", "Aprobado"], ["descartado", "Descartado"]];
const tipoCuraduria = { aprobado: "ok", descartado: "error", pendiente: "neutro" };

export async function vistaBanco() {
  detenerSeguimiento();
  const curador = puede("curar_banco");
  const filtros = { q: "", ciclo_vida: "", estado_curaduria: "", hospedador: "" };
  const seleccion = new Set();
  let pagina = 0;
  const info = el("p", { class: "suave chico", "aria-live": "polite" });
  const resultado = el("div");
  const salida = el("div", { "aria-live": "polite" });

  async function cargar() {
    try {
      const r = await api(`/api/v1/fagos${parametros({ ...filtros, limite: POR_PAGINA, desplazamiento: pagina * POR_PAGINA })}`);
      const paginas = Math.max(1, Math.ceil(r.total / POR_PAGINA));
      info.textContent = `${numero(r.total)} ${r.total === 1 ? "fago" : "fagos"} · página ${pagina + 1} de ${paginas}${seleccion.size ? ` · ${seleccion.size} seleccionados` : ""}`;
      const casilla = (f) => el("input", { type: "checkbox", "aria-label": `Seleccionar ${f.nombre}`, checked: seleccion.has(f.id), onclick: (e) => e.stopPropagation(), onchange: (e) => {
        e.target.checked ? seleccion.add(f.id) : seleccion.delete(f.id);
        info.textContent = info.textContent.replace(/ · \d+ seleccionados/, "") + (seleccion.size ? ` · ${seleccion.size} seleccionados` : "");
      } });
      resultado.replaceChildren(
        r.items.length
          ? tabla([
              ...(curador ? [{ titulo: "", celda: casilla }] : []),
              { titulo: "Nombre", celda: (f) => f.nombre },
              { titulo: "Accesión", celda: (f) => el("span", { class: "mono" }, f.accesion) },
              { titulo: "Familia", celda: (f) => vacio(f.familia) },
              { titulo: "Longitud", numerica: true, celda: (f) => (f.longitud_pb ? `${numero(f.longitud_pb)} pb` : "—") },
              { titulo: "Ciclo de vida", celda: (f) => (f.ciclo_vida === "desconocido" ? insignia("sin curar", "neutro") : f.ciclo_vida) },
              { titulo: "Curaduría", celda: (f) => insignia(f.estado_curaduria, tipoCuraduria[f.estado_curaduria] || "neutro") },
            ], r.items, { alHacerClic: (f) => { location.hash = `#/fago/${f.id}`; } })
          : el("p", { class: "vacio" }, "Ningún fago coincide con la búsqueda."),
        el("div", { class: "paginacion" },
          el("button", { type: "button", class: "secundario", disabled: pagina === 0, onclick: () => { pagina--; cargar(); } }, "Anterior"),
          el("button", { type: "button", class: "secundario", disabled: pagina + 1 >= paginas, onclick: () => { pagina++; cargar(); } }, "Siguiente")),
      );
    } catch (e) {
      resultado.replaceChildren(mensaje("error", e.message));
    }
  }

  async function curarLote(accion, ids) {
    try {
      let total = 0;
      for (let i = 0; i < ids.length; i += 500) {
        const r = await api("/api/v1/fagos/lote", { method: "POST", json: { accion, ids: ids.slice(i, i + 500) } });
        total += r.actualizados;
      }
      seleccion.clear();
      salida.replaceChildren(mensaje("ok", `${numero(total)} fagos ${accion === "aprobar" ? "aprobados" : "descartados"}.`));
      cargar();
    } catch (e) {
      salida.replaceChildren(mensaje("error", e.message));
    }
  }

  // "Todos los pendientes de la búsqueda": recorre las páginas con los filtros actuales y junta los ids.
  async function idsPendientesDeLaBusqueda() {
    const ids = [];
    for (let desplazamiento = 0; ; desplazamiento += 200) {
      const r = await api(`/api/v1/fagos${parametros({ ...filtros, estado_curaduria: "pendiente", limite: 200, desplazamiento })}`);
      ids.push(...r.items.map((f) => f.id));
      if (desplazamiento + 200 >= r.total) return ids;
    }
  }

  let espera;
  const buscador = el("input", { type: "search", id: "q", placeholder: "Nombre, accesión, familia o género", autocomplete: "off" });
  buscador.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(() => { filtros.q = buscador.value.trim(); pagina = 0; cargar(); }, 250); });
  const ciclo = el("select", { id: "f-ciclo" }, el("option", { value: "" }, "Todos"), opciones(CICLOS));
  const cur = el("select", { id: "f-cur" }, el("option", { value: "" }, "Todos"), opciones(CURADURIA));
  const hosp = el("input", { type: "search", id: "f-hosp", placeholder: "Hospedador declarado", autocomplete: "off" });
  ciclo.addEventListener("change", () => { filtros.ciclo_vida = ciclo.value; pagina = 0; cargar(); });
  cur.addEventListener("change", () => { filtros.estado_curaduria = cur.value; pagina = 0; cargar(); });
  hosp.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(() => { filtros.hospedador = hosp.value.trim(); pagina = 0; cargar(); }, 250); });

  vista.replaceChildren(
    el("h1", {}, "Banco de fagos"),
    el("p", { class: "suave" }, "Solo los fagos aprobados participan en las predicciones, y el modelo solo conoce los del conjunto PhageHostLearn (accesión PHL-…). ", curador ? "Aprueba o descarta los que importaste; selecciona varios para hacerlo en lote." : "Tu rol solo consulta el banco."),
    el("section", { class: "tarjeta" },
      el("div", { class: "fila-campos" }, campo("Buscar", buscador), campo("Ciclo de vida", ciclo), campo("Curaduría", cur), campo("Hospedador", hosp)),
      curador ? el("div", { class: "acciones" },
        el("button", { type: "button", onclick: () => seleccion.size && curarLote("aprobar", [...seleccion]) }, "Aprobar seleccionados"),
        el("button", { type: "button", class: "peligro", onclick: () => seleccion.size && curarLote("descartar", [...seleccion]) }, "Descartar seleccionados"),
        el("button", { type: "button", class: "secundario", onclick: async () => {
          const ids = await idsPendientesDeLaBusqueda().catch((e) => { salida.replaceChildren(mensaje("error", e.message)); return []; });
          if (ids.length && confirm(`¿Aprobar los ${ids.length} fagos pendientes de esta búsqueda?`)) curarLote("aprobar", ids);
        } }, "Aprobar todos los pendientes de la búsqueda")) : null,
      salida, info, resultado),
  );
  cargar();
}

export async function vistaFago(id) {
  detenerSeguimiento();
  vista.replaceChildren(el("p", { class: "suave" }, "Cargando…"));
  try {
    const f = await api(`/api/v1/fagos/${id}`);
    const curador = puede("curar_banco");
    const salida = el("div", { "aria-live": "polite" });
    const llamar = (ruta) => async () => {
      try { await api(`/api/v1/fagos/${id}/${ruta}`, { method: "POST" }); vistaFago(id); }
      catch (e) { salida.replaceChildren(mensaje("error", e.message)); }
    };
    const nombre = el("input", { type: "text", id: "e-nombre", value: f.nombre, maxlength: "300" });
    const familia = el("input", { type: "text", id: "e-familia", value: f.familia || "", maxlength: "120" });
    const genero = el("input", { type: "text", id: "e-genero", value: f.genero || "", maxlength: "120" });
    const ciclo = el("select", { id: "e-ciclo" }, opciones(CICLOS, f.ciclo_vida));
    const hospedador = el("input", { type: "text", id: "e-hosp", value: f.hospedador_declarado || "", maxlength: "200" });
    const formulario = el("form", { novalidate: true, class: "sin-imprimir" },
      el("div", { class: "fila-campos" }, campo("Nombre", nombre), campo("Familia", familia), campo("Género", genero), campo("Ciclo de vida", ciclo), campo("Hospedador declarado", hospedador)),
      el("button", { type: "submit" }, "Guardar cambios"));
    formulario.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api(`/api/v1/fagos/${id}`, { method: "PATCH", json: { nombre: nombre.value, familia: familia.value || null, genero: genero.value || null, ciclo_vida: ciclo.value, hospedador_declarado: hospedador.value || null } });
        vistaFago(id);
      } catch (err) { salida.replaceChildren(mensaje("error", err.message)); }
    });
    const positivas = f.interacciones.filter((i) => i.resultado === "infecta").length;
    vista.replaceChildren(
      el("p", {}, el("a", { href: "#/banco" }, "← Banco de fagos")),
      el("div", { class: "cabecera-vista" }, el("h1", {}, f.nombre), insignia(f.estado_curaduria, tipoCuraduria[f.estado_curaduria] || "neutro")),
      curador ? el("div", { class: "acciones" },
        el("button", { type: "button", disabled: f.estado_curaduria === "aprobado", onclick: llamar("aprobar") }, "Aprobar"),
        el("button", { type: "button", class: "peligro", disabled: f.estado_curaduria === "descartado", onclick: llamar("descartar") }, "Descartar")) : null,
      salida,
      el("section", { class: "tarjeta" }, el("h2", {}, "Datos del fago"), datos([
        ["Accesión", el("span", { class: "mono" }, f.accesion)], ["Familia", vacio(f.familia)], ["Género", vacio(f.genero)], ["Ciclo de vida", f.ciclo_vida],
        ["Longitud", f.longitud_pb ? `${numero(f.longitud_pb)} pb` : "—"], ["Completitud", vacio(f.completitud)], ["Hospedador declarado", vacio(f.hospedador_declarado)],
        ["Curado", f.curado_en ? fecha(f.curado_en) : "—"],
      ])),
      curador ? el("section", { class: "tarjeta" }, el("h2", {}, "Corregir metadatos"), formulario) : null,
      el("section", { class: "tarjeta" }, el("h2", {}, `Interacciones conocidas (${numero(f.interacciones.length)}; ${numero(positivas)} positivas)`),
        f.interacciones.length
          ? tabla([
              { titulo: "Cepa", celda: (i) => vacio(i.cepa) }, { titulo: "Hospedador", celda: (i) => el("em", {}, i.especie_hospedador) },
              { titulo: "Locus K", celda: (i) => vacio(i.locus_k_tipo) },
              { titulo: "Resultado", celda: (i) => insignia(i.resultado === "infecta" ? "infecta" : "no infecta", i.resultado === "infecta" ? "ok" : "neutro") },
              { titulo: "Fuente", celda: (i) => vacio(i.fuente) },
            ], f.interacciones.slice(0, 200))
          : el("p", { class: "vacio" }, "Este fago no tiene interacciones conocidas en el banco.")),
    );
  } catch (e) {
    vista.replaceChildren(el("p", {}, el("a", { href: "#/banco" }, "← Banco de fagos")), mensaje("error", e.message));
  }
}
