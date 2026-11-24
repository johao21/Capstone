"use strict";
/* Solicitudes: lista y alta, bandeja de validación, detalle con avance, predicción, validación y recomendación emitida. */
import {
  ADVERTENCIA, MECANISMOS, TIPOS_MUESTRA, api, campo, datos, detenerSeguimiento, el, fecha, insignia, insigniaEstado, mensaje, numero,
  opciones, parametros, porcentaje, puede, seguir, sesion, tabla, vacio, vista,
} from "./base.js";

const TAMANO_MAXIMO = 60 * 1024 * 1024; // igual que el tope del servidor (routers/solicitudes.py)
const SONDEO_MS = 3000;

// ¿El pipeline terminó y el modelo está generando el ranking? (la solicitud sigue "en_analisis" hasta que la predicción queda lista)
const analisisTerminado = (s) => s.estado === "en_analisis" && Boolean(s.locus_k_tipo || s.especie_detectada);
// Mientras la solicitud esté en manos del sistema, la pantalla se refresca sola.
const enCurso = (s) => s.estado === "registrada" || s.estado === "en_analisis";
const insigniaSolicitud = (s) => (analisisTerminado(s) ? insignia("Generando predicción", "curso") : insigniaEstado(s.estado));

/* ---------- lista y alta ---------- */
export async function vistaSolicitudes({ bandeja = false } = {}) {
  vista.replaceChildren(el("p", { class: "suave" }, "Cargando…"));
  const filtros = { estado: bandeja ? "prediccion_lista" : "", desde: "", hasta: "", centro_id: "" };
  let centros = [];
  if (puede("gestionar_usuarios")) centros = await api("/api/v1/centros").catch(() => []);
  const zona = el("div");

  async function cargar() {
    try {
      const [resumen, lista] = await Promise.all([api("/api/v1/resumen"), api(`/api/v1/solicitudes${parametros({ ...filtros, limite: 100 })}`)]);
      zona.replaceChildren(cifras(resumen), tarjetaLista(lista, bandeja));
      if (lista.items.some(enCurso)) seguir(() => (location.hash === (bandeja ? "#/bandeja" : "#/solicitudes")) && cargar(), SONDEO_MS);
    } catch (e) {
      zona.replaceChildren(mensaje("error", e.message));
    }
  }

  const selectEstado = el("select", { id: "f-estado" }, el("option", { value: "" }, "Todos"), opciones(Object.entries({ registrada: "Registrada", en_analisis: "En análisis", prediccion_lista: "Predicción lista", en_validacion: "En validación", emitida: "Emitida", cerrada: "Cerrada", rechazada: "Rechazada", anulada: "Anulada", error: "Error" }), filtros.estado));
  const desde = el("input", { type: "date", id: "f-desde" });
  const hasta = el("input", { type: "date", id: "f-hasta" });
  const selectCentro = centros.length ? el("select", { id: "f-centro" }, el("option", { value: "" }, "Todos"), centros.map((c) => el("option", { value: c.id }, `${c.codigo} · ${c.nombre}`))) : null;
  const aplicar = () => { filtros.estado = selectEstado.value; filtros.desde = desde.value; filtros.hasta = hasta.value; filtros.centro_id = selectCentro ? selectCentro.value : ""; cargar(); };
  for (const c of [selectEstado, desde, hasta, selectCentro]) c?.addEventListener("change", aplicar);
  const filtrosUI = el("section", { class: "tarjeta" }, el("div", { class: "fila-campos" },
    campo("Estado", selectEstado), campo("Desde", desde), campo("Hasta", hasta), selectCentro ? campo("Centro", selectCentro) : null));

  vista.replaceChildren(
    el("h1", {}, bandeja ? "Bandeja de validación" : "Solicitudes"),
    el("p", { class: "suave" }, bandeja
      ? "Solicitudes con la predicción lista. Toma una para validarla: descartas candidatos con justificación y la apruebas o la rechazas."
      : puede("registrar_solicitud") ? "Sube el genoma ensamblado de un aislado de Klebsiella pneumoniae para analizarlo." : "Solicitudes que tu rol puede ver."),
    el("div", { class: puede("registrar_solicitud") ? "rejilla rejilla--2" : "" }, el("div", {}, filtrosUI, zona), puede("registrar_solicitud") ? formularioNueva() : null),
  );
  await cargar();
}

