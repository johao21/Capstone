// Inicio de sesión (RF-61): las mismas credenciales de la web.
import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Boton, Callout, Icono } from "../componentes/ui";
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
            <View style={estilos.logo}>
              <Icono nombre="virus-outline" tamano={52} color={colores.primarioTexto} />
            </View>
            <Text style={estilos.marca} accessibilityRole="header">
              SIRFA
            </Text>
            <Text style={estilos.lema}>Sistema de Recomendación de Fagos frente a Antibiorresistencia</Text>
            <Text style={estilos.bienvenida}>Consulta cómo van tus solicitudes y qué fagos se recomiendan.</Text>
          </View>

          {aviso ? <Callout tono="alerta" vivo>{aviso}</Callout> : null}

          <View style={estilos.formulario}>
            <Text style={estilos.etiqueta}>Correo</Text>
            <View style={estilos.campoConIcono}>
              <Icono nombre="email-outline" tamano={22} color={colores.textoSuave} />
              <TextInput
                style={estilos.entrada}
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
            </View>

            <Text style={estilos.etiqueta}>Contraseña</Text>
            <View style={estilos.campoConIcono}>
              <Icono nombre="lock-outline" tamano={22} color={colores.textoSuave} />
              <TextInput
                style={estilos.entrada}
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
                hitSlop={6}
              >
                <Icono nombre={verPassword ? "eye-off-outline" : "eye-outline"} tamano={24} color={colores.primario} />
              </Pressable>
            </View>

            {error ? <Callout tono="error" vivo>{error}</Callout> : null}

            <View style={{ marginTop: espacio.s }}>
              <Boton texto="Ingresar" icono="login" onPress={enviar} cargando={enviando} deshabilitado={!puedeEnviar} />
            </View>
          </View>

          <View style={estilos.servidor}>
            <Pressable
              onPress={() => setEditaServidor((v) => !v)}
              accessibilityRole="button"
              accessibilityState={{ expanded: editaServidor }}
              accessibilityLabel="Servidor"
              style={estilos.servidorCabecera}
            >
              <Icono nombre="server-network-outline" tamano={20} color={colores.textoSuave} />
              <Text style={estilos.servidorTitulo}>Servidor</Text>
              <Text style={estilos.servidorValor} numberOfLines={1}>
                {editaServidor ? "Ocultar" : direccion}
              </Text>
            </Pressable>
            {editaServidor ? (
              <View style={{ gap: espacio.s }}>
                <TextInput
                  style={estilos.campoServidor}
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
  cabecera: { alignItems: "center", gap: espacio.s },
  logo: { width: 96, height: 96, borderRadius: 28, backgroundColor: colores.primario, alignItems: "center", justifyContent: "center", marginBottom: espacio.s },
  marca: { fontSize: 38, fontWeight: "800", color: colores.primarioOscuro, letterSpacing: 3 },
  lema: { fontSize: 14, color: colores.textoSuave, lineHeight: 20, textAlign: "center" },
  bienvenida: { fontSize: 16, color: colores.texto, lineHeight: 22, textAlign: "center", marginTop: espacio.s },
  formulario: { gap: espacio.s },
  etiqueta: { fontSize: 14, fontWeight: "700", color: colores.texto, marginTop: espacio.s },
  campoConIcono: {
    minHeight: alturaTactil,
    flexDirection: "row",
    alignItems: "center",
    gap: espacio.s,
    paddingLeft: espacio.m,
    backgroundColor: colores.superficie,
    borderColor: colores.borde,
    borderWidth: 1,
    borderRadius: radio,
  },
  entrada: { flex: 1, minHeight: alturaTactil, fontSize: 16, color: colores.texto },
  ojo: { minHeight: alturaTactil, justifyContent: "center", paddingHorizontal: espacio.m },
  campoServidor: {
    minHeight: alturaTactil,
    backgroundColor: colores.superficie,
    borderColor: colores.borde,
    borderWidth: 1,
    borderRadius: radio,
    paddingHorizontal: espacio.m,
    fontSize: 16,
    color: colores.texto,
  },
  servidor: { gap: espacio.s },
  servidorCabecera: { minHeight: 44, flexDirection: "row", alignItems: "center", gap: espacio.s },
  servidorTitulo: { fontSize: 14, fontWeight: "700", color: colores.textoSuave },
  servidorValor: { flex: 1, textAlign: "right", fontSize: 14, color: colores.primario, fontWeight: "600" },
  ayuda: { fontSize: 13, color: colores.textoSuave, lineHeight: 18 },
  pie: { fontSize: 13, color: colores.textoSuave, textAlign: "center" },
});
