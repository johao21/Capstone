// Piezas de interfaz que repiten todas las pantallas. Cada gráfico lleva su texto: el color y el ícono ayudan,
// pero nunca son lo único que dice algo (y los íconos se ocultan al lector de pantalla para que no los lea dos veces).
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { fraccionPuntaje, iniciales, progreso } from "../logica/estados";
import { puntaje } from "../logica/formato";
import { alturaTactil, colores, espacio, radio, sombra, tonos } from "../tema";

// Ícono de cada tono de aviso.
const ICONO_TONO = { ok: "check-circle", info: "information", curso: "information", validacion: "information", alerta: "alert", error: "alert-circle", neutro: "information-outline" };

/** Ícono decorativo (MaterialCommunityIcons). */
export function Icono({ nombre, tamano = 20, color = colores.texto }) {
  return <MaterialCommunityIcons name={nombre} size={tamano} color={color} accessible={false} importantForAccessibility="no" />;
}

/** Círculo de color suave con un ícono dentro. */
export function Insignia({ icono, tono = "neutro", tamano = 44 }) {
  const t = tonos[tono] ?? tonos.neutro;
  return (
    <View style={{ width: tamano, height: tamano, borderRadius: tamano / 2, backgroundColor: t.fondo, alignItems: "center", justifyContent: "center" }}>
      <Icono nombre={icono} tamano={Math.round(tamano * 0.52)} color={t.acento} />
    </View>
  );
}

/** Pastilla con el estado o el resultado, con su ícono opcional. */
export function Etiqueta({ texto, tono = "neutro", icono }) {
  const t = tonos[tono] ?? tonos.neutro;
  return (
    <View style={[estilos.etiqueta, { backgroundColor: t.fondo }]}>
      {icono ? <Icono nombre={icono} tamano={15} color={t.texto} /> : null}
      <Text style={[estilos.etiquetaTexto, { color: t.texto }]}>{texto}</Text>
    </View>
  );
}

/** Caja blanca con sombra suave. Con `onPress` es tocable y se anuncia como botón. */
export function Tarjeta({ children, onPress, estilo, etiquetaAccesible }) {
  if (!onPress) return <View style={[estilos.tarjeta, estilo]}>{children}</View>;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={etiquetaAccesible}
      onPress={onPress}
      style={({ pressed }) => [estilos.tarjeta, estilo, pressed && { backgroundColor: colores.primarioSuave }]}
    >
      {children}
    </Pressable>
  );
}

export function Boton({ texto, onPress, cargando = false, deshabilitado = false, variante = "primario", icono }) {
  const inactivo = cargando || deshabilitado;
  const colorTexto = variante === "primario" ? colores.primarioTexto : variante === "peligro" ? colores.error : colores.primario;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={texto}
      accessibilityState={{ disabled: inactivo, busy: cargando }}
      disabled={inactivo}
      onPress={onPress}
      style={({ pressed }) => [estilos.boton, estilos[`boton_${variante}`], inactivo && { opacity: 0.55 }, pressed && { opacity: 0.8 }]}
    >
      {cargando ? (
        <ActivityIndicator color={colorTexto} />
      ) : (
        <View style={estilos.botonContenido}>
          {icono ? <Icono nombre={icono} tamano={20} color={colorTexto} /> : null}
          <Text style={[estilos.botonTexto, { color: colorTexto }]}>{texto}</Text>
        </View>
      )}
    </Pressable>
  );
}

/** Texto tocable sin caja (acciones secundarias). `sobreColor` lo pinta de blanco, para la barra de arriba. */
export function Enlace({ texto, onPress, deshabilitado = false, icono, sobreColor = false }) {
  const color = sobreColor ? "#ffffff" : colores.primario;
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={texto} disabled={deshabilitado} onPress={onPress} hitSlop={8} style={estilos.enlace}>
      <View style={[estilos.enlaceContenido, deshabilitado && { opacity: 0.55 }]}>
        {icono ? <Icono nombre={icono} tamano={18} color={color} /> : null}
        <Text style={[estilos.enlaceTexto, { color }]}>{texto}</Text>
      </View>
    </Pressable>
  );
}

/** Aviso destacado, con ícono. `vivo` hace que el lector de pantalla lo lea apenas aparece (errores). */
export function Callout({ tono = "info", titulo, children, vivo = false, icono }) {
  const t = tonos[tono] ?? tonos.info;
  return (
    <View accessibilityRole={tono === "error" ? "alert" : undefined} accessibilityLiveRegion={vivo ? "polite" : "none"} style={[estilos.callout, { backgroundColor: t.fondo }]}>
      <Icono nombre={icono ?? ICONO_TONO[tono] ?? "information"} tamano={24} color={t.acento} />
      <View style={estilos.calloutCuerpo}>
        {titulo ? <Text style={[estilos.calloutTitulo, { color: t.texto }]}>{titulo}</Text> : null}
        {typeof children === "string" ? <Text style={[estilos.calloutTexto, { color: t.texto }]}>{children}</Text> : children}
      </View>
    </View>
  );
}

