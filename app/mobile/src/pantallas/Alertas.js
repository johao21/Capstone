// Bandeja de alertas con marca de leída (RF-65). Tocar una alerta la marca como leída y abre su solicitud.
import { useLayoutEffect } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";

import { Callout, Cargando, Enlace, Icono, Insignia, Tarjeta, Vacio } from "../componentes/ui";
import { useAlertas } from "../AlertasContexto";
import { haceCuanto } from "../logica/formato";
import { colores, espacio, tonos } from "../tema";

// tipo de alerta (backend/app/alertas.py) -> [texto, tono, ícono]
const TIPOS = {
  emitida: ["Recomendación emitida", "ok", "check-circle"],
  rechazada: ["Solicitud rechazada", "error", "close-circle"],
  prediccion_lista: ["Predicción lista", "validacion", "chart-box-outline"],
};

export default function Alertas({ navigation }) {
  const { items, noLeidas, cargando, error, recargar, marcarLeida, leerTodas } = useAlertas();

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => <Enlace texto="Marcar todas" icono="check-all" sobreColor onPress={leerTodas} deshabilitado={noLeidas === 0} />,
    });
  }, [navigation, leerTodas, noLeidas]);

  function abrir(alerta) {
    marcarLeida(alerta.id);
    navigation.navigate("Solicitud", { id: alerta.solicitud_id });
  }

  if (cargando && items.length === 0 && !error) return <Cargando texto="Cargando alertas…" />;
  if (error && items.length === 0) return <Vacio icono="cloud-off-outline" tono="error" titulo="No se pudieron cargar las alertas" texto={error} accion={recargar} textoAccion="Reintentar" />;

  return (
    <FlatList
      data={items}
      keyExtractor={(a) => a.id}
      contentContainerStyle={estilos.lista}
      refreshControl={<RefreshControl refreshing={cargando} onRefresh={recargar} colors={[colores.primario]} />}
      ListHeaderComponent={
        <View style={{ gap: espacio.m, marginBottom: items.length ? espacio.m : 0 }}>
          {error ? <Callout tono="error" vivo>{`No se pudo actualizar: ${error}`}</Callout> : null}
          {items.length ? (
            <View style={estilos.resumen}>
              <Icono nombre={noLeidas === 0 ? "bell-check-outline" : "bell-ring-outline"} tamano={22} color={noLeidas === 0 ? tonos.ok.acento : colores.primarioOscuro} />
              <Text style={estilos.resumenTexto}>{noLeidas === 0 ? "Todo leído" : noLeidas === 1 ? "1 alerta sin leer" : `${noLeidas} alertas sin leer`}</Text>
            </View>
          ) : null}
        </View>
      }
      ListEmptyComponent={<Vacio icono="bell-sleep-outline" titulo="No tienes alertas" texto="Te avisaremos acá cuando una de tus solicitudes cambie de estado." />}
      renderItem={({ item }) => <ItemAlerta alerta={item} alAbrir={() => abrir(item)} />}
      ItemSeparatorComponent={() => <View style={{ height: espacio.m }} />}
    />
  );
}

function ItemAlerta({ alerta, alAbrir }) {
  const [tipo, tono, icono] = TIPOS[alerta.tipo] ?? [alerta.tipo, "neutro", "bell-outline"];
  const t = tonos[tono] ?? tonos.neutro;
  return (
    <Tarjeta
      onPress={alAbrir}
      etiquetaAccesible={`${alerta.leida ? "Leída" : "Sin leer"}. ${tipo}. ${alerta.mensaje}. ${haceCuanto(alerta.creada_en)}`}
      estilo={[estilos.alerta, !alerta.leida && { borderColor: t.acento, borderWidth: 2 }]}
    >
      <Insignia icono={icono} tono={tono} tamano={46} />
      <View style={{ flex: 1, gap: 2 }}>
        <View style={estilos.cabecera}>
          <Text style={[estilos.tipo, { color: t.texto }]}>{tipo}</Text>
          {!alerta.leida ? <View style={[estilos.punto, { backgroundColor: t.acento }]} accessibilityLabel="Sin leer" /> : null}
        </View>
        <Text style={[estilos.mensaje, !alerta.leida && { fontWeight: "700" }]}>{alerta.mensaje}</Text>
        <Text style={estilos.fecha}>{haceCuanto(alerta.creada_en)}</Text>
      </View>
    </Tarjeta>
  );
}

const estilos = StyleSheet.create({
  lista: { padding: espacio.l, paddingBottom: espacio.xl, flexGrow: 1, width: "100%", maxWidth: 720, alignSelf: "center" },
  resumen: { flexDirection: "row", alignItems: "center", gap: espacio.s },
  resumenTexto: { fontSize: 16, fontWeight: "800", color: colores.texto },
  alerta: { flexDirection: "row", alignItems: "flex-start", gap: espacio.m },
  cabecera: { flexDirection: "row", alignItems: "center", gap: espacio.s },
  tipo: { fontSize: 14, fontWeight: "800" },
  punto: { width: 10, height: 10, borderRadius: 5 },
  fecha: { fontSize: 13, color: colores.textoSuave, marginTop: 2 },
  mensaje: { fontSize: 15, color: colores.texto, lineHeight: 21 },
});
