// Inicio de sesión (RF-61): las mismas credenciales de la web.
import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Boton, Callout } from "../componentes/ui";
import { useSesion } from "../Sesion";
import { alturaTactil, colores, espacio, radio } from "../tema";

export default function Ingreso() {
  const { servidor, aviso, ingresar } = useSesion();
  const [correo, setCorreo] = useState("");
  const [password, setPassword] = useState("");
  const [verPassword, setVerPassword] = useState(false);
  const [direccion, setDireccion] = useState(servidor);
  const [editaServidor, setEditaServidor] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);

  const puedeEnviar = correo.trim().length > 0 && password.length > 0 && !enviando;

  async function enviar() {
    if (!puedeEnviar) return;
    setEnviando(true);
    setError(null);
    try {
      await ingresar(correo, password, direccion);
    } catch (e) {
      setError(e.message);
      setEnviando(false);
    }
  }

  return (
    <SafeAreaView style={estilos.pantalla}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={estilos.contenido} keyboardShouldPersistTaps="handled">
          <View style={estilos.cabecera}>
            <Text style={estilos.marca} accessibilityRole="header">
              SIRFA
            </Text>
            <Text style={estilos.lema}>Sistema de Recomendación de Fagos frente a Antibiorresistencia</Text>
          </View>

          {aviso ? <Callout tono="alerta" vivo>{aviso}</Callout> : null}

          <View style={estilos.formulario}>
            <Text style={estilos.etiqueta}>Correo</Text>
            <TextInput
              style={estilos.campo}
              value={correo}
              onChangeText={setCorreo}
              placeholder="nombre@centro.cl"
              placeholderTextColor={colores.textoSuave}
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="email"
              keyboardType="email-address"
              textContentType="username"
              returnKeyType="next"
              accessibilityLabel="Correo"
            />

            <Text style={estilos.etiqueta}>Contraseña</Text>
            <View style={estilos.campoConBoton}>
              <TextInput
                style={[estilos.campo, { flex: 1, borderWidth: 0 }]}
                value={password}
                onChangeText={setPassword}
                secureTextEntry={!verPassword}
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="current-password"
                textContentType="password"
                returnKeyType="go"
                onSubmitEditing={enviar}
                accessibilityLabel="Contraseña"
              />
              <Pressable
                onPress={() => setVerPassword((v) => !v)}
                accessibilityRole="button"
                accessibilityLabel={verPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                style={estilos.ojo}
              >
                <Text style={estilos.ojoTexto}>{verPassword ? "Ocultar" : "Mostrar"}</Text>
              </Pressable>
            </View>

            {error ? <Callout tono="error" vivo>{error}</Callout> : null}

            <Boton texto="Ingresar" onPress={enviar} cargando={enviando} deshabilitado={!puedeEnviar} />
          </View>

          <View style={estilos.servidor}>
            <Pressable
              onPress={() => setEditaServidor((v) => !v)}
              accessibilityRole="button"
              accessibilityState={{ expanded: editaServidor }}
              accessibilityLabel="Servidor"
              style={estilos.servidorCabecera}
            >
              <Text style={estilos.servidorTitulo}>Servidor</Text>
              <Text style={estilos.servidorValor} numberOfLines={1}>
                {editaServidor ? "Ocultar" : direccion}
              </Text>
            </Pressable>
            {editaServidor ? (
              <View style={{ gap: espacio.s }}>
                <TextInput
                  style={estilos.campo}
                  value={direccion}
                  onChangeText={setDireccion}
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="url"
                  accessibilityLabel="Dirección del servidor"
                />
                <Text style={estilos.ayuda}>
                  En el emulador de Android: http://10.0.2.2:8000. En un teléfono: la IP del computador donde corre SIRFA en la misma red wifi, por ejemplo
                  http://192.168.1.20:8000.
                </Text>
              </View>
            ) : null}
          </View>

          <Text style={estilos.pie}>SIRFA apoya la decisión de un profesional: no diagnostica ni prescribe.</Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const estilos = StyleSheet.create({
  pantalla: { flex: 1, backgroundColor: colores.fondo },
  contenido: { padding: espacio.xl, gap: espacio.xl, flexGrow: 1, justifyContent: "center", width: "100%", maxWidth: 480, alignSelf: "center" },
  cabecera: { gap: espacio.xs },
  marca: { fontSize: 40, fontWeight: "800", color: colores.primario, letterSpacing: 2 },
  lema: { fontSize: 15, color: colores.textoSuave, lineHeight: 21 },
  formulario: { gap: espacio.s },
  etiqueta: { fontSize: 14, fontWeight: "700", color: colores.texto, marginTop: espacio.s },
  campo: {
    minHeight: alturaTactil,
    backgroundColor: colores.superficie,
    borderColor: colores.borde,
    borderWidth: 1,
    borderRadius: radio,
    paddingHorizontal: espacio.m,
    fontSize: 16,
    color: colores.texto,
  },
  campoConBoton: { flexDirection: "row", alignItems: "center", backgroundColor: colores.superficie, borderColor: colores.borde, borderWidth: 1, borderRadius: radio },
  ojo: { minHeight: alturaTactil, justifyContent: "center", paddingHorizontal: espacio.m },
  ojoTexto: { color: colores.primario, fontWeight: "700", fontSize: 14 },
  servidor: { gap: espacio.s },
  servidorCabecera: { minHeight: 44, flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: espacio.m },
  servidorTitulo: { fontSize: 14, fontWeight: "700", color: colores.textoSuave },
  servidorValor: { flexShrink: 1, fontSize: 14, color: colores.primario, fontWeight: "600" },
  ayuda: { fontSize: 13, color: colores.textoSuave, lineHeight: 18 },
  pie: { fontSize: 13, color: colores.textoSuave, textAlign: "center" },
});
