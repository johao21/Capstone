// Piezas de interfaz que repiten todas las pantallas.
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { alturaTactil, colores, espacio, radio, tonos } from "../tema";

/** Pastilla con el estado o el resultado. El color nunca va solo: siempre lleva texto. */
export function Etiqueta({ texto, tono = "neutro" }) {
  const t = tonos[tono] ?? tonos.neutro;
  return (
    <View style={[estilos.etiqueta, { backgroundColor: t.fondo }]}>
      <Text style={[estilos.etiquetaTexto, { color: t.texto }]}>{texto}</Text>
    </View>
  );
}

/** Caja blanca con borde. Con `onPress` es tocable y se anuncia como botón. */
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

export function Boton({ texto, onPress, cargando = false, deshabilitado = false, variante = "primario" }) {
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
      {cargando ? <ActivityIndicator color={colorTexto} /> : <Text style={[estilos.botonTexto, { color: colorTexto }]}>{texto}</Text>}
    </Pressable>
  );
}

/** Texto tocable sin caja (acciones secundarias, como «Actualizar»). */
export function Enlace({ texto, onPress, deshabilitado = false }) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={texto} disabled={deshabilitado} onPress={onPress} hitSlop={8} style={estilos.enlace}>
      <Text style={[estilos.enlaceTexto, deshabilitado && { opacity: 0.5 }]}>{texto}</Text>
    </Pressable>
  );
}

/** Aviso destacado. `vivo` hace que el lector de pantalla lo lea apenas aparece (errores). */
export function Callout({ tono = "info", titulo, children, vivo = false }) {
  const t = tonos[tono] ?? tonos.info;
  return (
    <View
      accessibilityRole={tono === "error" ? "alert" : undefined}
      accessibilityLiveRegion={vivo ? "polite" : "none"}
      style={[estilos.callout, { backgroundColor: t.fondo, borderColor: t.texto }]}
    >
      {titulo ? <Text style={[estilos.calloutTitulo, { color: t.texto }]}>{titulo}</Text> : null}
      {typeof children === "string" ? <Text style={[estilos.calloutTexto, { color: t.texto }]}>{children}</Text> : children}
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

/** Pantalla vacía o con error, con una acción opcional. */
export function Vacio({ titulo, texto, accion, textoAccion }) {
  return (
    <View style={estilos.centro}>
      <Text style={estilos.vacioTitulo}>{titulo}</Text>
      {texto ? <Text style={[estilos.suave, { textAlign: "center" }]}>{texto}</Text> : null}
      {accion ? (
        <View style={{ alignSelf: "stretch", marginTop: espacio.l }}>
          <Boton texto={textoAccion} onPress={accion} variante="secundario" />
        </View>
      ) : null}
    </View>
  );
}

/** Bloque con título. */
export function Seccion({ titulo, children }) {
  return (
    <View style={estilos.seccion}>
      <Text accessibilityRole="header" style={estilos.seccionTitulo}>
        {titulo}
      </Text>
      {children}
    </View>
  );
}

/** Par «dato — valor». */
export function Fila({ etiqueta, valor, ultima = false }) {
  return (
    <View style={[estilos.fila, !ultima && estilos.filaBorde]}>
      <Text style={estilos.filaEtiqueta}>{etiqueta}</Text>
      <Text style={estilos.filaValor} selectable>
        {valor}
      </Text>
    </View>
  );
}

export const estilos = StyleSheet.create({
  etiqueta: { alignSelf: "flex-start", paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  etiquetaTexto: { fontSize: 13, fontWeight: "700" },
  tarjeta: {
    backgroundColor: colores.superficie,
    borderColor: colores.borde,
    borderWidth: 1,
    borderRadius: radio,
    padding: espacio.l,
  },
  boton: { minHeight: alturaTactil, borderRadius: radio, alignItems: "center", justifyContent: "center", paddingHorizontal: espacio.l, borderWidth: 1 },
  boton_primario: { backgroundColor: colores.primario, borderColor: colores.primario },
  boton_secundario: { backgroundColor: colores.superficie, borderColor: colores.primario },
  boton_peligro: { backgroundColor: colores.superficie, borderColor: colores.error },
  botonTexto: { fontSize: 16, fontWeight: "700" },
  enlace: { minHeight: 44, justifyContent: "center", paddingHorizontal: espacio.m },
  enlaceTexto: { color: colores.primario, fontSize: 15, fontWeight: "700" },
  callout: { borderLeftWidth: 4, borderRadius: radio, padding: espacio.m, gap: espacio.xs },
  calloutTitulo: { fontSize: 15, fontWeight: "700" },
  calloutTexto: { fontSize: 15, lineHeight: 21 },
  centro: { flex: 1, alignItems: "center", justifyContent: "center", padding: espacio.xl, gap: espacio.s },
  suave: { color: colores.textoSuave, fontSize: 15, lineHeight: 21 },
  vacioTitulo: { color: colores.texto, fontSize: 18, fontWeight: "700", textAlign: "center" },
  seccion: { gap: espacio.s },
  seccionTitulo: { color: colores.textoSuave, fontSize: 13, fontWeight: "700", letterSpacing: 0.6, textTransform: "uppercase", marginTop: espacio.s },
  fila: { flexDirection: "row", gap: espacio.m, paddingVertical: espacio.s },
  filaBorde: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colores.borde },
  filaEtiqueta: { width: 112, color: colores.textoSuave, fontSize: 14 },
  filaValor: { flex: 1, color: colores.texto, fontSize: 15, fontWeight: "600" },
});
