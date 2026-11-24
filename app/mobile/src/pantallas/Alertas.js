// Bandeja de alertas con marca de leída (RF-65). Tocar una alerta la marca como leída y abre su solicitud.
import { useLayoutEffect } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";

import { Callout, Cargando, Enlace, Etiqueta, Tarjeta, Vacio } from "../componentes/ui";
import { useAlertas } from "../AlertasContexto";
import { haceCuanto } from "../logica/formato";
import { colores, espacio } from "../tema";

// tipo de alerta (backend/app/alertas.py) -> [texto, tono]
const TIPOS = {
  emitida: ["Recomendación emitida", "ok"],
  rechazada: ["Solicitud rechazada", "error"],
  prediccion_lista: ["Predicción lista", "alerta"],
};

export default function Alertas({ navigation }) {
  const { items, noLeidas, cargando, error, recargar, marcarLeida, leerTodas } = useAlertas();

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => <Enlace texto="Marcar todas" onPress={leerTodas} deshabilitado={noLeidas === 0} />,
    });
  }, [navigation, leerTodas, noLeidas]);

  function abrir(alerta) {
    marcarLeida(alerta.id);
    navigation.navigate("Solicitud", { id: alerta.solicitud_id });
  }

  if (cargando && items.length === 0 && !error) return <Cargando texto="Cargando alertas…" />;
  if (error && items.length === 0) return <Vacio titulo="No se pudieron cargar las alertas" texto={error} accion={recargar} textoAccion="Reintentar" />;

  return (
    <FlatList
      data={items}
      keyExtractor={(a) => a.id}
      contentContainerStyle={estilos.lista}
      refreshControl={<RefreshControl refreshing={cargando} onRefresh={recargar} colors={[colores.primario]} />}
      ListHeaderComponent={
        <View style={{ gap: espacio.m, marginBottom: items.length ? espacio.m : 0 }}>
          {error ? <Callout tono="error" vivo>{`No se pudo actualizar: ${error}`}</Callout> : null}
          {items.length ? <Text style={estilos.resumen}>{noLeidas === 0 ? "Todo leído" : noLeidas === 1 ? "1 alerta sin leer" : `${noLeidas} alertas sin leer`}</Text> : null}
        </View>
      }
      ListEmptyComponent={<Vacio titulo="No tienes alertas" texto="Te avisaremos acá cuando una de tus solicitudes cambie de estado." />}
      renderItem={({ item }) => <ItemAlerta alerta={item} alAbrir={() => abrir(item)} />}
      ItemSeparatorComponent={() => <View style={{ height: espacio.m }} />}
    />
  );
}

function ItemAlerta({ alerta, alAbrir }) {
  const [tipo, tono] = TIPOS[alerta.tipo] ?? [alerta.tipo, "neutro"];
  return (
    <Tarjeta
      onPress={alAbrir}
      etiquetaAccesible={`${alerta.leida ? "Leída" : "Sin leer"}. ${tipo}. ${alerta.mensaje}. ${haceCuanto(alerta.creada_en)}`}
      estilo={[{ gap: espacio.s }, !alerta.leida && estilos.sinLeer]}
    >
      <View style={estilos.cabecera}>
        <Etiqueta texto={tipo} tono={tono} />
        <View style={estilos.cabeceraDerecha}>
          <Text style={estilos.fecha}>{haceCuanto(alerta.creada_en)}</Text>
          {!alerta.leida ? <View style={estilos.punto} /> : null}
        </View>
      </View>
      <Text style={[estilos.mensaje, !alerta.leida && { fontWeight: "700" }]}>{alerta.mensaje}</Text>
    </Tarjeta>
  );
}

const estilos = StyleSheet.create({
  lista: { padding: espacio.l, paddingBottom: espacio.xl, flexGrow: 1, width: "100%", maxWidth: 720, alignSelf: "center" },
  resumen: { fontSize: 14, fontWeight: "700", color: colores.textoSuave },
  sinLeer: { borderColor: colores.primario, borderWidth: 2 },
  cabecera: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: espacio.m },
  cabeceraDerecha: { flexDirection: "row", alignItems: "center", gap: espacio.s },
  fecha: { fontSize: 13, color: colores.textoSuave },
  punto: { width: 10, height: 10, borderRadius: 5, backgroundColor: colores.primario },
  mensaje: { fontSize: 15, color: colores.texto, lineHeight: 21 },
});
