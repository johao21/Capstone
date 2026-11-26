// Detalle de una solicitud y, cuando ya fue emitida, su recomendación en modo solo lectura (RF-63).
// Desde la app no se puede cargar, validar ni cambiar nada: solo consultar.
import { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import { BarraPuntaje, Callout, Cargando, Etiqueta, Fila, Icono, Insignia, Pasos, Seccion, Tarjeta, Vacio } from "../componentes/ui";
import { ADVERTENCIA, ESTADOS_CON_MOTIVO, ESTADOS_CON_RECOMENDACION, iconoEnsayo, iconoEstado, infoEnsayo, infoEstado, mensajeSinRecomendacion } from "../logica/estados";
import { dato, fechaCorta, fechaHora } from "../logica/formato";
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
  if (error && !solicitud) return <Vacio icono="cloud-off-outline" tono="error" titulo="No se pudo cargar la solicitud" texto={error} accion={() => cargar()} textoAccion="Reintentar" />;

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

      <Tarjeta estilo={{ gap: espacio.l }}>
        <View style={estilos.encabezado}>
          <Insignia icono={iconoEstado(solicitud.estado)} tono={tono} tamano={60} />
          <View style={{ flex: 1, gap: 6 }}>
            <Text style={estilos.codigo} accessibilityRole="header">
              {solicitud.codigo_interno}
            </Text>
            <Etiqueta texto={texto} tono={tono} />
          </View>
        </View>
        <Text style={estilos.etapa}>{solicitud.etapa}</Text>
        <Pasos estado={solicitud.estado} />
      </Tarjeta>

      {ESTADOS_CON_MOTIVO.includes(solicitud.estado) && solicitud.motivo_estado ? (
        <Callout tono={solicitud.estado === "error" ? "error" : "neutro"} titulo="Motivo">
          {solicitud.motivo_estado}
        </Callout>
      ) : null}

      <Seccion titulo="Recomendación" icono="clipboard-check-outline">
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

      <Seccion titulo="Aislado" icono="bacteria-outline">
        <Tarjeta>
          <Fila icono="bacteria-outline" etiqueta="Especie declarada" valor={dato(a.especie_declarada)} />
          <Fila icono="test-tube" etiqueta="Muestra" valor={dato(a.tipo_muestra)} />
          <Fila icono="calendar-month-outline" etiqueta="Aislamiento" valor={fechaCorta(a.fecha_aislamiento)} />
          <Fila icono="shield-off-outline" etiqueta="Resistencia" valor={dato(a.mecanismo_resistencia)} ultima={!a.observaciones} />
          {a.observaciones ? <Fila icono="note-text-outline" etiqueta="Observaciones" valor={a.observaciones} ultima /> : null}
        </Tarjeta>
      </Seccion>

      {an ? (
        <Seccion titulo="Análisis del genoma" icono="dna">
          <Tarjeta>
            <Fila icono="bacteria-outline" etiqueta="Especie" valor={dato(an.especie_detectada)} />
            <Fila icono="dna" etiqueta="Locus K" valor={an.locus_k_tipo ? `${an.locus_k_tipo}${an.locus_k_confianza ? ` (confianza ${an.locus_k_confianza})` : ""}` : "—"} />
            <Fila icono="counter" etiqueta="Genes" valor={dato(an.n_genes)} ultima />
          </Tarjeta>
        </Seccion>
      ) : null}

      <Seccion titulo="Historial" icono="history">
        <Tarjeta>
          {solicitud.historial.map((h, i) => {
            const e = infoEstado(h.estado_nuevo);
            const ultimo = i === solicitud.historial.length - 1;
            return (
              <View key={`${h.creado_en}-${i}`} style={estilos.hito}>
                <View style={estilos.hitoRiel}>
                  <Insignia icono={iconoEstado(h.estado_nuevo)} tono={e.tono} tamano={34} />
                  {!ultimo ? <View style={estilos.hitoLinea} /> : null}
                </View>
                <View style={[estilos.hitoCuerpo, !ultimo && { paddingBottom: espacio.m }]}>
                  <Text style={estilos.hitoEstado}>{e.texto}</Text>
                  <Text style={estilos.hitoFecha}>{fechaHora(h.creado_en)}</Text>
                  {h.motivo ? <Text style={estilos.hitoMotivo}>{h.motivo}</Text> : null}
                </View>
              </View>
            );
          })}
        </Tarjeta>
      </Seccion>

      <Seccion titulo="Personas" icono="account-group-outline">
        <Tarjeta>
          <Fila icono="account-outline" etiqueta="Registrada por" valor={dato(solicitud.registrada_por)} />
          <Fila icono="account-arrow-right-outline" etiqueta="Solicitante" valor={dato(solicitud.solicitante, "Sin solicitante")} />
          <Fila icono="microscope" etiqueta="Validación" valor={dato(solicitud.asignada_a, "Sin asignar")} ultima />
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
      <Callout tono="alerta" icono="flask-outline" titulo="Hipótesis a ensayar, no un diagnóstico">
        {rec.advertencia || ADVERTENCIA}
      </Callout>

      <Tarjeta>
        <Fila icono="file-document-outline" etiqueta="Versión" valor={rec.versiones?.length > 1 ? `${rec.version} de ${rec.versiones.length}` : String(rec.version)} />
        <Fila icono="account-check-outline" etiqueta="Validada por" valor={dato(rec.validador)} />
        <Fila icono="calendar-check-outline" etiqueta="Emitida" valor={fechaHora(rec.emitida_en)} />
        <Fila icono="chart-box-outline" etiqueta="Modelo" valor={dato(rec.modelo_version)} />
        <Fila icono="dna" etiqueta="Locus K" valor={dato(rec.locus_k_tipo)} ultima />
      </Tarjeta>

      {rec.baja_confianza ? (
        <Callout tono="alerta" icono="gauge-low" titulo="Baja confianza">
          El modelo marcó esta predicción como de baja confianza. Trátala con especial cautela y prioriza el ensayo de laboratorio.
        </Callout>
      ) : null}

      {rec.observacion ? (
        <Callout tono="info" icono="comment-text-outline" titulo="Observación del microbiólogo">
          {rec.observacion}
        </Callout>
      ) : null}

      <View style={estilos.subtituloFila}>
        <Icono nombre="virus-outline" tamano={22} color={colores.primarioOscuro} />
        <Text style={estilos.subtitulo}>Fagos candidatos, por orden de prioridad</Text>
      </View>
      <Text style={estilos.explicacion}>
        La barra muestra el puntaje del modelo, de 0 a 1. Sirve para ordenar los fagos; no es la probabilidad de que funcionen.
      </Text>
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
  const primero = c.rango === 1;
  return (
    <Tarjeta estilo={[{ gap: espacio.m }, c.descartado && { opacity: 0.7 }]}>
      <View style={estilos.candidatoCabecera}>
        <View style={[estilos.rango, primero && estilos.rangoPrimero]} accessibilityLabel={`Posición ${c.rango}`}>
          <Text style={[estilos.rangoTexto, primero && { color: colores.primarioTexto }]}>{c.rango}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={estilos.candidatoNombre}>{c.nombre}</Text>
          <Text style={estilos.candidatoAccesion}>{c.accesion}</Text>
        </View>
      </View>
      <BarraPuntaje valor={c.puntaje} />
      <View style={estilos.candidatoPie}>
        <Etiqueta texto={ensayo.texto} tono={ensayo.tono} icono={iconoEnsayo(c.resultado_ensayo)} />
        {c.descartado ? <Etiqueta texto="Descartado" tono="error" icono="cancel" /> : null}
      </View>
      {c.descartado && c.justificacion ? <Text style={estilos.justificacion}>{c.justificacion}</Text> : null}
    </Tarjeta>
  );
}

