import assert from "node:assert/strict";
import { test } from "node:test";

import {
  capacidades,
  contarPorFiltro,
  ESTADOS,
  filtrarSolicitudes,
  FILTROS,
  infoEnsayo,
  infoEstado,
  mensajeSinRecomendacion,
  nombreRol,
} from "../src/logica/estados.js";

const solicitudes = ["emitida", "cerrada", "error", "en_validacion", "rechazada", "registrada", "anulada"].map((estado, i) => ({ id: String(i), estado }));

test("cada estado del servidor tiene texto y tono", () => {
  // Los nueve estados de backend/app/models.py (ESTADOS_SOLICITUD).
  for (const e of ["registrada", "en_analisis", "prediccion_lista", "en_validacion", "emitida", "cerrada", "rechazada", "anulada", "error"]) {
    assert.ok(ESTADOS[e], `falta el estado ${e}`);
  }
  assert.deepEqual(infoEstado("emitida"), { texto: "Emitida", tono: "ok" });
  assert.deepEqual(infoEstado("error"), { texto: "Error", tono: "error" });
});

test("un estado desconocido se muestra tal cual, en neutro", () => {
  assert.deepEqual(infoEstado("algo_nuevo"), { texto: "algo_nuevo", tono: "neutro" });
  assert.deepEqual(infoEstado(null), { texto: "—", tono: "neutro" });
});

test("resultado de ensayo: los tres valores del servidor y uno desconocido", () => {
  assert.equal(infoEnsayo("infecta").tono, "ok");
  assert.equal(infoEnsayo("no_infecta").tono, "error");
  assert.equal(infoEnsayo("no_ensayado").texto, "Sin ensayar");
  assert.equal(infoEnsayo("raro").texto, "Sin ensayar");
});

test("los filtros reparten todos los estados sin repetir ninguno", () => {
  const grupos = FILTROS.filter((f) => f.estados).flatMap((f) => f.estados);
  assert.equal(new Set(grupos).size, grupos.length);
  assert.deepEqual([...grupos].sort(), Object.keys(ESTADOS).sort());
});

test("filtrarSolicitudes y contarPorFiltro", () => {
  assert.equal(filtrarSolicitudes(solicitudes, "todas").length, 7);
  assert.deepEqual(filtrarSolicitudes(solicitudes, "emitidas").map((s) => s.estado), ["emitida", "cerrada"]);
  assert.equal(filtrarSolicitudes(solicitudes, "no_existe").length, 7);
  assert.deepEqual(contarPorFiltro(solicitudes), { todas: 7, curso: 2, emitidas: 2, sin_resultado: 3 });
});

test("capacidades salen de los permisos que entrega la API", () => {
  assert.deepEqual(capacidades({ permisos: ["ver_solicitudes", "recibir_alertas"] }), { verSolicitudes: true, recibirAlertas: true });
  assert.deepEqual(capacidades({ permisos: ["ver_solicitudes"] }), { verSolicitudes: true, recibirAlertas: false }); // administrador
  assert.deepEqual(capacidades({ permisos: ["ver_tablero"] }), { verSolicitudes: false, recibirAlertas: false }); // epidemiólogo
  assert.deepEqual(capacidades(null), { verSolicitudes: false, recibirAlertas: false });
});

test("mensajeSinRecomendacion no promete una alerta cuando la solicitud ya terminó sin recomendación", () => {
  for (const estado of ["rechazada", "anulada", "error"]) {
    assert.doesNotMatch(mensajeSinRecomendacion(estado).texto, /recibirás una alerta/, estado);
  }
  assert.match(mensajeSinRecomendacion("en_validacion").texto, /recibirás una alerta/);
  assert.match(mensajeSinRecomendacion("error").texto, /reintentar/);
});

test("nombreRol", () => {
  assert.equal(nombreRol("CLI"), "Clínico solicitante");
  assert.equal(nombreRol("XXX"), "XXX");
});
