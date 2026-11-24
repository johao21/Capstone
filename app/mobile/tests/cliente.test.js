// Pruebas del cliente de la API: se reemplaza `fetch` por una función que devuelve respuestas armadas a mano.
import assert from "node:assert/strict";
import { test } from "node:test";

import { crearCliente, ErrorApi, normalizarServidor } from "../src/api/cliente.js";

/** Respuesta mínima compatible con lo que usa el cliente. */
function respuesta(estado, cuerpo = null, cabeceras = {}) {
  return {
    ok: estado >= 200 && estado < 300,
    status: estado,
    headers: { get: (nombre) => cabeceras[nombre] ?? null },
    json: async () => {
      if (cuerpo === null) throw new SyntaxError("sin cuerpo");
      return cuerpo;
    },
  };
}

/** Cliente con un fetch falso; `llamadas` guarda cada petición para revisarla. */
function armar({ token = "tok-1", responder }) {
  const llamadas = [];
  const eventos = { guardados: [], vencida: 0 };
  const cliente = crearCliente({
    servidor: () => "http://192.168.1.20:8000",
    token: () => token,
    guardarToken: (t) => eventos.guardados.push(t),
    sesionVencida: () => (eventos.vencida += 1),
    fetchFn: async (url, opciones) => {
      llamadas.push({ url, ...opciones });
      return responder(url, opciones);
    },
  });
  return { cliente, llamadas, eventos };
}

test("normalizarServidor completa el esquema, quita la barra final y rechaza lo inválido", () => {
  assert.equal(normalizarServidor("192.168.1.20:8000"), "http://192.168.1.20:8000");
  assert.equal(normalizarServidor("  http://10.0.2.2:8000/  "), "http://10.0.2.2:8000");
  assert.equal(normalizarServidor("https://sirfa.ejemplo.cl/api/v1"), "https://sirfa.ejemplo.cl");
  assert.equal(normalizarServidor(""), null);
  assert.equal(normalizarServidor("   "), null);
  assert.equal(normalizarServidor("ftp://servidor"), null);
  assert.equal(normalizarServidor("http://"), null);
});

test("iniciarSesion envía correo y contraseña y no manda Authorization con el token viejo vacío", async () => {
  const { cliente, llamadas } = armar({ token: null, responder: () => respuesta(200, { access_token: "nuevo", usuario: { rol: "CLI" } }) });
  const salida = await cliente.iniciarSesion("  clinico@centro.cl ", "secreta");
  assert.equal(salida.access_token, "nuevo");
  assert.equal(llamadas[0].url, "http://192.168.1.20:8000/api/v1/auth/login");
  assert.equal(llamadas[0].method, "POST");
  assert.deepEqual(JSON.parse(llamadas[0].body), { correo: "clinico@centro.cl", password: "secreta" });
  assert.equal(llamadas[0].headers.Authorization, undefined);
});

test("las peticiones con sesión llevan el token Bearer", async () => {
  const { cliente, llamadas } = armar({ responder: () => respuesta(200, { id: "1" }) });
  await cliente.yo();
  assert.equal(llamadas[0].headers.Authorization, "Bearer tok-1");
});

test("un 401 en el login es «credenciales incorrectas» y NO cierra la sesión", async () => {
  const { cliente, eventos } = armar({ token: "viejo", responder: () => respuesta(401, { detail: "Correo o contraseña incorrectos" }) });
  await assert.rejects(cliente.iniciarSesion("a@b.cl", "x"), (e) => e instanceof ErrorApi && e.estado === 401 && e.message === "Correo o contraseña incorrectos");
  assert.equal(eventos.vencida, 0);
});

test("un 401 en otra ruta avisa que la sesión venció", async () => {
  const { cliente, eventos } = armar({ responder: () => respuesta(401, { detail: "Token inválido" }) });
  await assert.rejects(cliente.listarSolicitudes(), (e) => e.estado === 401 && /venció/.test(e.message));
  assert.equal(eventos.vencida, 1);
});

