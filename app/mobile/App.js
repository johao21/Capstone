// Raíz de la app: decide qué se ve según la sesión y arma la navegación.
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { DefaultTheme, NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { ProveedorAlertas, useAlertas } from "./src/AlertasContexto";
import { Cargando, Icono } from "./src/componentes/ui";
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

// Barra de arriba en el verde de la marca, con texto blanco.
const opcionesCabecera = { headerStyle: { backgroundColor: colores.primario }, headerTitleStyle: { fontWeight: "800", color: colores.primarioTexto }, headerTintColor: colores.primarioTexto };

const icono = (nombre) => ({ color }) => <Icono nombre={nombre} tamano={26} color={color} />;

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
        tabBarLabelStyle: { fontSize: 13, fontWeight: "700" },
        tabBarStyle: { minHeight: 64, paddingTop: 4 },
        tabBarBadgeStyle: { backgroundColor: colores.error, color: colores.primarioTexto, fontWeight: "800" },
      }}
    >
      {cap.verSolicitudes ? <Pestanas.Screen name="Solicitudes" component={Solicitudes} options={{ tabBarIcon: icono("clipboard-list-outline") }} /> : null}
      {cap.recibirAlertas ? (
        // El conteo de alertas sin leer va como globo rojo sobre el ícono.
        <Pestanas.Screen
          name="Alertas"
          component={Alertas}
          options={{
            tabBarIcon: icono("bell-outline"),
            tabBarBadge: noLeidas > 0 ? noLeidas : undefined,
            tabBarAccessibilityLabel: noLeidas > 0 ? `Alertas, ${noLeidas} sin leer` : "Alertas",
          }}
        />
      ) : null}
      <Pestanas.Screen name="Cuenta" component={Cuenta} options={{ tabBarIcon: icono("account-circle-outline") }} />
    </Pestanas.Navigator>
  );
}

function Contenido() {
  const { fase, usuario } = useSesion();
  // Dentro, la barra de arriba es verde (íconos blancos); en el ingreso y al arrancar el fondo es claro (íconos oscuros).
  const barra = <StatusBar style={fase === "dentro" ? "light" : "dark"} />;
  if (fase === "arrancando") return <>{barra}<Cargando texto="Abriendo SIRFA…" /></>;
  if (fase === "fuera") return <>{barra}<Ingreso /></>;

  const cap = capacidades(usuario);
  // Epidemiólogo: no tiene solicitudes ni alertas. Solo ve su cuenta, con el aviso de que su trabajo está en la web.
  if (!cap.verSolicitudes && !cap.recibirAlertas) {
    return (
      <>
        {barra}
        <NavigationContainer theme={tema}>
          <Pila.Navigator screenOptions={opcionesCabecera}>
            <Pila.Screen name="Cuenta" options={{ title: "SIRFA" }}>
              {() => <Cuenta sinAcceso />}
            </Pila.Screen>
          </Pila.Navigator>
        </NavigationContainer>
      </>
    );
  }

  return (
    <ProveedorAlertas habilitado={cap.recibirAlertas}>
      {barra}
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
      <ProveedorSesion>
        <Contenido />
      </ProveedorSesion>
    </SafeAreaProvider>
  );
}
