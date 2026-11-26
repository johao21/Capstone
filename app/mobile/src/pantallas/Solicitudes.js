// Lista de solicitudes con su estado (RF-62). Muestra las que el servidor deja ver a este rol (RF-06).
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { Cargando, Callout, Enlace, Etiqueta, Icono, Insignia, MiniPasos, Tarjeta, Vacio } from "../componentes/ui";
import { contarPorFiltro, filtrarSolicitudes, FILTROS, iconoEstado, infoEstado, progreso } from "../logica/estados";
import { dato, haceCuanto, plural } from "../logica/formato";
import { useSesion } from "../Sesion";
import { colores, espacio, radio, tonos } from "../tema";

const PAGINA = 100;

export default function Solicitudes({ navigation }) {
  const { cliente, usuario } = useSesion();
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
    navigation.setOptions({ headerRight: () => <Enlace texto="Actualizar" icono="refresh" sobreColor onPress={() => cargar()} deshabilitado={cargando} /> });
  }, [navigation, cargar, cargando]);

  const visibles = filtrarSolicitudes(items, filtro);
  const conteo = contarPorFiltro(items);
  const faltan = items.length < total;
  const primerNombre = String(usuario?.nombre ?? "").trim().split(/\s+/)[0];

  if (cargando && items.length === 0) return <Cargando texto="Cargando solicitudes…" />;
  if (error && items.length === 0) return <Vacio icono="cloud-off-outline" tono="error" titulo="No se pudieron cargar las solicitudes" texto={error} accion={() => cargar()} textoAccion="Reintentar" />;

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
          <View>
            <Text style={estilos.saludo}>{primerNombre ? `Hola, ${primerNombre}` : "Hola"}</Text>
            <Text style={estilos.saludoTexto}>Toca un grupo para ver solo esas solicitudes.</Text>
          </View>
          <View style={estilos.filtros} accessibilityRole="tablist">
            {FILTROS.map((f) => {
              const activo = f.clave === filtro;
              const t = tonos[f.tono];
              return (
                <Pressable
                  key={f.clave}
                  onPress={() => setFiltro(f.clave)}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: activo }}
                  accessibilityLabel={`${f.etiqueta}, ${plural(conteo[f.clave], "solicitud", "solicitudes")}`}
                  style={[estilos.cuadro, activo && { backgroundColor: t.fondo, borderColor: t.acento, borderWidth: 2 }]}
                >
                  <Icono nombre={f.icono} tamano={24} color={t.acento} />
                  <Text style={estilos.cuadroNumero}>{conteo[f.clave]}</Text>
                  <Text style={[estilos.cuadroTexto, activo && { color: t.texto }]} numberOfLines={2}>
                    {f.etiqueta}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      }
      ListEmptyComponent={
        <Vacio
          icono={items.length === 0 ? "clipboard-text-outline" : "filter-outline"}
          titulo={items.length === 0 ? "Aún no hay solicitudes" : "Ninguna solicitud en este grupo"}
          texto={items.length === 0 ? "Cuando haya solicitudes visibles para tu cuenta, aparecerán acá." : "Prueba con otro grupo."}
        />
      }
      ListFooterComponent={faltan ? <Text style={estilos.pieLista}>{cargandoMas ? "Cargando más…" : `Mostrando ${items.length} de ${total}`}</Text> : null}
      renderItem={({ item }) => <ItemSolicitud solicitud={item} alAbrir={() => navigation.navigate("Solicitud", { id: item.id, codigo: item.codigo_interno })} />}
      ItemSeparatorComponent={() => <View style={{ height: espacio.m }} />}
    />
  );
}

function ItemSolicitud({ solicitud: s, alAbrir }) {
  const { texto, tono } = infoEstado(s.estado);
  const p = progreso(s.estado);
  return (
    <Tarjeta onPress={alAbrir} etiquetaAccesible={`Solicitud ${s.codigo_interno}, ${texto}. ${s.etapa}`} estilo={{ gap: espacio.m }}>
      <View style={estilos.filaSuperior}>
        <Insignia icono={iconoEstado(s.estado)} tono={tono} tamano={48} />
        <View style={{ flex: 1, gap: 6 }}>
          <Text style={estilos.codigo} numberOfLines={1}>
            {s.codigo_interno}
          </Text>
          <Etiqueta texto={texto} tono={tono} />
        </View>
        <Icono nombre="chevron-right" tamano={26} color={colores.textoSuave} />
      </View>
      <Text style={estilos.etapa}>{s.etapa}</Text>
      {s.especie_detectada || s.locus_k_tipo ? (
        <View style={estilos.especie}>
          <Icono nombre="bacteria-outline" tamano={18} color={colores.textoSuave} />
          <Text style={estilos.detalle}>
            {s.especie_detectada ? <Text style={{ fontStyle: "italic" }}>{s.especie_detectada}</Text> : null}
            {s.especie_detectada && s.locus_k_tipo ? " · " : ""}
            {s.locus_k_tipo ? `Locus K: ${s.locus_k_tipo}` : ""}
          </Text>
        </View>
      ) : null}
      {p.pasos.length ? <MiniPasos estado={s.estado} tono={tono} /> : null}
      <View style={estilos.pie}>
        <Text style={estilos.fecha}>{p.pasos.length === 0 ? "Terminó sin recomendación" : p.actual < p.total - 1 ? `Etapa ${p.actual + 1} de ${p.total}` : "Proceso completo"}</Text>
        <Text style={estilos.fecha}>Actualizada {haceCuanto(s.actualizada_en)}</Text>
      </View>
    </Tarjeta>
  );
}

const estilos = StyleSheet.create({
  lista: { padding: espacio.l, paddingBottom: espacio.xl, flexGrow: 1, gap: 0, width: "100%", maxWidth: 720, alignSelf: "center" },
  saludo: { fontSize: 24, fontWeight: "800", color: colores.texto },
  saludoTexto: { fontSize: 15, color: colores.textoSuave, marginTop: 2 },
  filtros: { flexDirection: "row", gap: espacio.s, marginBottom: espacio.m },
  cuadro: {
    flex: 1,
    minHeight: 100,
    alignItems: "center",
    justifyContent: "flex-start",
    gap: 2,
    paddingVertical: espacio.m,
    paddingHorizontal: 4,
    borderRadius: radio,
    borderWidth: 1,
    borderColor: colores.borde,
    backgroundColor: colores.superficie,
  },
  cuadroNumero: { fontSize: 24, fontWeight: "800", color: colores.texto },
  cuadroTexto: { fontSize: 12, lineHeight: 15, minHeight: 30, fontWeight: "700", color: colores.textoSuave, textAlign: "center" },
  filaSuperior: { flexDirection: "row", alignItems: "center", gap: espacio.m },
  codigo: { flexShrink: 1, fontSize: 18, fontWeight: "800", color: colores.texto },
  etapa: { fontSize: 15, lineHeight: 21, color: colores.texto },
  especie: { flexDirection: "row", alignItems: "center", gap: espacio.s },
  detalle: { flex: 1, fontSize: 14, color: colores.textoSuave },
  pie: { flexDirection: "row", justifyContent: "space-between", gap: espacio.m },
  fecha: { fontSize: 13, color: colores.textoSuave },
  pieLista: { textAlign: "center", color: colores.textoSuave, fontSize: 13, paddingVertical: espacio.l },
});
