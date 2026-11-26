# SIRFA · App móvil

Aplicación móvil complementaria de SIRFA (React Native con Expo). Es de **solo consulta**: sirve para ver el estado de las solicitudes, leer la recomendación emitida y revisar las alertas. No carga genomas, no valida ni cambia nada; eso se hace en la plataforma web.

> ⚠️ SIRFA no diagnostica ni prescribe. Toda recomendación es una hipótesis priorizada que debe ensayarse en laboratorio antes de cualquier uso clínico. La app muestra esta advertencia sobre cada recomendación.

## Qué hace

| Pantalla | Requisito | Detalle |
|---|---|---|
| Ingreso | RF-61 | Mismas credenciales que la web. El token JWT queda en el almacén seguro del teléfono (Keystore en Android). Tras 5 intentos fallidos el servidor bloquea la cuenta 15 minutos |
| Solicitudes | RF-62 | Las que el servidor deja ver a tu rol, con su estado en color y en texto; filtros por grupo de estado; se actualiza al volver a la pantalla o al deslizar hacia abajo |
| Detalle y recomendación | RF-63, RF-45 | Advertencia primero, luego versión, validador, modelo, candidatos por orden de prioridad con su puntaje y el resultado del ensayo de laboratorio; aislado, análisis del genoma e historial de estados |
| Alertas | RF-64, RF-65 | Bandeja con marca de leída (tocar una alerta la marca y abre su solicitud) y «Marcar todas»; el conteo de no leídas va en la pestaña |
| Cuenta | RF-02 | Datos de la cuenta y **cerrar sesión**, que revoca el token en el servidor |

Qué ve cada rol (lo decide el servidor, la app solo lo refleja con los `permisos` que recibe al ingresar):

- **Técnico, microbiólogo, clínico:** solicitudes y alertas.
- **Administrador:** solicitudes, sin alertas.
- **Epidemiólogo:** nada que consultar en la app; solo ve su cuenta, con el aviso de que su trabajo (el tablero) está en la web.

**No incluido:** notificaciones push (RF-66, prioridad baja: exige un servicio externo). En su lugar la bandeja se actualiza al volver a la app y cada minuto mientras está abierta.

## Cómo se ve

El diseño busca que cada pantalla se entienda sin leer todo el texto: colores suaves, un ícono por cada estado y gráficos que muestran lo que ocurre.

- **Recorrido por etapas.** Cada solicitud muestra sus cinco etapas (registro, análisis, predicción, validación y emisión): lo hecho en verde con una marca, la etapa actual con un anillo y su color, y lo que falta en gris. En la lista es una barra de cinco segmentos; en el detalle, el recorrido completo con su nombre. Si la solicitud se detuvo (rechazada, anulada o con error) no hay recorrido y se muestra el ícono del estado con su motivo.
- **Cuadros de resumen.** En la lista, cuatro cuadros con un número (todas, en curso, emitidas y sin resultado) que además filtran al tocarlos.
- **Barra de puntaje.** Cada fago candidato trae una barra de 0 a 1 con el puntaje del modelo, con la aclaración de que sirve para ordenar y no es una probabilidad. El primero va destacado.
- **Íconos con texto.** Los íconos (MaterialCommunityIcons, vía `@expo/vector-icons`) acompañan al texto, nunca lo reemplazan, y el lector de pantalla los ignora; el color tampoco va solo.
- **Línea de tiempo** del historial de cada solicitud, **globo rojo** con el número de alertas sin leer sobre la pestaña, y pantallas vacías con un dibujo y qué hacer.

La paleta y los íconos están en `src/tema.js` y `src/logica/estados.js`; los gráficos, en `src/componentes/ui.js`.

## Cómo ejecutarla

Requisitos: Node.js 20 o más, y el sistema SIRFA corriendo (`docker compose up -d` en la carpeta `app/`, que publica la API en el puerto 8000).