function cifras(resumen) {
  const total = Object.values(resumen.solicitudes_por_estado).reduce((a, b) => a + b, 0);
  const porEstado = resumen.solicitudes_por_estado;
  const datosCifras = [
    [numero(total), "solicitudes visibles"],
    [numero(porEstado.prediccion_lista || 0), "con predicción lista"],
    [numero((porEstado.emitida || 0) + (porEstado.cerrada || 0)), "con recomendación emitida"],
    [numero(resumen.banco.fagos_curados), "fagos aprobados en el banco"],
  ];
  return el("div", { class: "cifras" }, datosCifras.map(([valor, texto]) => el("div", { class: "cifra" }, el("span", { class: "cifra__valor" }, valor), el("span", { class: "cifra__texto" }, texto))));
}

function tarjetaLista(lista, bandeja) {
  const contenido = lista.items.length
    ? tabla([
        { titulo: "Código", celda: (s) => s.codigo_interno },
        { titulo: "Estado", celda: insigniaSolicitud },
        { titulo: "Especie", celda: (s) => el("em", {}, vacio(s.especie_detectada)) },
        { titulo: "Locus K", celda: (s) => vacio(s.locus_k_tipo) },
        { titulo: "Creada", sinCortar: true, celda: (s) => fecha(s.creada_en) },
      ], lista.items, { alHacerClic: (s) => { location.hash = `#/solicitud/${s.id}`; } })
    : el("p", { class: "vacio" }, bandeja ? "No hay solicitudes esperando validación." : "No hay solicitudes con estos filtros.");
  return el("section", { class: "tarjeta" }, el("h2", {}, `${bandeja ? "Por validar" : "Solicitudes"} (${numero(lista.total)})`), contenido);
}

// Formulario de alta (solo el técnico). En el navegador solo se valida lo básico: la API repite y completa las validaciones.
function formularioNueva() {
  const salida = el("div", { "aria-live": "polite" });
  const boton = el("button", { type: "submit" }, "Registrar y analizar");
  const clinico = el("select", { id: "clinico", name: "clinico_id" }, el("option", { value: "" }, "Yo mismo"));
  api("/api/v1/usuarios/clinicos").then((lista) => lista.forEach((c) => clinico.append(el("option", { value: c.id }, c.nombre)))).catch(() => {});
  const form = el("form", { novalidate: true },
    campo("Genoma (FASTA)", el("input", { type: "file", id: "archivo", name: "archivo", accept: ".fasta,.fna,.fa,.fas,.gz", required: true }), ".fasta, .fna, .fa o .gz · hasta 60 MB · genoma ensamblado"),
    campo("Código del aislado", el("input", { type: "text", id: "codigo", name: "codigo_interno", maxlength: "80", required: true, autocomplete: "off" })),
    el("div", { class: "fila-campos" },
      campo("Tipo de muestra", el("select", { id: "muestra", name: "tipo_muestra" }, opciones(TIPOS_MUESTRA))),
      campo("Mecanismo de resistencia", el("select", { id: "mecanismo", name: "mecanismo_resistencia" }, opciones(MECANISMOS)))),
    campo("Clínico solicitante", clinico, "Recibirá la alerta cuando la recomendación se emita."),
    campo("Observaciones (opcional)", el("textarea", { id: "obs", name: "observaciones", maxlength: "500" })),
    boton, salida);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    salida.replaceChildren();
    const archivo = form.archivo.files[0];
    if (!archivo) return salida.replaceChildren(mensaje("error", "Elige el archivo FASTA del genoma."));
    if (archivo.size > TAMANO_MAXIMO) return salida.replaceChildren(mensaje("error", "El archivo supera los 60 MB."));
    if (!form.codigo_interno.value.trim()) return salida.replaceChildren(mensaje("error", "Escribe el código del aislado."));
    boton.disabled = true;
    boton.textContent = "Subiendo…";
    try {
      const datosForm = new FormData(form);
      if (!clinico.value) datosForm.delete("clinico_id");
      const creada = await api("/api/v1/solicitudes", { method: "POST", body: datosForm });
      location.hash = `#/solicitud/${creada.id}`;
    } catch (err) {
      salida.replaceChildren(mensaje("error", err.message));
      boton.disabled = false;
      boton.textContent = "Registrar y analizar";
    }
  });
  return el("section", { class: "tarjeta" }, el("h2", {}, "Nueva solicitud"), form);
}

