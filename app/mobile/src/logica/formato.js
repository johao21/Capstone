// Formatos de fecha y de números. Se hacen a mano, sin Intl, para que el texto sea igual en Android, en la web y en las pruebas.

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const dos = (n) => String(n).padStart(2, "0");

/**
 * Convierte el texto de fecha de la API en Date. La API a veces entrega fechas sin zona horaria
 * (así las devuelve SQLite); el servidor las trata como UTC, y aquí igual.
 */
export function parsearFecha(valor) {
  if (!valor) return null;
  if (valor instanceof Date) return Number.isNaN(valor.getTime()) ? null : valor;
  let texto = String(valor).trim();
  const soloFecha = /^\d{4}-\d{2}-\d{2}$/.test(texto);
  if (soloFecha) texto += "T00:00:00"; // una fecha sin hora (p. ej. fecha de aislamiento) se lee como fecha local, no UTC
  else if (!/(Z|[+-]\d{2}:?\d{2})$/i.test(texto)) texto += "Z";
  const fecha = new Date(texto);
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}

/** «17 nov 2026» */
export function fechaCorta(valor) {
  const f = parsearFecha(valor);
  return f ? `${f.getDate()} ${MESES[f.getMonth()]} ${f.getFullYear()}` : "—";
}

/** «17 nov 2026, 14:32» */
export function fechaHora(valor) {
  const f = parsearFecha(valor);
  return f ? `${fechaCorta(f)}, ${dos(f.getHours())}:${dos(f.getMinutes())}` : "—";
}

/** «hace 5 min», «hace 3 h», «ayer»; pasadas dos semanas, la fecha. `ahora` se inyecta para poder probarlo. */
export function haceCuanto(valor, ahora = new Date()) {
  const f = parsearFecha(valor);
  if (!f) return "—";
  const segundos = Math.round((ahora.getTime() - f.getTime()) / 1000);
  if (segundos < 45) return "ahora";
  const minutos = Math.round(segundos / 60);
  if (minutos < 60) return `hace ${minutos} min`;
  const horas = Math.round(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;
  const dias = Math.floor(horas / 24);
  if (dias === 1) return "ayer";
  if (dias < 14) return `hace ${dias} días`;
  return fechaCorta(f);
}

/** Puntaje del modelo con dos decimales y coma («0,87»). No es un porcentaje ni una probabilidad calibrada. */
export function puntaje(valor) {
  return typeof valor === "number" && Number.isFinite(valor) ? valor.toFixed(2).replace(".", ",") : "—";
}

/** Texto de un dato que puede faltar. */
export function dato(valor, vacio = "—") {
  return valor === null || valor === undefined || valor === "" ? vacio : String(valor);
}

/** «1 solicitud» / «3 solicitudes» */
export function plural(n, singular, pluralTexto) {
  return `${n} ${n === 1 ? singular : pluralTexto}`;
}
