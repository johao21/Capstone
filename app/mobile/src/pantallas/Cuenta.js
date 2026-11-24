// Datos de la cuenta y cierre de sesión (RF-02). También se usa solo, para los roles que no tienen nada más en la app.
import Constants from "expo-constants";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { Boton, Callout, Fila, Seccion, Tarjeta } from "../componentes/ui";
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
      {sinAcceso ? (
        <Callout tono="info" titulo={`Tu rol (${nombreRol(usuario.rol)}) no usa la app móvil`}>
          La app móvil sirve para consultar solicitudes, recomendaciones y alertas. Para el resto de tu trabajo, ingresa a la plataforma web.
        </Callout>
      ) : null}

      <Seccion titulo="Cuenta">
        <Tarjeta>
          <Fila etiqueta="Nombre" valor={usuario.nombre} />
          <Fila etiqueta="Correo" valor={usuario.correo} />
          <Fila etiqueta="Rol" valor={nombreRol(usuario.rol)} />
          <Fila etiqueta="Centro" valor={usuario.centro_nombre} ultima />
        </Tarjeta>
      </Seccion>

      <Seccion titulo="Conexión">
        <Tarjeta>
          <Fila etiqueta="Servidor" valor={servidor} />
          <Fila etiqueta="Versión de la app" valor={Constants.expoConfig?.version ?? "—"} ultima />
        </Tarjeta>
      </Seccion>

      <Boton texto="Cerrar sesión" variante="peligro" onPress={cerrar} cargando={saliendo} />

      <View style={{ marginTop: espacio.m }}>
        <Text style={estilos.pie}>SIRFA apoya la decisión de un profesional: no diagnostica ni prescribe. Toda recomendación es una hipótesis que debe ensayarse en laboratorio.</Text>
      </View>
    </ScrollView>
  );
}

const estilos = StyleSheet.create({
  contenido: { padding: espacio.l, gap: espacio.m, width: "100%", maxWidth: 720, alignSelf: "center" },
  pie: { fontSize: 13, color: colores.textoSuave, textAlign: "center", lineHeight: 18 },
});