/* ---------- detalle ---------- */
// Cinco etapas: registro, análisis, predicción, validación y recomendación. `clase`: hecho (verde), activo (azul), fallo (rojo) o ausente (punteado).
function pasos(d, tienePrediccion) {
  const t = ["1. Registro", "2. Análisis genómico", "3. Predicción", "4. Validación", "5. Recomendación"];
  const p = (i, estado, clase) => ({ titulo: t[i], estado, clase });
  const base = [p(0, "Genoma recibido", "hecho"), p(1, "Pendiente", "ausente"), p(2, "Pendiente", "ausente"), p(3, "Pendiente", "ausente"), p(4, "Pendiente", "ausente")];
  const tieneAnalisis = Boolean(d.analisis);
  switch (d.estado) {
    case "registrada": base[1] = p(1, "En cola", "activo"); break;
    case "en_analisis":
      if (!tieneAnalisis) base[1] = p(1, "En curso", "activo");
      else { base[1] = p(1, "Completo", "hecho"); base[2] = p(2, "Generando el ranking", "activo"); }
      break;
    case "prediccion_lista": base[1] = p(1, "Completo", "hecho"); base[2] = p(2, "Lista", "hecho"); base[3] = p(3, d.asignada_a ? `Asignada a ${d.asignada_a}` : "Por tomar", "activo"); break;
    case "en_validacion": base[1] = p(1, "Completo", "hecho"); base[2] = p(2, "Lista", "hecho"); base[3] = p(3, `En validación (${vacio(d.asignada_a)})`, "activo"); break;
    case "emitida": case "cerrada":
      base[1] = p(1, "Completo", "hecho"); base[2] = p(2, "Lista", "hecho"); base[3] = p(3, "Validada", "hecho"); base[4] = p(4, d.estado === "cerrada" ? "Cerrada" : "Emitida", "hecho"); break;
    case "rechazada":
      if (!tieneAnalisis) base[1] = p(1, "Rechazada", "fallo");
      else { base[1] = p(1, "Completo", "hecho"); base[2] = tienePrediccion ? p(2, "Lista", "hecho") : base[2]; base[3] = p(3, "Rechazada", "fallo"); }
      break;
    case "error":
      if (!tieneAnalisis) base[1] = p(1, "Error", "fallo");
      else { base[1] = p(1, "Completo", "hecho"); base[2] = p(2, "Error", "fallo"); }
      break;
    case "anulada": base[1] = p(1, "Anulada", "ausente"); break;
  }
  return base;
}

export async function vistaSolicitud(id) {
  vista.replaceChildren(el("p", { class: "suave" }, "Cargando…"));
  await pintar(id, true);
}

const intentar = (promesa) => promesa.catch(() => null);