const estilos = StyleSheet.create({
  contenido: { padding: espacio.l, gap: espacio.m, paddingBottom: espacio.xl * 2, width: "100%", maxWidth: 720, alignSelf: "center" },
  encabezado: { flexDirection: "row", alignItems: "center", gap: espacio.m },
  codigo: { fontSize: 24, fontWeight: "800", color: colores.texto },
  etapa: { fontSize: 16, lineHeight: 22, color: colores.texto },
  subtituloFila: { flexDirection: "row", alignItems: "center", gap: espacio.s, marginTop: espacio.s },
  subtitulo: { flex: 1, fontSize: 16, fontWeight: "800", color: colores.primarioOscuro },
  explicacion: { fontSize: 14, lineHeight: 20, color: colores.textoSuave },
  hito: { flexDirection: "row", gap: espacio.m },
  hitoRiel: { alignItems: "center" },
  hitoLinea: { flex: 1, width: 2, backgroundColor: colores.borde, marginVertical: 2 },
  hitoCuerpo: { flex: 1, gap: 2, paddingTop: 2 },
  hitoEstado: { fontSize: 15, fontWeight: "700", color: colores.texto },
  hitoFecha: { fontSize: 13, color: colores.textoSuave },
  hitoMotivo: { fontSize: 14, color: colores.texto },
  candidatoCabecera: { flexDirection: "row", alignItems: "center", gap: espacio.m },
  rango: { width: 38, height: 38, borderRadius: 19, backgroundColor: colores.primarioSuave, alignItems: "center", justifyContent: "center" },
  rangoPrimero: { backgroundColor: colores.primario },
  rangoTexto: { color: colores.primario, fontWeight: "800", fontSize: 17 },
  candidatoNombre: { fontSize: 16, fontWeight: "700", color: colores.texto },
  candidatoAccesion: { fontSize: 13, color: colores.textoSuave },
  candidatoPie: { flexDirection: "row", flexWrap: "wrap", gap: espacio.s },
  justificacion: { fontSize: 14, color: colores.textoSuave },
});
