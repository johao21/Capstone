// Bandeja de alertas compartida: la pestaña muestra cuántas hay sin leer y la pantalla de alertas muestra la lista.
// RF-66 (notificaciones push) no está construido; en su lugar la bandeja se actualiza al volver a la app y cada minuto.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { AppState } from "react-native";

import { useSesion } from "./Sesion";

const CADA_MS = 60_000;
const Contexto = createContext(null);

export function useAlertas() {
  const valor = useContext(Contexto);
  if (!valor) throw new Error("useAlertas se usa dentro de <ProveedorAlertas>");
  return valor;
}

export function ProveedorAlertas({ habilitado, children }) {
  const { cliente } = useSesion();
  const [items, setItems] = useState([]);
  const [noLeidas, setNoLeidas] = useState(0);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);
  const montado = useRef(true);

  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
    };
  }, []);

  const recargar = useCallback(async () => {
    if (!habilitado) return;
    setCargando(true);
    try {
      const respuesta = await cliente.alertas({ limite: 100 });
      if (!montado.current) return;
      setItems(respuesta.items);
      setNoLeidas(respuesta.no_leidas);
      setError(null);
    } catch (e) {
      if (montado.current) setError(e.message);
    } finally {
      if (montado.current) setCargando(false);
    }
  }, [cliente, habilitado]);

  useEffect(() => {
    if (!habilitado) return undefined;
    recargar();
    const reloj = setInterval(() => AppState.currentState === "active" && recargar(), CADA_MS);
    const suscripcion = AppState.addEventListener("change", (estado) => estado === "active" && recargar());
    return () => {
      clearInterval(reloj);
      suscripcion.remove();
    };
  }, [habilitado, recargar]);

  // Se marca como leída al instante en pantalla y se confirma con el servidor; si falla, se vuelve a pedir la lista real.
  const marcarLeida = useCallback(
    async (id) => {
      const alerta = items.find((a) => a.id === id);
      if (!alerta || alerta.leida) return;
      setItems((actual) => actual.map((a) => (a.id === id ? { ...a, leida: true } : a)));
      setNoLeidas((n) => Math.max(0, n - 1));
      try {
        await cliente.marcarLeida(id);
      } catch {
        recargar();
      }
    },
    [cliente, items, recargar],
  );

  const leerTodas = useCallback(async () => {
    setItems((actual) => actual.map((a) => ({ ...a, leida: true })));
    setNoLeidas(0);
    try {
      await cliente.leerTodas();
    } catch {
      recargar();
    }
  }, [cliente, recargar]);

  const valor = useMemo(
    () => ({ items, noLeidas, cargando, error, recargar, marcarLeida, leerTodas }),
    [items, noLeidas, cargando, error, recargar, marcarLeida, leerTodas],
  );
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}