async function pintar(id, primera) {
  try {
    const d = await api(`/api/v1/solicitudes/${id}`);
    const ver = (estados) => estados.includes(d.estado);
    const [evidencia, prediccion, emitida] = await Promise.all([
      intentar(api(`/api/v1/solicitudes/${id}/recomendacion`)),
      puede("ver_prediccion") && ver(["prediccion_lista", "en_validacion", "emitida", "cerrada"]) ? intentar(api(`/api/v1/solicitudes/${id}/prediccion?limite=40`)) : null,
      ver(["emitida", "cerrada"]) ? intentar(api(`/api/v1/solicitudes/${id}/recomendacion-emitida`)) : null,
    ]);
    if (location.hash !== `#/solicitud/${id}`) return; // el usuario ya navegó a otra pantalla
    const recargar = () => pintar(id, false);
    const miSolicitud = sesion.usuario.rol === "MIC";
    vista.replaceChildren(...[
      el("p", {}, el("a", { href: sesion.usuario.rol === "MIC" ? "#/bandeja" : "#/solicitudes" }, "← Volver")),
      el("div", { class: "cabecera-vista" }, el("h1", {}, d.aislado.codigo_interno), insigniaSolicitud({ ...d, locus_k_tipo: d.analisis?.locus_k_tipo, especie_detectada: d.analisis?.especie_detectada })),
      d.motivo_estado && !["en_analisis", "registrada"].includes(d.estado) ? mensaje(["error", "rechazada"].includes(d.estado) ? "error" : "info", d.motivo_estado) : null,
      el("ol", { class: "pasos pasos--5", "aria-label": "Avance de la solicitud" }, pasos(d, Boolean(prediccion)).map((p) =>
        el("li", { class: `paso paso--${p.clase}` }, el("span", { class: "paso__titulo" }, p.titulo), el("span", { class: "paso__estado" }, p.estado)))),
      enCurso(d) ? el("p", { class: "suave chico" }, d.etapa) : null,
      acciones(d, recargar, prediccion),
      d.estado === "en_validacion" && miSolicitud && d.asignada_a === sesion.usuario.nombre && prediccion ? panelValidacion(d, prediccion, "aprobar", recargar) : null,
      prediccion && !(d.estado === "en_validacion" && d.asignada_a === sesion.usuario.nombre) ? tarjetaPrediccion(prediccion) : null,
      emitida ? tarjetaEmitida(d, emitida, prediccion, recargar) : null,
      el("div", { class: "rejilla rejilla--2" }, tarjetaAislado(d), tarjetaGenoma(d)),
      d.analisis ? tarjetaAnalisis(d.analisis) : null,
      evidencia && evidencia.estado === "evidencia_disponible" ? tarjetaEvidencia(evidencia) : null,
      el("div", { class: "rejilla rejilla--2" }, tarjetaHistorial(d), tarjetaTrabajos(d)),
      el("p", { class: "suave chico" }, ADVERTENCIA),
    ].filter(Boolean));
    if (primera) vista.focus({ preventScroll: true });
    if (enCurso(d)) seguir(() => pintar(id, false), SONDEO_MS);
    else detenerSeguimiento();
  } catch (e) {
    if (location.hash === `#/solicitud/${id}`) vista.replaceChildren(el("p", {}, el("a", { href: "#/solicitudes" }, "← Volver")), mensaje("error", e.message));
  }
}

// Botones según el estado y el rol. La API vuelve a validar cada transición; aquí solo se decide qué botón mostrar.
function acciones(d, recargar, prediccion) {
  const salida = el("div", { "aria-live": "polite" });
  const botones = [];
  const llamar = (ruta, cuerpo) => async () => {
    try { await api(`/api/v1/solicitudes/${d.id}/${ruta}`, { method: "POST", ...(cuerpo ? { json: cuerpo } : {}) }); recargar(); }
    catch (e) { salida.replaceChildren(mensaje("error", e.message)); }
  };
  const abierta = ["registrada", "en_analisis", "error", "prediccion_lista", "en_validacion"].includes(d.estado);
  if (puede("anular_solicitud") && abierta) {
    botones.push(el("button", { type: "button", class: "peligro", onclick: async () => {
      const motivo = prompt("Motivo de la anulación (obligatorio):");
      if (motivo && motivo.trim()) llamar("anular", { motivo: motivo.trim() })();
    } }, "Anular solicitud"));
  }
  if (puede("reintentar_solicitud") && d.estado === "error") botones.push(el("button", { type: "button", onclick: llamar("reintentar") }, "Reintentar"));
  if (puede("validar_recomendacion") && d.estado === "prediccion_lista") botones.push(el("button", { type: "button", onclick: llamar("tomar") }, "Tomar para validar"));
  if (puede("validar_recomendacion") && d.estado === "en_validacion" && d.asignada_a === sesion.usuario.nombre) {
    botones.push(el("button", { type: "button", class: "secundario", onclick: llamar("liberar") }, "Devolver a la bandeja"));
  }
  if (puede("reasignar_solicitud") && ["prediccion_lista", "en_validacion"].includes(d.estado)) botones.push(controlReasignar(d, llamar));
  return botones.length ? el("div", {}, el("div", { class: "acciones" }, botones), salida) : el("div");
}

