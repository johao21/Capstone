// Detalle de una solicitud y, cuando ya fue emitida, su recomendación en modo solo lectura (RF-63).
// Desde la app no se puede cargar, validar ni cambiar nada: solo consultar.
import { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import { Callout, Cargando, Etiqueta, Fila, Seccion, Tarjeta, Vacio } from "../componentes/ui";
import { ADVERTENCIA, ESTADOS_CON_MOTIVO, ESTADOS_CON_RECOMENDACION, infoEnsayo, infoEstado, mensajeSinRecomendacion } from "../logica/estados";
import { dato, fechaCorta, fechaHora, puntaje } from "../logica/formato";
import { useSesion } from "../Sesion";
import { colores, espacio } from "../tema";

export default function Detalle({ route, navigation }) {
  const { id } = route.params;
  const { cliente } = useSesion();
  const [solicitud, setSolicitud] = useState(null);
  const [recomendacion, setRecomendacion] = useState(null);
  const [errorRecomendacion, setErrorRecomendacion] = useState(null);
  const [error, setError] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [refrescando, setRefrescando] = useState(false);

  const cargar = useCallback(
    async (silencioso = false) => {
      if (!silencioso) setCargando(true);
      try {
        const detalle = await cliente.detalleSolicitud(id);
        // La recomendación existe solo desde que se emite; antes, pedirla daría 404.
        let rec = null;
        let falloRec = null;
        if (ESTADOS_CON_RECOMENDACION.includes(detalle.estado)) {
          try {
            rec = await cliente.recomendacionEmitida(id);
          } catch (e) {
            falloRec = e.message;
          }
        }
        // Todo se publica junto: si el detalle se pintara antes que la recomendación, una solicitud emitida
        // mostraría por un instante «todavía no hay recomendación».
        setSolicitud(detalle);
        setRecomendacion(rec);
        setErrorRecomendacion(falloRec);
        setError(null);
      } catch (e) {
        setError(e.message);
      } finally {
        setCargando(false);
        setRefrescando(false);
      }
    },
    [cliente, id],
  );

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Desde una alerta se llega sin el código; el título de la barra lo toma del detalle apenas llega.
  useEffect(() => {
    if (solicitud?.codigo_interno) navigation.setOptions({ title: solicitud.codigo_interno });
  }, [navigation, solicitud?.codigo_interno]);

  if (cargando && !solicitud) return <Cargando texto="Cargando solicitud…" />;
  if (error && !solicitud) return <Vacio titulo="No se pudo cargar la solicitud" texto={error} accion={() => cargar()} textoAccion="Reintentar" />;

  const { texto, tono } = infoEstado(solicitud.estado);
  const sinRecomendacion = mensajeSinRecomendacion(solicitud.estado);
  const a = solicitud.aislado;
  const an = solicitud.analisis;

  return (
    <ScrollView
      contentContainerStyle={estilos.contenido}
      refreshControl={<RefreshControl refreshing={refrescando} onRefresh={() => { setRefrescando(true); cargar(true); }} colors={[colores.primario]} />}
    >
      {error ? <Callout tono="error" vivo>{`No se pudo actualizar: ${error}`}</Callout> : null}

      <View style={estilos.encabezado}>
        <Text style={estilos.codigo} accessibilityRole="header">
          {solicitud.codigo_interno}
        </Text>
        <Etiqueta texto={texto} tono={tono} />
        <Text style={estilos.etapa}>{solicitud.etapa}</Text>
      </View>

      {ESTADOS_CON_MOTIVO.includes(solicitud.estado) && solicitud.motivo_estado ? (
        <Callout tono={solicitud.estado === "error" ? "error" : "neutro"} titulo="Motivo">
          {solicitud.motivo_estado}
        </Callout>
      ) : null}

      <Seccion titulo="Recomendación">
        {recomendacion ? (
          <Recomendacion rec={recomendacion} />
        ) : errorRecomendacion ? (
          <Callout tono="error" titulo="No se pudo cargar la recomendación" vivo>
            {errorRecomendacion}
          </Callout>
        ) : (
          <Callout tono="info" titulo={sinRecomendacion.titulo}>
            {sinRecomendacion.texto}
          </Callout>
        )}
      </Seccion>

      <Seccion titulo="Aislado">
        <Tarjeta>
          <Fila etiqueta="Especie declarada" valor={dato(a.especie_declarada)} />
          <Fila etiqueta="Muestra" valor={dato(a.tipo_muestra)} />
          <Fila etiqueta="Aislamiento" valor={fechaCorta(a.fecha_aislamiento)} />
          <Fila etiqueta="Resistencia" valor={dato(a.mecanismo_resistencia)} ultima={!a.observaciones} />
          {a.observaciones ? <Fila etiqueta="Observaciones" valor={a.observaciones} ultima /> : null}
        </Tarjeta>
      </Seccion>

      {an ? (
        <Seccion titulo="Análisis del genoma">
          <Tarjeta>
            <Fila etiqueta="Especie" valor={dato(an.especie_detectada)} />
            <Fila etiqueta="Locus K" valor={an.locus_k_tipo ? `${an.locus_k_tipo}${an.locus_k_confianza ? ` (confianza ${an.locus_k_confianza})` : ""}` : "—"} />
            <Fila etiqueta="Genes" valor={dato(an.n_genes)} ultima />
          </Tarjeta>
        </Seccion>
      ) : null}

      <Seccion titulo="Historial">
        <Tarjeta>
          {solicitud.historial.map((h, i) => (
            <View key={`${h.creado_en}-${i}`} style={[estilos.hito, i < solicitud.historial.length - 1 && estilos.hitoBorde]}>
              <Text style={estilos.hitoEstado}>{infoEstado(h.estado_nuevo).texto}</Text>
              <Text style={estilos.hitoFecha}>{fechaHora(h.creado_en)}</Text>
              {h.motivo ? <Text style={estilos.hitoMotivo}>{h.motivo}</Text> : null}
            </View>
          ))}
        </Tarjeta>
      </Seccion>

      <Seccion titulo="Personas">
        <Tarjeta>
          <Fila etiqueta="Registrada por" valor={dato(solicitud.registrada_por)} />
          <Fila etiqueta="Solicitante" valor={dato(solicitud.solicitante, "Sin solicitante")} />
          <Fila etiqueta="Validación" valor={dato(solicitud.asignada_a, "Sin asignar")} ultima />
        </Tarjeta>
      </Seccion>
    </ScrollView>
  );
}

/** La recomendación emitida: la advertencia va primero y siempre visible (RF-45). */
function Recomendacion({ rec }) {
  const candidatos = [...rec.candidatos].sort((x, y) => x.rango - y.rango);
  return (
    <View style={{ gap: espacio.m }}>
      <Callout tono="alerta" titulo="Hipótesis a ensayar, no un diagnóstico">
        {rec.advertencia || ADVERTENCIA}
      </Callout>

      <Tarjeta>
        <Fila etiqueta="Versión" valor={rec.versiones?.length > 1 ? `${rec.version} de ${rec.versiones.length}` : String(rec.version)} />
        <Fila etiqueta="Validada por" valor={dato(rec.validador)} />
        <Fila etiqueta="Emitida" valor={fechaHora(rec.emitida_en)} />
        <Fila etiqueta="Modelo" valor={dato(rec.modelo_version)} />
        <Fila etiqueta="Locus K" valor={dato(rec.locus_k_tipo)} ultima />
      </Tarjeta>

      {rec.baja_confianza ? (
        <Callout tono="alerta" titulo="Baja confianza">
          El modelo marcó esta predicción como de baja confianza. Trátala con especial cautela y prioriza el ensayo de laboratorio.
        </Callout>
      ) : null}

      {rec.observacion ? (
        <Callout tono="info" titulo="Observación del microbiólogo">
          {rec.observacion}
        </Callout>
      ) : null}

      <Text style={estilos.subtitulo}>Fagos candidatos, por orden de prioridad</Text>
      {candidatos.length === 0 ? (
        <Callout tono="neutro">Esta recomendación no incluye fagos candidatos.</Callout>
      ) : (
        candidatos.map((c) => <Candidato key={c.fago_id} c={c} />)
      )}
    </View>
  );
}

function Candidato({ c }) {
  const ensayo = infoEnsayo(c.resultado_ensayo);
  return (
    <Tarjeta estilo={[{ gap: espacio.s }, c.descartado && { opacity: 0.7 }]}>
      <View style={estilos.candidatoCabecera}>
        <View style={estilos.rango} accessibilityLabel={`Posición ${c.rango}`}>
          <Text style={estilos.rangoTexto}>{c.rango}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={estilos.candidatoNombre}>{c.nombre}</Text>
          <Text style={estilos.candidatoAccesion}>{c.accesion}</Text>
        </View>
        <View style={{ alignItems: "flex-end" }}>
          <Text style={estilos.puntaje}>{puntaje(c.puntaje)}</Text>
          <Text style={estilos.puntajeEtiqueta}>puntaje</Text>
        </View>
      </View>
      <View style={estilos.candidatoPie}>
        <Etiqueta texto={ensayo.texto} tono={ensayo.tono} />
        {c.descartado ? <Etiqueta texto="Descartado" tono="error" /> : null}
      </View>
      {c.descartado && c.justificacion ? <Text style={estilos.justificacion}>{c.justificacion}</Text> : null}
    </Tarjeta>
  );
}

const estilos = StyleSheet.create({
  contenido: { padding: espacio.l, gap: espacio.m, paddingBottom: espacio.xl * 2, width: "100%", maxWidth: 720, alignSelf: "center" },
  encabezado: { gap: espacio.s },
  codigo: { fontSize: 24, fontWeight: "800", color: colores.texto },
  etapa: { fontSize: 16, color: colores.texto },
  subtitulo: { fontSize: 15, fontWeight: "700", color: colores.texto, marginTop: espacio.s },
  hito: { paddingVertical: espacio.s, gap: 2 },
  hitoBorde: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colores.borde },
  hitoEstado: { fontSize: 15, fontWeight: "700", color: colores.texto },
  hitoFecha: { fontSize: 13, color: colores.textoSuave },
  hitoMotivo: { fontSize: 14, color: colores.texto },
  candidatoCabecera: { flexDirection: "row", alignItems: "center", gap: espacio.m },
  rango: { width: 36, height: 36, borderRadius: 18, backgroundColor: colores.primarioSuave, alignItems: "center", justifyContent: "center" },
  rangoTexto: { color: colores.primario, fontWeight: "800", fontSize: 16 },
  candidatoNombre: { fontSize: 16, fontWeight: "700", color: colores.texto },
  candidatoAccesion: { fontSize: 13, color: colores.textoSuave },
  puntaje: { fontSize: 18, fontWeight: "800", color: colores.texto },
  puntajeEtiqueta: { fontSize: 12, color: colores.textoSuave },
  candidatoPie: { flexDirection: "row", flexWrap: "wrap", gap: espacio.s },
  justificacion: { fontSize: 14, color: colores.textoSuave },
});
