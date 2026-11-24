@echo off
rem Lanzador de SIRFA con doble clic: enciende Docker Desktop si hace falta, levanta los contenedores y abre la web.
rem El proyecto se toma de la carpeta donde esta este archivo. Si Docker Desktop esta en otra carpeta, ajustar DOCKER_EXE.
title Iniciar SIRFA
set "APP=%~dp0"
set "DOCKER_EXE=C:\Program Files\Docker\Docker\Docker Desktop.exe"
set "INTENTOS=0"

rem Paso 1: docker info falla si el motor de Docker no esta encendido.
echo [1/4] Comprobando Docker...
docker info >nul 2>&1
if not errorlevel 1 goto docker_listo

rem Docker apagado: se abre Docker Desktop y se espera hasta 60 intentos de unos 3 segundos (unos 3 minutos).
echo Docker no esta corriendo. Abriendo Docker Desktop...
start "" "%DOCKER_EXE%"

rem Bucle de espera. ping -n 4 a 127.0.0.1 es la forma de dormir unos 3 segundos en un .bat (no existe sleep).
:esperar_docker
set /a INTENTOS+=1
if %INTENTOS% GTR 60 goto docker_fallo
ping -n 4 127.0.0.1 >nul
docker info >nul 2>&1
if errorlevel 1 goto esperar_docker

:docker_listo
echo [2/4] Docker listo.
rem Paso 3: cd /d tambien cambia de unidad de disco; si la carpeta no existe se salta a ruta_fallo.
rem docker compose up -d deja los contenedores corriendo en segundo plano.
echo [3/4] Levantando contenedores...
cd /d "%APP%" || goto ruta_fallo
docker compose up -d
if errorlevel 1 goto compose_fallo

rem Paso 4: se consulta /api/v1/salud hasta 30 veces, cada 2 segundos. curl -f falla si la respuesta es un error HTTP (por ejemplo 503).
echo [4/4] Esperando a que la API responda...
set "INTENTOS=0"

:esperar_api
set /a INTENTOS+=1
if %INTENTOS% GTR 30 goto api_fallo
curl -s -f http://localhost:8000/api/v1/salud >nul 2>&1
if not errorlevel 1 goto api_lista
ping -n 3 127.0.0.1 >nul
goto esperar_api

rem Todo listo: se abre la web en el navegador predeterminado.
:api_lista
echo.
echo SIRFA lista en http://localhost:8000/
start "" http://localhost:8000/
goto fin

rem Mensajes de error: cada etiqueta explica que fallo y que hacer. Todas terminan en :fin.
:docker_fallo
echo.
echo Docker no respondio en 3 minutos. Abre Docker Desktop a mano y vuelve a ejecutar este archivo.
goto fin

:ruta_fallo
echo.
echo No encuentro la carpeta %APP%
goto fin

:compose_fallo
echo.
echo "docker compose up -d" fallo. Revisa el mensaje de arriba.
goto fin

:api_fallo
echo.
echo Los contenedores subieron pero la API no responde en http://localhost:8000/. Prueba: docker compose logs api
goto fin

rem pause deja la ventana abierta para poder leer los mensajes.
:fin
echo.
pause