function controlReasignar(d, llamar) {
  const lista = el("select", { id: "reasignar", "aria-label": "Microbiólogo" });
  api("/api/v1/usuarios?rol=MIC&activo=true").then((r) => r.items.forEach((u) => lista.append(el("option", { value: u.id }, u.nombre)))).catch(() => {});
  return el("span", { class: "en-linea" }, lista, el("button", { type: "button", class: "secundario", onclick: () => lista.value && llamar("reasignar", { usuario_id: lista.value })() }, "Reasignar"));
}

/* ---------- predicción y validación ---------- */
function resumenExplicacion(e) {
  if (!e || e.metodo !== "shap") return null;
  const signo = (x) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2);
  return el("details", { class: "explicacion" }, el("summary", {}, "¿Por qué este puntaje?"),
    el("p", { class: "chico" }, `SHAP (log-odds, base ${e.valor_base}): fago (RBP) ${signo(e.bloques.rbp_fago)} · locus K del hospedador ${signo(e.bloques.locus_k_hospedador)}.${e.rbp ? ` RBP decisiva: ${e.rbp}.` : ""}`),
    el("ul", { class: "chico" }, e.caracteristicas.map((c) => el("li", {}, `${c.nombre}: ${signo(c.contribucion)}`))),
    el("p", { class: "suave chico" }, "Cada característica es una dimensión del embedding ESM-2: pesa en el modelo, pero no tiene una lectura biológica individual."));
}

function textoEvidencia(ev) {
  return ev ? `${ev.interacciones_positivas} de ${ev.cepas_probadas} cepas de locus parecido` : "—";
}

function avisosPrediccion(pred) {
  const m = pred.modelo.metricas || {};
  const cepa = m.validacion_por_cepa;
  const similares = (pred.detalle?.cepas_similares || []).map((c) => `${c.cepa} (${porcentaje(c.similitud)})`).join(", ");
  return [
    pred.baja_confianza ? mensaje("alerta", el("strong", {}, "Baja confianza. "), pred.motivo_baja_confianza) : null,
    el("p", { class: "suave chico" }, `Modelo ${pred.modelo.version} (${pred.modelo.algoritmo}) · generada ${fecha(pred.generada_en)} · ${numero(pred.total_fagos)} fagos aprobados en el ranking · aislado de locus ${vacio(pred.locus_k_tipo)}.`),
    similares ? el("p", { class: "suave chico" }, `Su locus K se parece a ${similares} del conjunto de entrenamiento (similitud máxima ${porcentaje(pred.detalle.similitud_maxima)}).`) : null,
    m.top5 !== undefined ? el("p", { class: "suave chico" }, `Validación (acierto en el top-5, entre los fagos ensayados): tipo K no visto ${porcentaje(m.top5)} frente a ${porcentaje(m.linea_base_frecuencia_del_fago?.top5)} de la línea base que ignora al hospedador`,
      cepa ? `; tipo K representado ${porcentaje(cepa.top5)} frente a ${porcentaje(cepa.linea_base_frecuencia_del_fago?.top5)}.` : ".",
      " Con un tipo K no visto el modelo no supera a esa línea base.") : null,
  ];
}

// Ranking solo de lectura (antes de tomar la solicitud, o para el administrador).
function tarjetaPrediccion(pred) {
  return el("section", { class: "tarjeta" }, el("h2", {}, "Predicción de compatibilidad"), avisosPrediccion(pred),
    tabla([
      { titulo: "#", numerica: true, celda: (f) => f.rango },
      { titulo: "Fago", celda: (f) => el("span", {}, f.nombre, el("br"), el("span", { class: "mono suave" }, f.accesion)) },
      { titulo: "Prob. estimada", numerica: true, celda: (f) => porcentaje(f.puntaje) },
      { titulo: "Evidencia conocida", celda: (f) => textoEvidencia(f.evidencia) },
      { titulo: "Explicación", celda: (f) => resumenExplicacion(f.explicacion) || "—" },
    ], pred.items.slice(0, 15)),
    el("p", { class: "suave chico" }, ADVERTENCIA));
}

