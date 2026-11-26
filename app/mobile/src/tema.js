// Paleta de la app. Verde agua como color de marca, tonos pastel para los estados y texto oscuro encima:
// el color nunca va solo (siempre lo acompañan un ícono y un texto) y todo texto cumple contraste AA.
export const colores = {
  fondo: "#f2f8f6",
  superficie: "#ffffff",
  texto: "#1b2b27",
  textoSuave: "#4d605a",
  borde: "#dbe8e3",
  primario: "#0d7a6b",
  primarioOscuro: "#0a5d51",
  primarioTexto: "#ffffff",
  primarioSuave: "#dff3ee",
  error: "#b3261e",
};

// Tono de una etiqueta, aviso o ícono -> fondo pastel, texto oscuro y color del ícono (`acento`).
// «curso» e «info» son el azul de «en proceso»; «validacion» es el violeta de «lo revisa un microbiólogo».
export const tonos = {
  ok: { fondo: "#ddf4e6", texto: "#13663b", acento: "#1f8a50" },
  curso: { fondo: "#e0eefd", texto: "#1b4b8a", acento: "#2f72c4" },
  info: { fondo: "#e0eefd", texto: "#1b4b8a", acento: "#2f72c4" },
  validacion: { fondo: "#ece6fa", texto: "#52349a", acento: "#6a43c9" },
  alerta: { fondo: "#fff0d0", texto: "#7a4c00", acento: "#a86a00" },
  error: { fondo: "#fde3e0", texto: "#a1261c", acento: "#c93a2d" },
  neutro: { fondo: "#e9eeed", texto: "#3b4844", acento: "#66766f" },
};

export const espacio = { xs: 4, s: 8, m: 12, l: 16, xl: 24 };
export const radio = 16;

// Sombra suave de las tarjetas (en vez de un borde marcado).
export const sombra = {
  shadowColor: "#0b3d35",
  shadowOpacity: 0.08,
  shadowRadius: 8,
  shadowOffset: { width: 0, height: 2 },
  elevation: 2,
};

// Alto mínimo de todo lo que se toca: 48 dp, por encima de los 44 que recomienda la guía de accesibilidad.
export const alturaTactil = 48;
