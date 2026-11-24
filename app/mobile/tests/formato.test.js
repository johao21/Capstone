import assert from "node:assert/strict";
import { test } from "node:test";

import { dato, fechaCorta, fechaHora, haceCuanto, parsearFecha, plural, puntaje } from "../src/logica/formato.js";

test("una fecha sin zona horaria se lee como UTC, igual que en el servidor", () => {
  assert.equal(parsearFecha("2026-11-17T15:46:42").toISOString(), "2026-11-17T15:46:42.000Z");
  assert.equal(parsearFecha("2026-11-17T15:46:42.830000Z").toISOString(), "2026-11-17T15:46:42.830Z");
  assert.equal(parsearFecha("2026-11-17T12:46:42-03:00").toISOString(), "2026-11-17T15:46:42.000Z");
});

test("una fecha sin hora es la fecha local, no un día antes por el huso horario", () => {
  const f = parsearFecha("2026-10-30");
  assert.deepEqual([f.getFullYear(), f.getMonth(), f.getDate()], [2026, 9, 30]);
  assert.equal(fechaCorta("2026-10-30"), "30 oct 2026");
});

test("valores vacíos o inválidos no rompen", () => {
  for (const v of [null, undefined, "", "no es fecha"]) {
    assert.equal(parsearFecha(v), null);
    assert.equal(fechaCorta(v), "—");
    assert.equal(fechaHora(v), "—");
    assert.equal(haceCuanto(v), "—");
  }
});

test("fechaHora usa dos dígitos en la hora", () => {
  const f = new Date(2026, 10, 5, 9, 4); // hora local: 5 nov 2026, 09:04
  assert.equal(fechaHora(f), "5 nov 2026, 09:04");
});

test("haceCuanto: ahora, minutos, horas, ayer, días y fecha", () => {
  const ahora = new Date("2026-11-18T12:00:00Z");
  const antes = (ms) => new Date(ahora.getTime() - ms).toISOString();
  const min = 60_000;
  assert.equal(haceCuanto(antes(10_000), ahora), "ahora");
  assert.equal(haceCuanto(antes(5 * min), ahora), "hace 5 min");
  assert.equal(haceCuanto(antes(3 * 60 * min), ahora), "hace 3 h");
  assert.equal(haceCuanto(antes(30 * 60 * min), ahora), "ayer");
  assert.equal(haceCuanto(antes(5 * 24 * 60 * min), ahora), "hace 5 días");
  assert.match(haceCuanto(antes(30 * 24 * 60 * min), ahora), /^\d{1,2} \w{3} 2026$/);
});

test("puntaje usa coma y dos decimales", () => {
  assert.equal(puntaje(0.8734), "0,87");
  assert.equal(puntaje(1), "1,00");
  assert.equal(puntaje(null), "—");
  assert.equal(puntaje(NaN), "—");
});

test("dato y plural", () => {
  assert.equal(dato(null), "—");
  assert.equal(dato(""), "—");
  assert.equal(dato(0), "0");
  assert.equal(dato(undefined, "sin dato"), "sin dato");
  assert.equal(plural(1, "solicitud", "solicitudes"), "1 solicitud");
  assert.equal(plural(0, "solicitud", "solicitudes"), "0 solicitudes");
});