// Panel del microbiólogo: elige cuántos candidatos emitir, descarta con justificación y aprueba o rechaza (RF-43).
// Con modo "corregir" emite una nueva versión de una recomendación ya emitida (RF-46).
function panelValidacion(d, pred, modo, recargar) {
  const marcados = new Map(); // fago_id -> campo con la justificación
  const top = el("input", { type: "number", id: `top-${modo}`, min: "1", max: "20", value: "5" });
  const obs = el("textarea", { id: `obs-${modo}`, maxlength: "1000" });
  const salida = el("div", { "aria-live": "polite" });
  const filas = pred.items.slice(0, 20).map((f) => {
    const just = el("input", { type: "text", placeholder: "Justificación (obligatoria)", maxlength: "500", class: "oculto", "aria-label": `Justificación para descartar ${f.nombre}` });
    const casilla = el("input", { type: "checkbox", "aria-label": `Descartar ${f.nombre}`, onchange: (e) => {
      just.classList.toggle("oculto", !e.target.checked);
      if (e.target.checked) { marcados.set(f.fago_id, just); just.focus(); } else marcados.delete(f.fago_id);
    } });
    return el("tr", {}, el("td", { class: "num" }, f.rango), el("td", {}, f.nombre, el("br"), el("span", { class: "mono suave" }, f.accesion)),
      el("td", { class: "num" }, porcentaje(f.puntaje)), el("td", {}, textoEvidencia(f.evidencia)), el("td", {}, resumenExplicacion(f.explicacion) || "—"),
      el("td", {}, casilla, just));
  });
  const enviar = async (ruta, cuerpo) => {
    try { await api(`/api/v1/solicitudes/${d.id}/${ruta}`, { method: "POST", json: cuerpo }); recargar(); }
    catch (e) { salida.replaceChildren(mensaje("error", e.message)); }
  };
  const armar = () => {
    const descartes = [];
    for (const [fagoId, just] of marcados) {
      if (just.value.trim().length < 5) { salida.replaceChildren(mensaje("error", "Cada candidato descartado necesita una justificación de al menos 5 caracteres.")); return null; }
      descartes.push({ fago_id: fagoId, justificacion: just.value.trim() });
    }
    return { top: Number(top.value) || 5, descartes, observacion: obs.value.trim() || null };
  };
  const botones = modo === "aprobar"
    ? [
        el("button", { type: "button", onclick: () => { const c = armar(); if (c) enviar("validacion/aprobar", c); } }, "Aprobar y emitir la recomendación"),
        el("button", { type: "button", class: "peligro", onclick: () => {
          const j = prompt("Justificación del rechazo (obligatoria):");
          if (j && j.trim().length >= 5) enviar("validacion/rechazar", { justificacion: j.trim() });
        } }, "Rechazar la solicitud"),
      ]
    : [el("button", { type: "button", onclick: () => {
        const c = armar();
        if (!c) return;
        if (!c.observacion || c.observacion.length < 5) return salida.replaceChildren(mensaje("error", "Indica en la observación el motivo de la corrección."));
        enviar("recomendacion-emitida/corregir", c);
      } }, "Emitir versión corregida")];
  return el("section", { class: "tarjeta" }, el("h2", {}, modo === "aprobar" ? "Validar la predicción" : "Corregir la recomendación"),
    ...avisosPrediccion(pred),
    el("div", { class: "tabla-envoltorio" }, el("table", {}, el("thead", {}, el("tr", {}, ["#", "Fago", "Prob. estimada", "Evidencia conocida", "Explicación", "Descartar"].map((t) => el("th", { scope: "col" }, t)))), el("tbody", {}, filas))),
    el("div", { class: "fila-campos" }, campo("Candidatos a emitir", top, "Se emiten los mejores que no descartes."),
      campo(modo === "aprobar" ? "Observación (opcional)" : "Motivo de la corrección", obs)),
    el("div", { class: "acciones" }, botones), salida);
}

