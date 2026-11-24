// Paleta de la app: la misma de la web (frontend/estilos.css), para que las dos se vean como un solo sistema.
export const colores = {
  fondo: "#f6f8f7",
  superficie: "#ffffff",
  texto: "#17231f",
  textoSuave: "#55645f",
  borde: "#d6dfdb",
  primario: "#0b6b52",
  primarioTexto: "#ffffff",
  primarioSuave: "#e2f1ec",
  error: "#a32121",
};

// Tono de una etiqueta o aviso -> colores de fondo y de texto. «curso» es el azul de «en proceso».
export const tonos = {
  ok: { fondo: "#e1f3e8", texto: "#17683f" },
  curso: { fondo: "#e3edf9", texto: "#1f4f8a" },
  info: { fondo: "#e3edf9", texto: "#1f4f8a" },
  alerta: { fondo: "#fff2d6", texto: "#8a5a00" },
  error: { fondo: "#fde7e7", texto: "#a32121" },
  neutro: { fondo: "#eceff0", texto: "#3f4b47" },
};

export const espacio = { xs: 4, s: 8, m: 12, l: 16, xl: 24 };
export const radio = 12;

// Alto mínimo de todo lo que se toca: 48 dp, por encima de los 44 que recomienda la guía de accesibilidad.
export const alturaTactil = 48;
