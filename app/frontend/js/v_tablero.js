"use strict";
/* Tablero: cobertura del banco, brechas terapéuticas y tendencias. Solo datos agregados; los grupos pequeños llegan suprimidos del servidor. */
import { api, barras, campo, descargar, detenerSeguimiento, el, insignia, mensaje, numero, parametros, puede, sesion, tabla, vista } from "./base.js";

export async function vistaTablero() {
  detenerSeguimiento();
  const completo = puede("ver_tablero_completo");
  const filtros = { desde: "", hasta: "", centro_id: "", especie: "", locus_k: "" };
  const zona = el("div");
  let centros = [];
  if (completo) centros = await api("/api/v1/centros").catch(() => []);

  async function cargar() {
    try {
      const consultas = [api("/api/v1/tablero/cobertura")];
      if (completo) consultas.push(api(`/api/v1/tablero/brechas${parametros(filtros)}`), api(`/api/v1/tablero/tendencias${parametros(filtros)}`));
      const [cobertura, brechas, tendencias] = await Promise.all(consultas);
      zona.replaceChildren(
        el("section", { class: "tarjeta" }, el("h2", {}, "Cobertura del banco"),
          el("p", { class: "suave chico" }, `${numero(cobertura.fagos_aprobados)} fagos aprobados de ${numero(cobertura.fagos_total)} en el banco.`),
          el("div", { class: "rejilla rejilla--3" },
            bloque("Por familia", cobertura.por_familia.map((g) => ({ ...g }))), bloque("Por ciclo de vida", cobertura.por_ciclo_vida), bloque("Por hospedador", cobertura.por_hospedador))),
        ...(completo ? [tarjetaBrechas(brechas), tarjetaTendencias(tendencias)] : []),
      );
    } catch (e) {
      zona.replaceChildren(mensaje("error", e.message));
    }
  }

  const f = (id, tipo = "text") => el("input", { type: tipo, id, autocomplete: "off" });
  const desde = f("t-desde", "date"), hasta = f("t-hasta", "date"), especie = f("t-especie"), locus = f("t-locus");
  const centro = centros.length ? el("select", { id: "t-centro" }, el("option", { value: "" }, "Todos"), centros.map((c) => el("option", { value: c.id }, `${c.codigo} · ${c.nombre}`))) : null;
  const aplicar = () => { Object.assign(filtros, { desde: desde.value, hasta: hasta.value, centro_id: centro ? centro.value : "", especie: especie.value.trim(), locus_k: locus.value.trim() }); cargar(); };
  for (const c of [desde, hasta, centro, especie, locus]) c?.addEventListener("change", aplicar);

  vista.replaceChildren(
    el("h1", {}, "Tablero"),
    el("p", { class: "suave" }, completo
      ? "Datos agregados de las solicitudes. Los grupos con menos casos que el mínimo configurado se reúnen en «Otros» para que no se pueda reconocer una solicitud."
      : "Cobertura del banco de fagos aprobados."),
    completo ? el("section", { class: "tarjeta" }, el("div", { class: "fila-campos" }, campo("Desde", desde), campo("Hasta", hasta), centro ? campo("Centro", centro) : null, campo("Especie", especie), campo("Locus K", locus)),
      sesion.usuario.rol === "EPI" ? el("button", { type: "button", class: "secundario", onclick: () => descargar(`/api/v1/tablero/exportar.csv${parametros(filtros)}`, "tablero_sirfa.csv").catch((e) => alert(e.message)) }, "Exportar a CSV") : null) : null,
    zona,
  );
  await cargar();
}

function bloque(titulo, grupos) {
  return el("div", {}, el("h3", {}, titulo), barras(grupos));
}

function tarjetaBrechas(b) {
  return el("section", { class: "tarjeta" }, el("h2", {}, "Brechas terapéuticas"),
    el("p", { class: "suave chico" }, `Tipos de locus K presentes en las solicitudes. Una brecha es un tipo sin fagos con compatibilidad conocida ni candidatos sobre el umbral de predicción (${b.umbral_candidato}). Mínimo por grupo: ${b.minimo_grupo} casos.`),
    b.grupos.length
      ? tabla([
          { titulo: "Locus K", celda: (g) => g.locus_k }, { titulo: "Solicitudes", numerica: true, celda: (g) => numero(g.solicitudes) },
          { titulo: "Fagos con evidencia", numerica: true, celda: (g) => numero(g.fagos_con_evidencia) },
          { titulo: "Candidatos del modelo", numerica: true, celda: (g) => numero(g.fagos_candidatos) },
          { titulo: "Estado", celda: (g) => (g.brecha ? insignia("brecha", "error") : insignia("cubierto", "ok")) },
        ], b.grupos)
      : el("p", { class: "vacio chico" }, "No hay tipos de locus K con casos suficientes para mostrar."),
    b.casos_suprimidos ? el("p", { class: "suave chico" }, `${numero(b.casos_suprimidos)} casos de grupos pequeños no se muestran.`) : null);
}

function tarjetaTendencias(t) {
  return el("section", { class: "tarjeta" }, el("h2", {}, "Tendencias"),
    el("p", { class: "suave chico" }, t.total_solicitudes === null ? `Hay menos de ${t.minimo_grupo} solicitudes: no se muestran datos para proteger su anonimato.` : `${numero(t.total_solicitudes)} solicitudes (sin las anuladas).`),
    el("div", { class: "rejilla rejilla--2" }, bloque("Solicitudes por mes", t.por_mes), bloque("Tipos de locus K", t.por_locus_k), bloque("Mecanismo de resistencia", t.por_mecanismo), bloque("Por centro", t.por_centro)));
}