export function Cargando({ texto = "Cargando…" }) {
  return (
    <View style={estilos.centro} accessibilityRole="progressbar" accessibilityLabel={texto}>
      <ActivityIndicator size="large" color={colores.primario} />
      <Text style={estilos.suave}>{texto}</Text>
    </View>
  );
}

/** Pantalla vacía o con error: un dibujo grande, qué pasa y, si corresponde, una acción. */
export function Vacio({ titulo, texto, accion, textoAccion, icono = "inbox-outline", tono = "neutro" }) {
  return (
    <View style={estilos.centro}>
      <Insignia icono={icono} tono={tono} tamano={88} />
      <Text style={estilos.vacioTitulo}>{titulo}</Text>
      {texto ? <Text style={[estilos.suave, { textAlign: "center" }]}>{texto}</Text> : null}
      {accion ? (
        <View style={{ alignSelf: "stretch", marginTop: espacio.l }}>
          <Boton texto={textoAccion} onPress={accion} variante="secundario" icono="refresh" />
        </View>
      ) : null}
    </View>
  );
}

/** Bloque con título e ícono. */
export function Seccion({ titulo, icono, children }) {
  return (
    <View style={estilos.seccion}>
      <View style={estilos.seccionCabecera}>
        {icono ? <Icono nombre={icono} tamano={20} color={colores.primarioOscuro} /> : null}
        <Text accessibilityRole="header" style={estilos.seccionTitulo}>
          {titulo}
        </Text>
      </View>
      {children}
    </View>
  );
}

/** Par «dato — valor». */
export function Fila({ etiqueta, valor, ultima = false, icono }) {
  return (
    <View style={[estilos.fila, !ultima && estilos.filaBorde]}>
      {icono ? <Icono nombre={icono} tamano={18} color={colores.textoSuave} /> : null}
      <Text style={estilos.filaEtiqueta}>{etiqueta}</Text>
      <Text style={estilos.filaValor} selectable>
        {valor}
      </Text>
    </View>
  );
}

/** Círculo con las iniciales de la persona. */
export function Avatar({ nombre, tamano = 72 }) {
  return (
    <View style={{ width: tamano, height: tamano, borderRadius: tamano / 2, backgroundColor: colores.primario, alignItems: "center", justifyContent: "center" }} accessible={false}>
      <Text style={{ color: colores.primarioTexto, fontSize: Math.round(tamano * 0.38), fontWeight: "800" }}>{iniciales(nombre)}</Text>
    </View>
  );
}

/**
 * Recorrido de la solicitud en cinco etapas, de izquierda a derecha: lo hecho en verde con una marca,
 * la etapa actual con anillo y lo que falta en gris. Se entiende sin leer; el texto de abajo lo confirma.
 * Si la solicitud se detuvo (rechazada, anulada, con error) no hay recorrido que dibujar.
 */
export function Pasos({ estado }) {
  const p = progreso(estado);
  if (p.pasos.length === 0) return null;
  const ultimo = p.pasos.length - 1;
  return (
    <View accessible accessibilityLabel={p.resumen} style={{ gap: espacio.s }}>
      <View style={[estilos.pasosFila, { marginHorizontal: -espacio.s }]}>
        {p.pasos.map((paso, i) => (
          <View key={paso.clave} style={estilos.paso}>
            <View style={estilos.pasoGrafico}>
              <View style={[estilos.pasoLinea, i === 0 && { opacity: 0 }, paso.situacion !== "pendiente" && estilos.pasoLineaHecha]} />
              <CirculoPaso paso={paso} />
              <View style={[estilos.pasoLinea, i === ultimo && { opacity: 0 }, paso.situacion === "hecho" && estilos.pasoLineaHecha]} />
            </View>
            <Text style={[estilos.pasoTexto, paso.situacion === "actual" && estilos.pasoTextoActual, paso.situacion === "pendiente" && { opacity: 0.7 }]} numberOfLines={2}>
              {paso.texto}
            </Text>
          </View>
        ))}
      </View>
      <Text style={estilos.pasosResumen}>{p.resumen}</Text>
    </View>
  );
}

function CirculoPaso({ paso }) {
  if (paso.situacion === "hecho") {
    return (
      <View style={[estilos.circulo, { backgroundColor: colores.primario }]}>
        <Icono nombre="check" tamano={18} color={colores.primarioTexto} />
      </View>
    );
  }
  if (paso.situacion === "actual") {
    return (
      <View style={[estilos.circulo, { backgroundColor: colores.superficie, borderWidth: 3, borderColor: colores.primario }]}>
        <Icono nombre={paso.icono} tamano={17} color={colores.primario} />
      </View>
    );
  }
  return (
    <View style={[estilos.circulo, { backgroundColor: "#eaf1ee" }]}>
      <Icono nombre={paso.icono} tamano={16} color={tonos.neutro.acento} />
    </View>
  );
}

