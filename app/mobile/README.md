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

## Cómo ejecutarla

Requisitos: Node.js 20 o más, y el sistema SIRFA corriendo (`docker compose up -d` en la carpeta `app/`, que publica la API en el puerto 8000).

```bash
cd mobile
npm install
npm start
```

- **Teléfono con Expo Go** (Android): instalar Expo Go, escanear el código QR que muestra `npm start`, con el teléfono en la **misma red wifi** que el computador. La app intenta con la IP del computador que aparece en el QR (`http://<esa IP>:8000`); si no conecta, se corrige en «Servidor» (esa deducción automática aún no se probó en un teléfono). Si Windows pregunta por el cortafuegos, permitir el acceso en redes privadas.
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

29 pruebas con `node --test` (sin dependencias extra): el cliente de la API (token, renovación de sesión, 401 en el login frente a 401 con sesión, 404 de «sin recomendación», cortes por tiempo, errores de validación, escape de identificadores en la URL), los formatos de fecha (fechas sin zona horaria tratadas como UTC, igual que el servidor), el estado de cada solicitud, los filtros y los permisos por rol.

Lo que **no** cubren las pruebas automáticas es la interfaz: se verificó a mano en el navegador contra la API real (ingreso con error y con éxito, lista y filtros, detalle con recomendación, alertas con marca de leída confirmada en el servidor, cierre de sesión, y los roles clínico, microbiólogo y epidemiólogo). **Falta probarla en un teléfono o emulador Android.**

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
│   ├── componentes/ui.js   etiqueta, tarjeta, botón, avisos
│   ├── pantallas/          Ingreso, Solicitudes, Detalle, Alertas, Cuenta
│   └── tema.js             paleta, la misma de la web
└── tests/                  pruebas con node --test
```

## Pendiente

- Probar en un teléfono Android real o en un emulador.
- Íconos propios (hoy los de la plantilla de Expo) y modo oscuro.
- Notificaciones push (RF-66).