/* ---------- recomendación emitida ---------- */
function tarjetaEmitida(d, e, pred, recargar) {
  const mic = sesion.usuario.rol === "MIC" && d.asignada_a === sesion.usuario.nombre;
  const editable = mic && d.estado === "emitida";
  const selects = new Map();
  const salida = el("div", { "aria-live": "polite" });
  const filas = e.candidatos.map((c) => {
    let ensayo = c.resultado_ensayo.replace("_", " ");
    if (editable && !c.descartado) {
      const s = el("select", { "aria-label": `Resultado del ensayo de ${c.nombre}` }, opciones([["no_ensayado", "No ensayado"], ["infecta", "Infecta"], ["no_infecta", "No infecta"]], c.resultado_ensayo));
      selects.set(c.fago_id, s);
      ensayo = s;
    }
    return el("tr", { class: c.descartado ? "tachada" : null }, el("td", { class: "num" }, c.rango), el("td", {}, c.nombre, el("br"), el("span", { class: "mono suave" }, c.accesion)),
      el("td", { class: "num" }, porcentaje(c.puntaje)), el("td", {}, c.descartado ? insignia("descartado", "neutro") : insignia("candidato", "ok"), c.justificacion ? el("div", { class: "chico suave" }, c.justificacion) : null),
      el("td", {}, ensayo));
  });
  const guardar = (cerrar) => async () => {
    const resultados = [...selects].map(([fago_id, s]) => ({ fago_id, resultado: s.value }));
    if (!resultados.length) return;
    if (cerrar && !confirm("¿Cerrar la solicitud? Ya no se podrán registrar más ensayos.")) return;
    try { await api(`/api/v1/solicitudes/${d.id}/ensayos`, { method: "POST", json: { resultados, cerrar } }); recargar(); }
    catch (err) { salida.replaceChildren(mensaje("error", err.message)); }
  };
  return el("section", { class: "tarjeta tarjeta--emitida", id: "recomendacion" },
    el("div", { class: "cabecera-vista" }, el("h2", {}, `Recomendación emitida · versión ${e.version}`), insignia(e.estado, e.estado === "vigente" ? "ok" : "neutro")),
    mensaje("alerta", el("strong", {}, "Hipótesis a ensayar. "), e.advertencia),
    e.baja_confianza ? mensaje("alerta", el("strong", {}, "Baja confianza: "), "el locus K del aislado casi no está representado en los datos de entrenamiento.") : null,
    el("p", { class: "suave chico" }, `Validada por ${e.validador} el ${fecha(e.emitida_en)} · modelo ${e.modelo_version} · locus ${vacio(e.locus_k_tipo)}`),
    e.observacion ? el("p", {}, e.observacion) : null,
    el("div", { class: "tabla-envoltorio" }, el("table", {}, el("thead", {}, el("tr", {}, ["#", "Fago", "Puntaje", "Decisión", "Ensayo de laboratorio"].map((t) => el("th", { scope: "col" }, t)))), el("tbody", {}, filas))),
    editable ? el("div", { class: "acciones" }, el("button", { type: "button", class: "secundario", onclick: guardar(false) }, "Guardar ensayos"), el("button", { type: "button", onclick: guardar(true) }, "Guardar y cerrar la solicitud")) : null,
    salida,
    e.versiones.length > 1 ? el("p", { class: "suave chico" }, "Versiones: ", e.versiones.map((v) => `v${v.version} (${v.estado}, ${fecha(v.emitida_en)})`).join(" · ")) : null,
    el("div", { class: "acciones sin-imprimir" }, el("button", { type: "button", class: "secundario", onclick: () => window.print() }, "Imprimir / guardar como PDF")),
    editable && pred ? el("details", { class: "sin-imprimir" }, el("summary", {}, "Corregir la recomendación (emite una versión nueva)"), panelValidacion(d, pred, "corregir", recargar)) : null);
}

/* ---------- tarjetas de datos ---------- */
function tarjetaAislado(d) {
  const a = d.aislado;
  return el("section", { class: "tarjeta" }, el("h2", {}, "Aislado"), datos([
    ["Código", a.codigo_interno], ["Fecha de aislamiento", a.fecha_aislamiento], ["Especie declarada", el("em", {}, a.especie_declarada)],
    ["Tipo de muestra", a.tipo_muestra], ["Mecanismo de resistencia", vacio(a.mecanismo_resistencia)], ["Observaciones", vacio(a.observaciones)],
    ["Registrada por", vacio(d.registrada_por)], ["Clínico solicitante", vacio(d.solicitante)],
  ]));
}

