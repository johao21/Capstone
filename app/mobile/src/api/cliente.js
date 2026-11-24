// Cliente de la API de SIRFA (REST + JWT). No importa nada de React Native: recibe de afuera cómo guardar el token
// y qué `fetch` usar, y por eso se puede probar con node --test.

const TIEMPO_MAXIMO_MS = 15000;

export class ErrorApi extends Error {
  /**
   * @param {string} mensaje texto para mostrar al usuario
   * @param {{estado?: number, sinConexion?: boolean}} [extra] `estado`: código HTTP; `sinConexion`: no hubo respuesta
   */
  constructor(mensaje, { estado = null, sinConexion = false } = {}) {
    super(mensaje);
    this.name = "ErrorApi";
    this.estado = estado;
    this.sinConexion = sinConexion;
  }
}

/**
 * Deja la dirección del servidor en la forma «http(s)://host[:puerto]» sin barra final.
 * Devuelve null si no es una dirección válida. Sin esquema se asume http (se usa en redes locales).
 */
export function normalizarServidor(texto) {
  let valor = String(texto ?? "").trim();
  if (!valor) return null;
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(valor)) valor = `http://${valor}`;
  let url;
  try {
    url = new URL(valor);
  } catch {
    return null;
  }
  if (!["http:", "https:"].includes(url.protocol) || !url.hostname) return null;
  return `${url.protocol}//${url.host}`;
}

// La API responde {"detail": "texto"} o, en errores de validación, {"detail": [{"msg": ...}]}.
async function mensajeDeError(respuesta) {
  const base = `Error ${respuesta.status} del servidor`;
  try {
    const cuerpo = await respuesta.json();
    if (typeof cuerpo.detail === "string") return cuerpo.detail;
    if (Array.isArray(cuerpo.detail)) return cuerpo.detail.map((d) => d.msg).filter(Boolean).join("; ") || base;
  } catch {
    /* la respuesta no era JSON */
  }
  return base;
}

/**
 * @param {object} opciones
 * @param {() => string} opciones.servidor    dirección actual del servidor
 * @param {() => (string|null)} opciones.token  token de la sesión, o null
 * @param {(token: string) => void} [opciones.guardarToken]  se llama cuando el servidor renueva el token (cabecera X-Token-Renovado)
 * @param {() => void} [opciones.sesionVencida] se llama cuando el servidor responde 401 a una petición con sesión
 * @param {typeof fetch} [opciones.fetchFn]
 */
export function crearCliente({ servidor, token, guardarToken = () => {}, sesionVencida = () => {}, fetchFn = globalThis.fetch }) {
  async function pedir(ruta, { metodo = "GET", json, consulta, esLogin = false } = {}) {
    const base = servidor();
    const parametros = Object.entries(consulta ?? {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
    const direccion = `${base}${ruta}${parametros.length ? `?${new URLSearchParams(parametros.map(([k, v]) => [k, String(v)]))}` : ""}`;
    const cabeceras = { Accept: "application/json" };
    const actual = token();
    if (actual) cabeceras.Authorization = `Bearer ${actual}`;
    if (json !== undefined) cabeceras["Content-Type"] = "application/json";

    const control = new AbortController();
    const reloj = setTimeout(() => control.abort(), TIEMPO_MAXIMO_MS);
    let respuesta;
    try {
      respuesta = await fetchFn(direccion, { method: metodo, headers: cabeceras, body: json !== undefined ? JSON.stringify(json) : undefined, signal: control.signal });
    } catch (error) {
      const agotado = error?.name === "AbortError";
      throw new ErrorApi(
        agotado
          ? `El servidor ${base} no respondió a tiempo.`
          : `No hay conexión con ${base}. Revisa la dirección del servidor y que el teléfono esté en la misma red que el computador.`,
        { sinConexion: true },
      );
    } finally {
      clearTimeout(reloj);
    }

    const renovado = respuesta.headers?.get?.("X-Token-Renovado");
    if (renovado) guardarToken(renovado);

    if (!respuesta.ok) {
      const mensaje = await mensajeDeError(respuesta);
      // Un 401 en el login es «credenciales incorrectas»; en cualquier otra ruta, la sesión venció o fue revocada.
      if (respuesta.status === 401 && !esLogin && actual) {
        sesionVencida();
        throw new ErrorApi("Tu sesión venció. Vuelve a ingresar.", { estado: 401 });
      }
      throw new ErrorApi(mensaje, { estado: respuesta.status });
    }
    return respuesta.status === 204 ? null : respuesta.json();
  }

  return {
    // --- acceso (RF-61)
    iniciarSesion: (correo, password) => pedir("/api/v1/auth/login", { metodo: "POST", json: { correo: correo.trim(), password }, esLogin: true }),
    yo: () => pedir("/api/v1/auth/yo"),
    cerrarSesion: () => pedir("/api/v1/auth/logout", { metodo: "POST" }),

    // --- solicitudes (RF-62, RF-63)
    listarSolicitudes: ({ limite = 100, desplazamiento = 0, estado } = {}) =>
      pedir("/api/v1/solicitudes", { consulta: { limite, desplazamiento, estado } }),
    detalleSolicitud: (id) => pedir(`/api/v1/solicitudes/${encodeURIComponent(id)}`),
    /** Devuelve null si la solicitud todavía no tiene recomendación emitida (la API responde 404). */
    async recomendacionEmitida(id) {
      try {
        return await pedir(`/api/v1/solicitudes/${encodeURIComponent(id)}/recomendacion-emitida`);
      } catch (error) {
        if (error instanceof ErrorApi && error.estado === 404) return null;
        throw error;
      }
    },

    // --- alertas (RF-65)
    alertas: ({ soloNoLeidas = false, limite = 50 } = {}) => pedir("/api/v1/alertas", { consulta: { solo_no_leidas: soloNoLeidas || undefined, limite } }),
    marcarLeida: (id) => pedir(`/api/v1/alertas/${encodeURIComponent(id)}/leida`, { metodo: "POST" }),
    leerTodas: () => pedir("/api/v1/alertas/leer-todas", { metodo: "POST" }),
  };
}
