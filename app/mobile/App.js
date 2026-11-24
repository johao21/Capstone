// Raíz de la app: decide qué se ve según la sesión y arma la navegación.
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { DefaultTheme, NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { ProveedorAlertas, useAlertas } from "./src/AlertasContexto";
import { Cargando } from "./src/componentes/ui";
import { capacidades } from "./src/logica/estados";
import Alertas from "./src/pantallas/Alertas";
import Cuenta from "./src/pantallas/Cuenta";
import Detalle from "./src/pantallas/Detalle";
import Ingreso from "./src/pantallas/Ingreso";
import Solicitudes from "./src/pantallas/Solicitudes";
import { ProveedorSesion, useSesion } from "./src/Sesion";
import { colores } from "./src/tema";

const Pila = createNativeStackNavigator();
const Pestanas = createBottomTabNavigator();

const tema = {
  ...DefaultTheme,
  colors: { ...DefaultTheme.colors, primary: colores.primario, background: colores.fondo, card: colores.superficie, text: colores.texto, border: colores.borde },
};

const opcionesCabecera = { headerStyle: { backgroundColor: colores.superficie }, headerTitleStyle: { fontWeight: "800", color: colores.texto }, headerTintColor: colores.primario };

function Principal() {
  const { usuario } = useSesion();
  const { noLeidas } = useAlertas();
  const cap = capacidades(usuario);
  return (
    <Pestanas.Navigator
      screenOptions={{
        ...opcionesCabecera,
        tabBarActiveTintColor: colores.primario,
        tabBarInactiveTintColor: colores.textoSuave,
        tabBarIconStyle: { display: "none" }, // sin íconos: la etiqueta basta y se lee mejor
        tabBarLabelStyle: { fontSize: 15, fontWeight: "700" },
        tabBarStyle: { minHeight: 56 },
      }}
    >
      {cap.verSolicitudes ? <Pestanas.Screen name="Solicitudes" component={Solicitudes} /> : null}
      {cap.recibirAlertas ? (
        // Sin íconos, un badge no tendría dónde anclarse: el conteo de alertas sin leer va en la etiqueta.
        <Pestanas.Screen
          name="Alertas"
          component={Alertas}
          options={{
            tabBarLabel: noLeidas > 0 ? `Alertas (${noLeidas})` : "Alertas",
            tabBarAccessibilityLabel: noLeidas > 0 ? `Alertas, ${noLeidas} sin leer` : "Alertas",
          }}
        />
      ) : null}
      <Pestanas.Screen name="Cuenta" component={Cuenta} />
    </Pestanas.Navigator>
  );
}

function Contenido() {
  const { fase, usuario } = useSesion();
  if (fase === "arrancando") return <Cargando texto="Abriendo SIRFA…" />;
  if (fase === "fuera") return <Ingreso />;

  const cap = capacidades(usuario);
  // Epidemiólogo: no tiene solicitudes ni alertas. Solo ve su cuenta, con el aviso de que su trabajo está en la web.
  if (!cap.verSolicitudes && !cap.recibirAlertas) {
    return (
      <NavigationContainer theme={tema}>
        <Pila.Navigator screenOptions={opcionesCabecera}>
          <Pila.Screen name="Cuenta" options={{ title: "SIRFA" }}>
            {() => <Cuenta sinAcceso />}
          </Pila.Screen>
        </Pila.Navigator>
      </NavigationContainer>
    );
  }

  return (
    <ProveedorAlertas habilitado={cap.recibirAlertas}>
      <NavigationContainer theme={tema}>
        <Pila.Navigator screenOptions={opcionesCabecera}>
          <Pila.Screen name="Principal" component={Principal} options={{ headerShown: false }} />
          <Pila.Screen name="Solicitud" component={Detalle} options={({ route }) => ({ title: route.params?.codigo ?? "Solicitud" })} />
        </Pila.Navigator>
      </NavigationContainer>
    </ProveedorAlertas>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <ProveedorSesion>
        <Contenido />
      </ProveedorSesion>
    </SafeAreaProvider>
  );
}
