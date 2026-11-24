// Sesión de la app: quién está conectado, a qué servidor, y el cliente de la API ya configurado con ambos.
import Constants from "expo-constants";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Platform } from "react-native";

import { crearCliente, ErrorApi, normalizarServidor } from "./api/cliente";
import { CLAVES, guardar, leer } from "./almacen";

const PUERTO_API = 8000;

/**
 * Dirección con la que se prueba primero:
 * - web (solo desarrollo): el mismo origen desde donde se abrió la página;
 * - Expo Go en el teléfono: la IP del computador que sirve la app, con el puerto de la API (Docker publica el 8000);
 * - emulador de Android: 10.0.2.2, que es el computador visto desde el emulador.
 */
export function servidorPorDefecto() {
  if (Platform.OS === "web") return typeof window !== "undefined" ? window.location.origin : `http://localhost:${PUERTO_API}`;
  const host = Constants.expoConfig?.hostUri?.split(":")[0];
  return host ? `http://${host}:${PUERTO_API}` : `http://10.0.2.2:${PUERTO_API}`;
}

const Contexto = createContext(null);

export function useSesion() {
  const valor = useContext(Contexto);
  if (!valor) throw new Error("useSesion se usa dentro de <ProveedorSesion>");
  return valor;
}

export function ProveedorSesion({ children }) {
  // fase: «arrancando» (aún se lee lo guardado), «fuera» (pantalla de ingreso) o «dentro».
  const [fase, setFase] = useState("arrancando");
  const [usuario, setUsuario] = useState(null);
  const [servidor, setServidor] = useState(servidorPorDefecto);
  // Mensaje para la pantalla de ingreso: por qué se cerró la sesión.
  const [aviso, setAviso] = useState(null);

  // El cliente lee el token y el servidor de estas referencias, así que se crea una sola vez.
  const token = useRef(null);
  const servidorActual = useRef(servidor);

  const cerrarLocal = useCallback((mensaje) => {
    token.current = null;
    guardar(CLAVES.token, null);
    setUsuario(null);
    setAviso(mensaje ?? null);
    setFase("fuera");
  }, []);

  const cliente = useMemo(
    () =>
      crearCliente({
        servidor: () => servidorActual.current,
        token: () => token.current,
        guardarToken: (nuevo) => {
          token.current = nuevo;
          guardar(CLAVES.token, nuevo);
        },
        sesionVencida: () => cerrarLocal("Tu sesión venció. Vuelve a ingresar."),
      }),
    [cerrarLocal],
  );

  // Al abrir la app: recupera el servidor y el token guardados y comprueba que la sesión siga viva.
  useEffect(() => {
    let activo = true;
    (async () => {
      const guardado = await leer(CLAVES.servidor);
      if (guardado && activo) {
        servidorActual.current = guardado;
        setServidor(guardado);
      }
      const recordado = await leer(CLAVES.token);
      if (!recordado) return activo && setFase("fuera");
      token.current = recordado;
      try {
        const yo = await cliente.yo();
        if (!activo) return;
        setUsuario(yo);
        setFase("dentro");
      } catch (error) {
        if (!activo) return;
        // Un 401 ya cerró la sesión desde el cliente (con su aviso). Otro fallo, como no tener red, no borra el token guardado.
        if (error instanceof ErrorApi && error.estado === 401) return;
        token.current = null;
        setAviso(`No se pudo retomar la sesión: ${error.message}`);
        setFase("fuera");
      }
    })();
    return () => {
      activo = false;
    };
  }, [cliente]);

  const ingresar = useCallback(
    async (correo, password, direccion) => {
      const url = normalizarServidor(direccion);
      if (!url) throw new ErrorApi("La dirección del servidor no es válida. Ejemplo: http://192.168.1.20:8000");
      servidorActual.current = url;
      setServidor(url);
      const respuesta = await cliente.iniciarSesion(correo, password);
      token.current = respuesta.access_token;
      await Promise.all([guardar(CLAVES.token, respuesta.access_token), guardar(CLAVES.servidor, url)]);
      setUsuario(respuesta.usuario);
      setAviso(null);
      setFase("dentro");
    },
    [cliente],
  );

  const salir = useCallback(async () => {
    try {
      await cliente.cerrarSesion(); // revoca la sesión en el servidor (RF-02); si no hay red, igual se cierra acá
    } catch {
      /* se cierra la sesión local de todos modos */
    }
    cerrarLocal(null);
  }, [cliente, cerrarLocal]);

  const valor = useMemo(() => ({ fase, usuario, servidor, aviso, cliente, ingresar, salir }), [fase, usuario, servidor, aviso, cliente, ingresar, salir]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}