```bash
cd mobile
npm install
npm start
```

- **Teléfono con Expo Go** (Android): instalar Expo Go, escanear el código QR que muestra `npm start`, con el teléfono en la **misma red wifi** que el computador. La app intenta con la IP del computador que aparece en el QR (`http://<esa IP>:8000`); si no conecta, se corrige en «Servidor» (esa deducción automática funcionó en los teléfonos Android donde se probó). Si Windows pregunta por el cortafuegos, permitir el acceso en redes privadas.
- **Emulador de Android:** `npm run android`. El computador se ve como `http://10.0.2.2:8000`, que es la dirección que usa por defecto.
- **Otra dirección:** en la pantalla de ingreso, tocar «Servidor» y escribirla. Se recuerda para la próxima vez.

Las cuentas de demostración las crea `docker compose exec api python -m app.sembrar_usuarios` y sus contraseñas quedan en `data/credenciales_demo.txt`.

> La conexión de desarrollo es HTTP sin cifrar dentro de la red local. Fuera de ella la API debe estar detrás de HTTPS. Una app compilada (no Expo Go) también necesita HTTPS, porque Android bloquea HTTP en texto plano por defecto.

### Vista en el navegador (solo para desarrollo)

`npm run web` abre la app en el navegador. El navegador bloquea las llamadas a otro origen (la API no define CORS), así que sirve para ver el diseño pero no para iniciar sesión, salvo que la página y la API compartan origen (por ejemplo, con un proxy que reenvíe `/api` al puerto 8000). Así se verificó el primer corte.

## Pruebas

```bash
npm test
```

38 pruebas con `node --test` (sin dependencias extra): el recorrido por etapas, los íconos y la barra de puntaje (lo que se dibuja sale de funciones puras), el cliente de la API (token, renovación de sesión, 401 en el login frente a 401 con sesión, 404 de «sin recomendación», cortes por tiempo, errores de validación, escape de identificadores en la URL), los formatos de fecha (fechas sin zona horaria tratadas como UTC, igual que el servidor), el estado de cada solicitud, los filtros y los permisos por rol.

Lo que **no** cubren las pruebas automáticas es la interfaz: se verificó a mano contra la API real, primero en el navegador (18-11-2026) y después en teléfonos Android con Expo Go (25-11-2026). En ambos se recorrió el ingreso con error y con éxito, la lista y sus filtros, el detalle con la recomendación y su advertencia, las alertas con marca de leída, el cierre de sesión y lo que ve cada rol. No hay captura automatizada de esos recorridos: la prueba en el teléfono fue manual. Esa prueba fue con el diseño anterior; el rediseño visual de este mismo día (colores, íconos, recorrido por etapas) no cambió la lógica y se revisó en el navegador (en 375 y 360 px de ancho, con estados de prueba) y compilando el paquete de Android, pero falta repetir el recorrido en el teléfono.

## Estructura

```
mobile/
├── App.js                  sesión, pestañas y pila de navegación
├── src/
│   ├── api/cliente.js      cliente REST (sin dependencias de React Native; es lo que se prueba)
│   ├── logica/             estados, roles y filtros; formatos de fecha y número
│   ├── Sesion.js           quién está conectado y contra qué servidor
│   ├── AlertasContexto.js  bandeja de alertas compartida entre la pestaña y su pantalla
│   ├── almacen.js          token y servidor en el almacén seguro
│   ├── componentes/ui.js   etiqueta, tarjeta, botón, avisos y gráficos (recorrido, barra de puntaje)
│   ├── pantallas/          Ingreso, Solicitudes, Detalle, Alertas, Cuenta
│   └── tema.js             paleta y tonos de color
└── tests/                  pruebas con node --test
```

## Pendiente

- Ícono propio de la aplicación (hoy el de la plantilla de Expo) y modo oscuro.
- Repetir en el teléfono el recorrido con el diseño nuevo.
- Notificaciones push (RF-66).
