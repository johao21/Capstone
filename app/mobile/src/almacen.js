// Guarda el token de la sesión y la dirección del servidor. En el teléfono usa el almacén seguro del sistema
// (Keystore en Android); en la versión web, que solo sirve para desarrollo, SecureStore no existe y se guarda en memoria.
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const memoria = new Map();

export const CLAVES = { token: "sirfa.token", servidor: "sirfa.servidor" };

export async function leer(clave) {
  if (Platform.OS === "web") return memoria.get(clave) ?? null;
  try {
    return await SecureStore.getItemAsync(clave);
  } catch {
    return null; // sin almacén seguro la sesión simplemente no se recuerda
  }
}

export async function guardar(clave, valor) {
  if (Platform.OS === "web") {
    if (valor) memoria.set(clave, valor);
    else memoria.delete(clave);
    return;
  }
  try {
    if (valor) await SecureStore.setItemAsync(clave, valor);
    else await SecureStore.deleteItemAsync(clave);
  } catch {
    /* sin almacén seguro: se sigue con la sesión en memoria */
  }
}
