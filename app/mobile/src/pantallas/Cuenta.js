// Datos de la cuenta y cierre de sesión (RF-02). También se usa solo, para los roles que no tienen nada más en la app.
import Constants from "expo-constants";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { Avatar, Boton, Callout, Etiqueta, Fila, Seccion, Tarjeta } from "../componentes/ui";
import { nombreRol } from "../logica/estados";
import { useSesion } from "../Sesion";
import { colores, espacio } from "../tema";

export default function Cuenta({ sinAcceso = false }) {
  const { usuario, servidor, salir } = useSesion();
  const [saliendo, setSaliendo] = useState(false);

  async function cerrar() {
    setSaliendo(true);
    await salir();
  }

  return (
    <ScrollView contentContainerStyle={estilos.contenido}>
      <View style={estilos.perfil}>
        <Avatar nombre={usuario.nombre} />
        <Text style={estilos.nombre}>{usuario.nombre}</Text>
        <View style={{ alignSelf: "center" }}>
          <Etiqueta texto={nombreRol(usuario.rol)} tono="validacion" icono="shield-account-outline" />
        </View>
      </View>

      {sinAcceso ? (
        <Callout tono="info" titulo={`Tu rol (${nombreRol(usuario.rol)}) no usa la app móvil`}>
          La app móvil sirve para consultar solicitudes, recomendaciones y alertas. Para el resto de tu trabajo, ingresa a la plataforma web.
        </Callout>
      ) : null}

      <Seccion titulo="Cuenta" icono="account-circle-outline">
        <Tarjeta>
          <Fila icono="account-outline" etiqueta="Nombre" valor={usuario.nombre} />
          <Fila icono="email-outline" etiqueta="Correo" valor={usuario.correo} />
          <Fila icono="shield-account-outline" etiqueta="Rol" valor={nombreRol(usuario.rol)} />
          <Fila icono="domain" etiqueta="Centro" valor={usuario.centro_nombre} ultima />
        </Tarjeta>
      </Seccion>

      <Seccion titulo="Conexión" icono="server-network-outline">
        <Tarjeta>
          <Fila icono="link-variant" etiqueta="Servidor" valor={servidor} />
          <Fila icono="cellphone" etiqueta="Versión de la app" valor={Constants.expoConfig?.version ?? "—"} ultima />
        </Tarjeta>
      </Seccion>

      <Boton texto="Cerrar sesión" icono="logout" variante="peligro" onPress={cerrar} cargando={saliendo} />

      <View style={{ marginTop: espacio.m }}>
        <Text style={estilos.pie}>SIRFA apoya la decisión de un profesional: no diagnostica ni prescribe. Toda recomendación es una hipótesis que debe ensayarse en laboratorio.</Text>
      </View>
    </ScrollView>
  );
}

const estilos = StyleSheet.create({
  contenido: { padding: espacio.l, gap: espacio.m, width: "100%", maxWidth: 720, alignSelf: "center" },
  perfil: { alignItems: "center", gap: espacio.s, paddingVertical: espacio.m },
  nombre: { fontSize: 22, fontWeight: "800", color: colores.texto, textAlign: "center" },
  pie: { fontSize: 13, color: colores.textoSuave, textAlign: "center", lineHeight: 18 },
});