/** Versión chica del recorrido para las tarjetas de la lista: cinco segmentos que se van llenando. */
export function MiniPasos({ estado, tono = "curso" }) {
  const p = progreso(estado);
  if (p.pasos.length === 0) return null;
  return (
    <View accessible accessibilityLabel={p.resumen} style={estilos.miniFila}>
      {p.pasos.map((paso) => (
        <View
          key={paso.clave}
          style={[estilos.miniSegmento, paso.situacion === "hecho" && { backgroundColor: colores.primario }, paso.situacion === "actual" && { backgroundColor: (tonos[tono] ?? tonos.curso).acento }]}
        />
      ))}
    </View>
  );
}

/** Barra de 0 a 1 con el puntaje del modelo y su valor al lado. */
export function BarraPuntaje({ valor }) {
  return (
    <View style={estilos.barraFila} accessible accessibilityLabel={`Puntaje ${puntaje(valor)} de 1`}>
      <View style={estilos.barraPista}>
        <View style={[estilos.barraRelleno, { width: `${Math.round(fraccionPuntaje(valor) * 100)}%` }]} />
      </View>
      <Text style={estilos.barraValor}>{puntaje(valor)}</Text>
    </View>
  );
}

export const estilos = StyleSheet.create({
  etiqueta: { alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  etiquetaTexto: { fontSize: 13, fontWeight: "700" },
  tarjeta: {
    backgroundColor: colores.superficie,
    borderColor: colores.borde,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radio,
    padding: espacio.l,
    ...sombra,
  },
  boton: { minHeight: alturaTactil, borderRadius: radio, alignItems: "center", justifyContent: "center", paddingHorizontal: espacio.l, borderWidth: 1 },
  boton_primario: { backgroundColor: colores.primario, borderColor: colores.primario },
  boton_secundario: { backgroundColor: colores.superficie, borderColor: colores.primario },
  boton_peligro: { backgroundColor: colores.superficie, borderColor: colores.error },
  botonContenido: { flexDirection: "row", alignItems: "center", gap: espacio.s },
  botonTexto: { fontSize: 16, fontWeight: "700" },
  enlace: { minHeight: 44, justifyContent: "center", paddingHorizontal: espacio.m },
  enlaceContenido: { flexDirection: "row", alignItems: "center", gap: 6 },
  enlaceTexto: { fontSize: 15, fontWeight: "700" },
  callout: { flexDirection: "row", alignItems: "flex-start", gap: espacio.m, borderRadius: radio, padding: espacio.m },
  calloutCuerpo: { flex: 1, gap: espacio.xs },
  calloutTitulo: { fontSize: 15, fontWeight: "700" },
  calloutTexto: { fontSize: 15, lineHeight: 21 },
  centro: { flex: 1, alignItems: "center", justifyContent: "center", padding: espacio.xl, gap: espacio.m },
  suave: { color: colores.textoSuave, fontSize: 15, lineHeight: 21 },
  vacioTitulo: { color: colores.texto, fontSize: 19, fontWeight: "800", textAlign: "center", marginTop: espacio.s },
  seccion: { gap: espacio.s },
  seccionCabecera: { flexDirection: "row", alignItems: "center", gap: espacio.s, marginTop: espacio.s },
  seccionTitulo: { color: colores.primarioOscuro, fontSize: 17, fontWeight: "800" },
  fila: { flexDirection: "row", alignItems: "center", gap: espacio.s, paddingVertical: espacio.s },
  filaBorde: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colores.borde },
  filaEtiqueta: { width: 104, color: colores.textoSuave, fontSize: 14 },
  filaValor: { flex: 1, color: colores.texto, fontSize: 15, fontWeight: "600" },
  pasosFila: { flexDirection: "row" },
  paso: { flex: 1, alignItems: "center", gap: 6 },
  pasoGrafico: { flexDirection: "row", alignItems: "center", alignSelf: "stretch" },
  pasoLinea: { flex: 1, height: 3, backgroundColor: colores.borde },
  pasoLineaHecha: { backgroundColor: colores.primario },
  circulo: { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  pasoTexto: { fontSize: 12, lineHeight: 15, color: colores.textoSuave, textAlign: "center", paddingHorizontal: 1 },
  pasoTextoActual: { color: colores.texto, fontWeight: "800" },
  pasosResumen: { fontSize: 14, fontWeight: "700", color: colores.primarioOscuro, textAlign: "center" },
  miniFila: { flexDirection: "row", gap: 4 },
  miniSegmento: { flex: 1, height: 6, borderRadius: 3, backgroundColor: colores.borde },
  barraFila: { flexDirection: "row", alignItems: "center", gap: espacio.m },
  barraPista: { flex: 1, height: 10, borderRadius: 5, backgroundColor: "#e4eeea", overflow: "hidden" },
  barraRelleno: { height: 10, borderRadius: 5, backgroundColor: colores.primario },
  barraValor: { minWidth: 40, textAlign: "right", fontSize: 16, fontWeight: "800", color: colores.texto },
});