function tarjetaGenoma(d) {
  const g = d.genoma;
  const tipoQc = { aprobado: "ok", advertencia: "alerta", rechazado: "error" }[g.qc_resultado] || "neutro";
  return el("section", { class: "tarjeta" }, el("h2", {}, "Genoma y calidad"), datos([
    ["Archivo", g.nombre_original], ["Tamaño", `${(g.tamano_bytes / 1048576).toFixed(1)} MB`], ["SHA-256", el("span", { class: "mono" }, g.sha256)],
    ["Calidad", g.qc_resultado ? insignia(g.qc_resultado, tipoQc) : "Pendiente"], ["Longitud", g.qc_longitud ? `${numero(g.qc_longitud)} pb` : "—"],
    ["Contigs · N50", g.qc_contigs ? `${numero(g.qc_contigs)} · ${numero(g.qc_n50)} pb` : "—"],
    ["GC", g.qc_gc !== null && g.qc_gc !== undefined ? `${g.qc_gc} %` : "—"],
    ["Bases ambiguas", g.qc_prop_ambiguas !== null && g.qc_prop_ambiguas !== undefined ? `${(g.qc_prop_ambiguas * 100).toFixed(3)} %` : "—"],
  ]));
}

function tarjetaAnalisis(a) {
  const verificada = a.especie_verificada ? `Verificada con Mash (distancia ${Number(a.distancia_especie).toFixed(4)} a ${a.especie_referencia})` : "No verificada: solo es la especie declarada";
  const versiones = Object.entries(a.versiones_herramientas || {}).map(([k, v]) => (String(v).toLowerCase().startsWith(k.toLowerCase()) ? v : `${k} ${v}`)).join(" · ");
  return el("section", { class: "tarjeta" }, el("h2", {}, "Resultado del análisis genómico"), datos([
    ["Especie", el("span", {}, el("em", {}, vacio(a.especie_detectada)), " · ", verificada)],
    ["Locus K (Kaptive)", a.locus_k_tipo ? el("span", {}, el("strong", {}, a.locus_k_tipo), ` · confianza: ${vacio(a.locus_k_confianza)}`) : "—"],
    ["Genes predichos (Prodigal)", numero(a.n_genes)], ["Proteínas", numero(a.n_proteinas)], ["Herramientas", vacio(versiones)], ["Analizado", fecha(a.creado_en)],
  ]));
}

function tarjetaEvidencia(r) {
  return el("section", { class: "tarjeta" }, el("h2", {}, "Evidencia conocida por locus K"), mensaje("ok", r.mensaje),
    tabla([
      { titulo: "Fago", celda: (c) => el("span", {}, c.nombre, el("br"), el("span", { class: "mono suave" }, c.accesion)) },
      { titulo: "Positivas", numerica: true, celda: (c) => numero(c.interacciones_positivas) },
      { titulo: "Negativas", numerica: true, celda: (c) => numero(c.interacciones_negativas) },
      { titulo: "Tasa", numerica: true, celda: (c) => `${Math.round(c.tasa_positiva * 100)} %` },
    ], r.candidatos));
}

function tarjetaHistorial(d) {
  return el("section", { class: "tarjeta" }, el("h2", {}, "Historial de estados"), tabla([
    { titulo: "Cuándo", celda: (h) => fecha(h.creado_en) }, { titulo: "Estado", celda: (h) => insigniaEstado(h.estado_nuevo) }, { titulo: "Motivo", celda: (h) => vacio(h.motivo) },
  ], d.historial));
}

function tarjetaTrabajos(d) {
  const tipos = { pendiente: "curso", en_curso: "curso", ok: "ok", fallido: "error" };
  return el("section", { class: "tarjeta" }, el("h2", {}, "Trabajos del sistema"), tabla([
    { titulo: "Tipo", celda: (t) => t.tipo }, { titulo: "Estado", celda: (t) => insignia(t.estado, tipos[t.estado] || "neutro") },
    { titulo: "Intentos", numerica: true, celda: (t) => t.intentos }, { titulo: "Error", celda: (t) => vacio(t.error) },
  ], d.trabajos));
}