test("guarda el token renovado que manda el servidor", async () => {
  const { cliente, eventos } = armar({ responder: () => respuesta(200, { items: [], total: 0 }, { "X-Token-Renovado": "tok-2" }) });
  await cliente.listarSolicitudes();
  assert.deepEqual(eventos.guardados, ["tok-2"]);
});

test("listarSolicitudes arma la consulta sin parámetros vacíos", async () => {
  const { cliente, llamadas } = armar({ responder: () => respuesta(200, { items: [], total: 0 }) });
  await cliente.listarSolicitudes({ limite: 50, desplazamiento: 100 });
  assert.equal(llamadas[0].url, "http://192.168.1.20:8000/api/v1/solicitudes?limite=50&desplazamiento=100");
});

test("el detalle escapa el identificador para que no cambie la ruta", async () => {
  const { cliente, llamadas } = armar({ responder: () => respuesta(200, {}) });
  await cliente.detalleSolicitud("../auth/yo");
  assert.equal(llamadas[0].url, "http://192.168.1.20:8000/api/v1/solicitudes/..%2Fauth%2Fyo");
});

test("recomendacionEmitida devuelve null ante un 404 y propaga los demás errores", async () => {
  const sin = armar({ responder: () => respuesta(404, { detail: "La solicitud todavía no tiene una recomendación emitida" }) });
  assert.equal(await sin.cliente.recomendacionEmitida("abc"), null);

  const prohibida = armar({ responder: () => respuesta(403, { detail: "Tu rol no permite esta operación" }) });
  await assert.rejects(prohibida.cliente.recomendacionEmitida("abc"), (e) => e.estado === 403);

  const caida = armar({ responder: () => respuesta(500) });
  await assert.rejects(caida.cliente.recomendacionEmitida("abc"), (e) => e.estado === 500 && /500/.test(e.message));
});

test("alertas pide solo las no leídas cuando se indica", async () => {
  const { cliente, llamadas } = armar({ responder: () => respuesta(200, { no_leidas: 0, items: [] }) });
  await cliente.alertas({ soloNoLeidas: true, limite: 20 });
  await cliente.alertas();
  assert.equal(llamadas[0].url, "http://192.168.1.20:8000/api/v1/alertas?solo_no_leidas=true&limite=20");
  assert.equal(llamadas[1].url, "http://192.168.1.20:8000/api/v1/alertas?limite=50");
});

test("marcarLeida y leerTodas usan POST y toleran el 204 sin cuerpo", async () => {
  const { cliente, llamadas } = armar({ responder: () => respuesta(204) });
  assert.equal(await cliente.marcarLeida("a1"), null);
  assert.equal(await cliente.leerTodas(), null);
  assert.deepEqual(llamadas.map((l) => [l.method, l.url.split("/api/v1")[1]]), [["POST", "/alertas/a1/leida"], ["POST", "/alertas/leer-todas"]]);
});

test("los errores de validación (422) se resumen en un texto", async () => {
  const { cliente } = armar({ responder: () => respuesta(422, { detail: [{ msg: "campo requerido" }, { msg: "formato inválido" }] }) });
  await assert.rejects(cliente.yo(), (e) => e.message === "campo requerido; formato inválido");
});

test("un servidor caído se informa como sin conexión, con la dirección", async () => {
  const cliente = crearCliente({
    servidor: () => "http://10.0.2.2:8000",
    token: () => null,
    fetchFn: async () => {
      throw new TypeError("Network request failed");
    },
  });
  await assert.rejects(cliente.yo(), (e) => e.sinConexion === true && e.message.includes("http://10.0.2.2:8000"));
});

test("una petición que no responde se corta y se informa como falta de respuesta", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const cliente = crearCliente({
    servidor: () => "http://10.0.2.2:8000",
    token: () => null,
    fetchFn: (url, { signal }) =>
      new Promise((_, rechazar) => signal.addEventListener("abort", () => rechazar(Object.assign(new Error("abortado"), { name: "AbortError" })))),
  });
  const espera = assert.rejects(cliente.yo(), (e) => e.sinConexion === true && /no respondió a tiempo/.test(e.message));
  await new Promise((r) => setImmediate(r));
  t.mock.timers.tick(15000);
  await espera;
});
