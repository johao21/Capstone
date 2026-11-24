// Lista de solicitudes con su estado (RF-62). Muestra las que el servidor deja ver a este rol (RF-06).
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { Cargando, Callout, Enlace, Etiqueta, Tarjeta, Vacio } from "../componentes/ui";
import { contarPorFiltro, filtrarSolicitudes, FILTROS, infoEstado } from "../logica/estados";
import { dato, haceCuanto, plural } from "../logica/formato";
import { useSesion } from "../Sesion";
import { colores, espacio } from "../tema";

const PAGINA = 100;

export default function Solicitudes({ navigation }) {
  const { cliente } = useSesion();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [refrescando, setRefrescando] = useState(false);
  const [cargandoMas, setCargandoMas] = useState(false);
  const [error, setError] = useState(null);
  const [filtro, setFiltro] = useState("todas");
  const enCurso = useRef(false); // evita pedir dos páginas a la vez

  const cargar = useCallback(
    async ({ desde = 0, silencioso = false } = {}) => {
      if (enCurso.current) return;
      enCurso.current = true;
      if (desde > 0) setCargandoMas(true);
      else if (!silencioso) setCargando(true);
      try {
        const pagina = await cliente.listarSolicitudes({ limite: PAGINA, desplazamiento: desde });
        setItems((actual) => (desde > 0 ? [...actual, ...pagina.items] : pagina.items));
        setTotal(pagina.total);
        setError(null);
      } catch (e) {
        setError(e.message);
      } finally {
        enCurso.current = false;
        setCargando(false);
        setRefrescando(false);
        setCargandoMas(false);
      }
    },
    [cliente],
  );

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Al volver desde el detalle o desde otra pestaña, la lista se refresca sin mostrar el indicador de carga.
  useEffect(() => navigation.addListener("focus", () => cargar({ silencioso: true })), [navigation, cargar]);

  useLayoutEffect(() => {
    navigation.setOptions({ headerRight: () => <Enlace texto="Actualizar" onPress={() => cargar()} deshabilitado={cargando} /> });
  }, [navigation, cargar, cargando]);

  const visibles = filtrarSolicitudes(items, filtro);
  const conteo = contarPorFiltro(items);
  const faltan = items.length < total;

  if (cargando && items.length === 0) return <Cargando texto="Cargando solicitudes…" />;
  if (error && items.length === 0) return <Vacio titulo="No se pudieron cargar las solicitudes" texto={error} accion={() => cargar()} textoAccion="Reintentar" />;

  return (
    <FlatList
      data={visibles}
      keyExtractor={(s) => s.id}
      contentContainerStyle={estilos.lista}
      refreshControl={<RefreshControl refreshing={refrescando} onRefresh={() => { setRefrescando(true); cargar({ silencioso: true }); }} colors={[colores.primario]} />}
      onEndReachedThreshold={0.4}
      onEndReached={() => faltan && cargar({ desde: items.length })}
      ListHeaderComponent={
        <View style={{ gap: espacio.m }}>
          {error ? <Callout tono="error" vivo>{`No se pudo actualizar: ${error}`}</Callout> : null}
          <View style={estilos.filtros} accessibilityRole="tablist">
            {FILTROS.map((f) => {
              const activo = f.clave === filtro;
              return (
                <Pressable
                  key={f.clave}
                  onPress={() => setFiltro(f.clave)}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: activo }}
                  accessibilityLabel={`${f.etiqueta}, ${plural(conteo[f.clave], "solicitud", "solicitudes")}`}
                  style={[estilos.chip, activo && estilos.chipActivo]}
                >
                  <Text style={[estilos.chipTexto, activo && estilos.chipTextoActivo]}>
                    {f.etiqueta} · {conteo[f.clave]}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      }
      ListEmptyComponent={
        <Vacio
          titulo={items.length === 0 ? "Aún no hay solicitudes" : "Ninguna solicitud en este grupo"}
          texto={items.length === 0 ? "Cuando haya solicitudes visibles para tu cuenta, aparecerán acá." : "Prueba con otro grupo."}
        />
      }
      ListFooterComponent={faltan ? <Text style={estilos.pie}>{cargandoMas ? "Cargando más…" : `Mostrando ${items.length} de ${total}`}</Text> : null}
      renderItem={({ item }) => <ItemSolicitud solicitud={item} alAbrir={() => navigation.navigate("Solicitud", { id: item.id, codigo: item.codigo_interno })} />}
      ItemSeparatorComponent={() => <View style={{ height: espacio.m }} />}
    />
  );
}

function ItemSolicitud({ solicitud: s, alAbrir }) {
  const { texto, tono } = infoEstado(s.estado);
  return (
    <Tarjeta onPress={alAbrir} etiquetaAccesible={`Solicitud ${s.codigo_interno}, ${texto}. ${s.etapa}`} estilo={{ gap: espacio.s }}>
      <View style={estilos.filaSuperior}>
        <Text style={estilos.codigo} numberOfLines={1}>
          {s.codigo_interno}
        </Text>
        <Etiqueta texto={texto} tono={tono} />
      </View>
      <Text style={estilos.etapa}>{s.etapa}</Text>
      {s.especie_detectada || s.locus_k_tipo ? (
        <Text style={estilos.detalle}>
          {s.especie_detectada ? <Text style={{ fontStyle: "italic" }}>{s.especie_detectada}</Text> : null}
          {s.especie_detectada && s.locus_k_tipo ? " · " : ""}
          {s.locus_k_tipo ? `Locus K: ${s.locus_k_tipo}` : ""}
        </Text>
      ) : null}
      <Text style={estilos.fecha}>Actualizada {haceCuanto(s.actualizada_en)}</Text>
    </Tarjeta>
  );
}

const estilos = StyleSheet.create({
  lista: { padding: espacio.l, paddingBottom: espacio.xl, flexGrow: 1, gap: 0, width: "100%", maxWidth: 720, alignSelf: "center" },
  filtros: { flexDirection: "row", flexWrap: "wrap", gap: espacio.s, marginBottom: espacio.m },
  chip: { minHeight: 40, justifyContent: "center", paddingHorizontal: espacio.m, borderRadius: 999, borderWidth: 1, borderColor: colores.borde, backgroundColor: colores.superficie },
  chipActivo: { backgroundColor: colores.primario, borderColor: colores.primario },
  chipTexto: { fontSize: 14, fontWeight: "600", color: colores.texto },
  chipTextoActivo: { color: colores.primarioTexto },
  filaSuperior: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: espacio.m },
  codigo: { flexShrink: 1, fontSize: 17, fontWeight: "800", color: colores.texto },
  etapa: { fontSize: 15, color: colores.texto },
  detalle: { fontSize: 14, color: colores.textoSuave },
  fecha: { fontSize: 13, color: colores.textoSuave },
  pie: { textAlign: "center", color: colores.textoSuave, fontSize: 13, paddingVertical: espacio.l },
});
