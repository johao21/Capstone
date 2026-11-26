// Lo que dibuja la interfaz (recorrido, íconos, barra de puntaje) sale de funciones puras; aquí se prueban.
// Cómo se ve en pantalla no se prueba de forma automática: se revisó a mano.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { ESTADOS, ETAPAS, FILTROS, ICONOS_ENSAYO, ICONOS_ESTADO, ICONOS_PASO, ENSAYOS, PASOS, fraccionPuntaje, iconoEnsayo, iconoEstado, iniciales, progreso } from "../src/logica/estados.js";
import { tonos } from "../src/tema.js";

const RUTA_ICONOS = new URL("../node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/glyphmaps/MaterialCommunityIcons.json", import.meta.url);

test("cada estado del servidor tiene su ícono y el estado desconocido, uno genérico", () => {
  for (const e of Object.keys(ESTADOS)) assert.ok(ICONOS_ESTADO[e], `falta el ícono de ${e}`);
  assert.equal(iconoEstado("emitida"), "check-circle");
  assert.equal(iconoEstado("algo_nuevo"), "help-circle-outline");
});

test("los tonos que usan los estados, los ensayos y los filtros existen en el tema", () => {
  const usados = [...Object.values(ESTADOS).map((e) => e[1]), ...Object.values(ENSAYOS).map((e) => e[1]), ...FILTROS.map((f) => f.tono)];
  for (const t of usados) assert.ok(tonos[t], `falta el tono ${t}`);
});

test("todos los íconos que se usan existen en MaterialCommunityIcons", { skip: !existsSync(RUTA_ICONOS) }, () => {
  const glifos = JSON.parse(readFileSync(RUTA_ICONOS, "utf8"));
  const nombres = [...Object.values(ICONOS_ESTADO), ...Object.values(ICONOS_PASO), ...Object.values(ICONOS_ENSAYO), ...FILTROS.map((f) => f.icono)];
  for (const n of nombres) assert.ok(n in glifos, `no existe el ícono ${n}`);
});

test("progreso: lo hecho, la etapa actual y lo que falta, en el orden del proceso", () => {
  const p = progreso("prediccion_lista");
  assert.deepEqual(p.pasos.map((x) => x.situacion), ["hecho", "hecho", "actual", "pendiente", "pendiente"]);
  assert.equal(p.actual, 2);
  assert.equal(p.total, 5);
  assert.equal(p.detenido, false);
  assert.equal(p.resumen, "Etapa 3 de 5: Predicción lista");
  assert.deepEqual(p.pasos.map((x) => x.clave), PASOS);
  // Cada nombre debe caber en una palabra bajo su círculo.
  for (const x of p.pasos) assert.ok(x.texto === ETAPAS[x.clave] && !x.texto.includes(" "), x.clave);
});

test("progreso: emitida y cerrada son el proceso completo; registrada es el primer paso", () => {
  assert.ok(progreso("emitida").pasos.every((x) => x.situacion === "hecho"));
  assert.equal(progreso("emitida").resumen, "Las 5 etapas están completas");
  assert.ok(progreso("cerrada").pasos.every((x) => x.situacion === "hecho"));
  assert.equal(progreso("cerrada").resumen, "Las 5 etapas están completas · solicitud cerrada");
  assert.deepEqual(progreso("registrada").pasos.map((x) => x.situacion), ["actual", "pendiente", "pendiente", "pendiente", "pendiente"]);
});

test("progreso: lo que se detuvo no tiene recorrido que dibujar", () => {
  for (const e of ["rechazada", "anulada", "error"]) {
    const p = progreso(e);
    assert.equal(p.pasos.length, 0, e);
    assert.equal(p.detenido, true, e);
    assert.equal(p.resumen, null, e);
  }
  assert.equal(progreso("algo_nuevo").detenido, false);
  assert.equal(progreso(undefined).pasos.length, 0);
});

test("ícono del ensayo de laboratorio", () => {
  assert.equal(iconoEnsayo("infecta"), "check-circle");
  assert.equal(iconoEnsayo("no_infecta"), "close-circle");
  assert.equal(iconoEnsayo("raro"), ICONOS_ENSAYO.no_ensayado);
});

test("fraccionPuntaje recorta a 0–1 y trata lo que no es número como 0", () => {
  assert.equal(fraccionPuntaje(0.87), 0.87);
  assert.equal(fraccionPuntaje(1.4), 1);
  assert.equal(fraccionPuntaje(-0.2), 0);
  assert.equal(fraccionPuntaje(null), 0);
  assert.equal(fraccionPuntaje("0.5"), 0);
  assert.equal(fraccionPuntaje(NaN), 0);
});

test("iniciales del nombre", () => {
  assert.equal(iniciales("Ana Pérez Soto"), "AP");
  assert.equal(iniciales("  johao  "), "J");
  assert.equal(iniciales(""), "?");
  assert.equal(iniciales(null), "?");
});
