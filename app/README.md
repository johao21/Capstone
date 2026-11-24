# SIRFA — Sistema de Recomendación de Fagos frente a Antibiorresistencia

Proyecto de título — Capstone PTY4614 / APT122, Ingeniería en Informática, Duoc UC sede San Joaquín, segundo semestre 2026.

> **Estado al 18-11-2026 (semana 16).** Funciona el ciclo completo: un técnico registra el genoma de un aislado de *Klebsiella pneumoniae*; el pipeline lo analiza (calidad, especie, locus K, genes); el modelo (XGBoost sobre embeddings ESM-2, con explicación SHAP) ordena los fagos aprobados del banco; un microbiólogo valida y emite la recomendación; el técnico y el clínico reciben la alerta. Hay inicio de sesión con JWT, permisos por rol, auditoría de solo adición con hashes encadenados, y tablero. **Límites que importan:** el modelo se entrenó con 200 cepas y 105 fagos del conjunto público PhageHostLearn y, ante un tipo de locus K que no vio, no supera a la línea base que ignora al hospedador (ver «Calidad del modelo»); la app móvil es un primer corte de consulta y alertas (verificada en el navegador, no en un teléfono, y sin notificaciones push); la web son módulos JavaScript sin compilar, no Next.js. Toda recomendación es una hipótesis a ensayar en laboratorio.

---

## Descripción

**¿Qué problema resuelve?**

Cuando un paciente contrae una infección por una bacteria multirresistente, el antibiograma tarda días y en los casos más graves concluye que no queda ningún antibiótico efectivo. La alternativa emergente es la **terapia fágica**: usar bacteriófagos —virus que infectan y destruyen bacterias, sin afectar a las células humanas— como tratamiento.

El obstáculo es que cada fago es extremadamente específico: infecta solo una o pocas cepas bacterianas concretas. Determinar cuál de los cientos de fagos conocidos sirve para *ese* aislado en particular requiere hoy ensayar en laboratorio uno por uno, con el costo y el tiempo que eso implica en un contexto clínico donde el paciente no puede esperar.

**¿Qué hace SIRFA?**

Es una plataforma web que prioriza computacionalmente los fagos candidatos antes del ensayo de laboratorio:

1. Un laboratorio clínico registra un aislado bacteriano resistente y carga su genoma.
2. Un pipeline bioinformático lo procesa: control de calidad, identificación de especie y tipificación.
3. Un modelo de aprendizaje automático predice qué fagos de un banco curado tienen probabilidad de infectar esa cepa, y entrega una lista priorizada con explicación de los factores que sustentan cada predicción.
4. Un microbiólogo revisa y valida la recomendación antes de que se emita.
5. El clínico solicitante la consulta desde la web.
6. Un tablero muestra la cobertura del banco, las brechas terapéuticas y la evolución de la resistencia.

Todo el ciclo queda trazado con **control de acceso por rol** y **registro de auditoría inmutable**, por tratarse de datos de origen clínico.

**¿A quién va dirigido?**

| Rol | Uso |
|---|---|
| Técnico de laboratorio | Registra aislados y carga genomas |
| Microbiólogo / curador | Cura el banco de fagos, valida predicciones, emite recomendaciones |
| Clínico solicitante | Consulta recomendaciones y recibe alertas (principal usuario móvil) |
| Epidemiólogo | Consume el tablero agregado de cobertura y tendencias |
| Administrador | Gestiona usuarios, roles y revisa la auditoría |

**Alcance del patógeno:** el foco principal es *Klebsiella pneumoniae*, por ser el único patógeno con un conjunto de datos público de interacciones fago–hospedador verificadas experimentalmente a nivel de cepa, y a la vez el dominante en la vigilancia chilena de carbapenemasas (58% de 489 aislados productores procesados por el ISP entre 2014 y 2017). *Pseudomonas aeruginosa* queda como extensión secundaria.

> ⚠️ **SIRFA no diagnostica ni prescribe.** Toda salida del sistema es una hipótesis priorizada a ensayar, no un resultado validado. Ninguna recomendación es aplicable clínicamente sin validación experimental previa en laboratorio. El proyecto es enteramente computacional: no incluye trabajo de laboratorio húmedo ni genera secuencias virales nuevas.

---

## Estado actual

| Componente | Estado | Detalle |
|---|---|---|
| Banco de fagos | Construido | 200 fagos de *Klebsiella* de INPHARED (abril 2026) y 105 de PhageHostLearn con sus 10.891 interacciones conocidas con 215 cepas. La curaduría (aprobar, descartar, editar) es del microbiólogo; solo los aprobados participan en las predicciones |
| Pipeline genómico | Construido | Validación del FASTA, calidad, especie con Mash (13 referencias), locus K con Kaptive 3.3.2 y genes con Prodigal 2.6.3 |
| Cola de trabajos | Construido | Tabla en PostgreSQL con `FOR UPDATE SKIP LOCKED` (probado con 8 workers contra PostgreSQL real), 3 intentos y estado `error`; dos workers: `worker-pipeline` y `worker-prediction` |
| Modelo de predicción | Construido | XGBoost sobre embeddings ESM-2 (RBP del fago + locus K del hospedador), probabilidades calibradas (Platt), SHAP por candidato y marca de baja confianza. Ver «Calidad del modelo» |
| API REST | Construida | 47 operaciones: acceso, usuarios, solicitudes, validación y emisión, banco, modelo, tablero, alertas y auditoría |
| Autenticación, roles y auditoría | Construido | JWT (sesión deslizante y cierre de sesión), 5 roles con alcance de datos, bloqueo tras 5 intentos fallidos, Argon2; auditoría con disparador de solo adición en PostgreSQL y cadena de hashes verificable |
| Web | Construida | HTML, CSS y módulos JavaScript sin compilar, servidos por la API, con pantallas por rol; no es la web con Next.js del diseño |
| Tablero | Construido | Cobertura del banco, brechas terapéuticas y tendencias, con supresión de grupos pequeños y exportación a CSV |
| App móvil | Primer corte | Hecha desde cero en la semana 15 (React Native con Expo): ingreso, lista de solicitudes, detalle con la recomendación emitida en solo lectura y bandeja de alertas. Verificada en el navegador contra la API real; **sin probar todavía en un teléfono o emulador Android** y sin notificaciones push (RF-66). Ver [mobile/README.md](mobile/README.md) |
| Pruebas | 212 pasan + 29 de la app móvil | pytest dentro del contenedor: 211 con SQLite en memoria y una de concurrencia contra PostgreSQL real (se activa con `SIRFA_TEST_POSTGRES_DB`); además, un recorrido completo contra el sistema real. La app móvil tiene 29 pruebas de su lógica (`npm test` en `mobile/`); su interfaz no tiene pruebas automáticas. La integración continua (`.github/workflows/ci.yml`) corre `pytest` y `npm test` en cada push; se verificó en local con una instalación limpia, pero aún no se ha ejecutado en GitHub |

Las cuentas son de demostración: el sistema no opera con pacientes ni datos identificables.

### Calidad del modelo

Validación cruzada de 5 pliegues sobre 10,006 pares cepa–fago ensayados (333 positivos, 3 %). «Top-5» es la proporción de cepas para las que alguno de los 5 primeros fagos sí las infecta, entre los fagos ensayados con esa cepa. La línea base ordena los fagos solo por cuántas cepas infectan, sin mirar al hospedador.

| Escenario | AUC | Top-5 | Línea base (AUC / top-5) | Al azar (top-5) |
|---|---|---|---|---|
| Aislado de un tipo de locus K **no visto** | 0,62 | 50 % | 0,60 / 52 % | 22 % |
| Cepa nueva con tipo de locus K representado | 0,76 | 79 % | 0,67 / 60 % | 22 % |

Con un tipo K no visto el modelo no supera a la línea base; con uno representado sí. Por eso SIRFA compara el locus del aislado con el de las cepas de entrenamiento (BLAST) y marca de **baja confianza** el resultado cuando no hay una cepa parecida (similitud menor a 90 %). Se probó reducir los embeddings con PCA y agregar el producto RBP × locus: no mejoró de forma material. Los embeddings ESM-2 vienen precalculados con el conjunto; no se calculan para fagos nuevos, así que solo se ordenan los 105 fagos del conjunto. Referencia: Boeckaerts et al. (2024), Nature Communications.

---

## Tecnologías

| Área | Se usa | Planificado en el diseño |
|---|---|---|
| Backend y API | Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · Pydantic · PyJWT · argon2-cffi | — |
| Bioinformática | Prodigal · Mash · Kaptive · Biopython · BLAST+ (parecido del locus K) | DIAMOND, minimap2 (instalado, sin uso) |
| Aprendizaje automático | XGBoost · SHAP · scikit-learn · NumPy · embeddings ESM-2 del conjunto PhageHostLearn | Calcular ESM-2 para fagos y aislados nuevos |
| Bases de datos | PostgreSQL 16 (dominio, cola de trabajos y auditoría) · MongoDB 7 (salidas crudas del análisis) | Caché de representaciones vectoriales |
| Frontend | HTML · CSS · JavaScript (módulos ES, sin compilar) | Next.js · Recharts |
| Aplicación móvil | React Native · Expo (SDK 58) · React Navigation · expo-secure-store | Notificaciones push (RF-66) |
| Seguridad | JWT HS256 · Argon2id · permisos por rol en el servidor · auditoría con hashes encadenados y disparador de solo adición | HTTPS (fuera del entorno local), GitHub Actions |
| Infraestructura y calidad | Docker · docker compose · pytest · GitHub Actions (integración continua) | Playwright |

---

## Arquitectura

**Hoy**

```
                                                  ┌─► Mash · Kaptive · Prodigal
  Navegador ──► API (FastAPI, :8000) ──► PostgreSQL ◄── worker-pipeline ──► MongoDB (salidas crudas)
  App móvil ──►  │  JWT · roles · auditoría   │  (dominio, cola, auditoría)
  (Expo, HTTP)   │                            └◄── worker-prediction ──► BLAST + XGBoost + SHAP (ml/models)
                └─ sirve la web y /api/v1
```

**Objetivo (Documento de Diseño)**

```
                         ┌──────────────┐   ┌──────────────┐
                         │   Web (Next) │   │ Móvil (RN)   │
                         └──────┬───────┘   └──────┬───────┘
                                └────────┬─────────┘
                                         │ HTTPS / JWT
                                ┌────────▼─────────┐
                                │   API (FastAPI)  │
                                │  AuthN · RBAC    │
                                │    Auditoría     │
                                └────────┬─────────┘
                  ┌──────────────────────┼──────────────────────┐
                  │                      │                      │
        ┌─────────▼────────┐   ┌─────────▼────────┐   ┌─────────▼────────┐
        │ Pipeline         │   │ Motor de         │   │ Servicio de      │
        │ bioinformático   │   │ predicción (ML)  │   │ analítica (BI)   │
        │ QC · tipificación│   │ ESM-2 + XGBoost  │   │ cobertura·brechas│
        └─────────┬────────┘   └─────────┬────────┘   └─────────┬────────┘
                  └──────────────────────┼──────────────────────┘
                             ┌───────────┴───────────┐
                    ┌────────▼────────┐    ┌─────────▼────────┐
                    │   PostgreSQL    │    │     MongoDB      │
                    │ dominio + audit │    │ análisis · caché │
                    └─────────────────┘    └──────────────────┘

  Ingesta externa (batch): INPHARED · PhageScope · MVP · NCBI Virus ──► banco de fagos
```

Los diagramas detallados (componentes, casos de uso, clases, secuencia) y el modelo entidad-relación están en el Documento de Diseño del curso.

---

## Estructura del repositorio

```
app/
├── backend/            API: app/ (código), migrations/ (tablas), tests/, Dockerfile
├── pipeline/           análisis genómico, predicción y carga del banco de fagos; worker
├── ml/                 modelo: entrenamiento, validación y predicción; models/ guarda los artefactos
├── frontend/           web: index.html, estilos.css y js/ (módulos por pantalla)
├── mobile/             app móvil (React Native con Expo): App.js, src/ y tests/; ver mobile/README.md
├── data/               genomas, referencias y conjunto PhageHostLearn; no se versiona
├── docs/               manual técnico y de despliegue, guías de demostración y diagramas del diseño (ver docs/README.md)
├── docker-compose.yml  5 servicios: postgres, mongo, api, worker-pipeline y worker-prediction
├── pytest.ini          configuración de las pruebas
└── .env.example        variables de entorno, sin secretos
```

---

## Ejecución local

Este código vive en la carpeta `app/` del repositorio [Capstone](https://github.com/johao21/Capstone); los documentos del curso (SRS, diseño, informes) están en `Fase 1/`, `Fase 2/` y `Fase 3/`. Los comandos de abajo se ejecutan desde `app/`.

Esta sección resume lo esencial. El procedimiento completo, con servicios y puertos, variables de entorno, operación, respaldos y solución de problemas, está en el [Manual técnico y de despliegue](docs/MANUAL_TECNICO.md).

### Requisitos previos

- Docker Desktop (con Docker Compose)
- Conexión a internet la primera vez, para descargar imágenes y datos públicos

### Pasos

```bash
cp .env.example .env
docker compose up --build -d
```

Servicios expuestos:

| Servicio | URL |
|---|---|
| Aplicación web | http://localhost:8000/ |
| API (documentación OpenAPI) | http://localhost:8000/docs |
| Estado de las bases | http://localhost:8000/api/v1/salud |

PostgreSQL y MongoDB no publican puertos: solo los usan los otros contenedores.

### Poblar el banco de fagos y las referencias de especie

```bash
docker compose exec api python -m pipeline.seed_phage_bank --descargar --hospedador Klebsiella --limite 200
```

```bash
docker compose exec api python -m pipeline.referencias construir
```

Sin las referencias, el pipeline no verifica la especie y usa la declarada.

### Cuentas de demostración, banco y modelo

```bash
docker compose exec api python -m app.sembrar_usuarios
```

Crea una cuenta por rol (técnico, microbiólogo, clínico, epidemiólogo y administrador) con contraseñas al azar que quedan en `data/credenciales_demo.txt` (no se versiona). Para tener fagos con los que predecir, se carga el conjunto PhageHostLearn y se entrena el modelo:

```bash
mkdir -p data/raw/phagehostlearn   # descargar allí los 7 archivos del registro de Zenodo 11061100 (ver ml/datos.py)
docker compose run --rm worker-prediction python -m ml.entrenar --registrar
```

Tarda unos 15 minutos (validación cruzada) y deja el modelo en `ml/models/`. Con `--sin-entrenar` solo registra los artefactos ya guardados. Después, el microbiólogo aprueba los fagos en «Banco de fagos» (hay «Aprobar todos los pendientes de la búsqueda»): sin fagos aprobados la predicción termina en error con ese motivo.

### Usarlo

Abrir http://localhost:8000/ e ingresar. Cada rol ve lo suyo: el técnico registra y sigue sus solicitudes; el microbiólogo valida desde la bandeja y cura el banco; el clínico consulta las de su centro; el epidemiólogo ve el tablero; el administrador gestiona usuarios y revisa la auditoría. Subir, por ejemplo, `data/genomas/HS11286.fna.gz` y esperar un minuto hasta «Predicción lista». La guía paso a paso, con la misma prueba por la API, está en [docs/demo_avance.md](docs/demo_avance.md).

### App móvil

Con el sistema corriendo, `cd mobile && npm install && npm start` y abrir con Expo Go en un teléfono Android de la misma red. Detalle, cuentas por rol y limitaciones en [mobile/README.md](mobile/README.md).

### Ejecutar las pruebas

```bash
docker compose exec api pytest
```

La lógica de la app móvil se prueba aparte: `cd mobile && npm test`.

> El archivo `.env.example` documenta las variables de entorno. No se versiona ningún `.env` real ni credencial.

---

## Metodología de trabajo

**Tradicional en cascada — modelo secuencial por etapas, desarrollador único.**

Se elige porque los requisitos del sistema pueden especificarse por completo desde el inicio y porque el curso exige artefactos formales de ingeniería de software (especificación de requisitos, documento de diseño, plan de pruebas con evidencias y manual técnico), cuyo orden natural es el de las etapas de este modelo. Cada etapa termina en una **puerta de control** con un entregable aprobado antes de iniciar la siguiente; los hitos sumativos del curso (Informe de Avance en la semana 10, Informe Final en la semana 15) coinciden con el cierre de etapas.

| Etapa | Semanas | Entregable | Puerta de control |
|---|---|---|---|
| 1. Análisis | 5–6 | Especificación de Requisitos de Software (SRS) | SRS aprobada; cambios posteriores pasan por control de cambios |
| 2. Diseño | 6–7 | Documento de Diseño: arquitectura, modelo ER, esquema documental, UML y plan de pruebas | Línea base de diseño congelada |
| 3. Construcción | 8–14 | Sistema integrado en Docker: pipeline y banco de fagos, modelo predictivo, plataforma web y app móvil | Componentes integrados sin pasos manuales no documentados |
| 4. Pruebas | 15 | Plan de Pruebas con evidencias (unitarias, integración, E2E, rendimiento y seguridad) | Defectos críticos corregidos o documentados |
| 5. Despliegue y cierre | 16–18 | Manual técnico y de despliegue, README final, presentación ante comisión | Sistema desplegable y documentado |

### Hoja de ruta (tareas específicas)

El estado es el del 02-11-2026 (semana 13); las filas 1.x a 3.6 son las del Informe de Avance.

| Tarea | Semanas | OE | Estado |
|---|---|---|---|
| 1.1 Repositorio público, estructura del proyecto y entorno Docker base | 5 | OE1 | Completado, con retraso: el código se publicó en la semana 16 (ver «Historial del repositorio») |
| 1.2 Levantamiento de requisitos y definición de roles y permisos | 5–6 | OE1 | Completado, con retraso |
| 1.3 SRS: requisitos funcionales, no funcionales e historias por rol | 5–6 | OE1 | Completado, con retraso |
| 2.1 Arquitectura y diagrama de componentes | 6 | OE1 | Completado, con retraso |
| 2.2 Modelo de datos: ER de PostgreSQL y esquema documental de MongoDB | 6–7 | OE1 | Completado, con retraso |
| 2.3 Diagramas UML: casos de uso, clases y secuencia | 7 | OE1 | Completado, con retraso |
| 2.4 Documento de Diseño y plan de pruebas | 7 | OE1 | Completado, con retraso |
| 3.1 Descarga y normalización de genomas de fagos (INPHARED, PhageScope) | 8 | OE2 | En curso: tabla de metadatos y 200 genomas; faltan PhageScope y MVP |
| 3.2 Ingesta de aislados: validación de formato y control de calidad | 8 | OE2 | Completado |
| 3.3 Identificación de especie y tipificación del locus K (Kaptive) | 9 | OE2 | Completado |
| 3.4 Predicción de genes (Prodigal) y proteínas de unión al receptor | 9 | OE2 | En curso: faltan las proteínas de unión |
| 3.5 Carga del banco curado y empaquetado en Docker | 9–10 | OE2 | En curso: el banco aún no se cura |
| 3.6 Integración del pipeline e Informe de Avance | 10 | OE2 | En curso |
| 3.7 Representaciones vectoriales ESM-2 de fagos y hospedadores | 11 | OE3 | Parcial: se usan los embeddings ESM-2 precalculados del conjunto PhageHostLearn; no se calculan para fagos ni aislados nuevos |
| 3.8 Entrenamiento del clasificador XGBoost con validación cruzada | 11–12 | OE3 | Completado: XGBoost con validación cruzada agrupada por tipo de locus K y por cepa |
| 3.9 Evaluación (top-5, AUC) y explicabilidad SHAP | 12 | OE3 | Completado: AUC y top-5 medidos (ver «Calidad del modelo») y SHAP en cada candidato |
| 3.10 API: autenticación JWT, RBAC y máquina de estados de solicitudes | 13 | OE4 | Completado: JWT, permisos por rol en el servidor y máquina de estados de solicitudes |
| 3.11 Registro de auditoría inmutable e integración del modelo | 13 | OE4 | Completado: auditoría de solo adición con hashes encadenados e integración del modelo |
| 3.12 Interfaz web por rol | 13–14 | OE4 | Completado: web por rol con módulos JavaScript (no Next.js) |
| 3.13 Tablero de cobertura, brechas terapéuticas y tendencias | 14 | OE4 | Completado: cobertura, brechas y tendencias, con supresión de grupos pequeños |
| 3.14 Aplicación móvil: consulta de solicitudes y alertas | 14 | OE5 | Primer corte en la semana 15 (una semana después de lo planificado): RF-61 a RF-65 construidos, sin push (RF-66); falta probarla en Android |
| 4.1 Pruebas unitarias y de integración | 15 | OE5 | En curso: 212 pruebas automáticas |
| 4.2 Pruebas de extremo a extremo y de rendimiento | 15 | OE5 | Parcial: un recorrido completo contra el sistema real; sin pruebas de rendimiento ni Playwright |
| 4.3 Pruebas de seguridad: RBAC y completitud de la auditoría | 15 | OE5 | Parcial: pruebas de permisos por rol, alcance por centro y completitud de la auditoría |
| 4.4 Plan de Pruebas con evidencias e Informe Final | 15 | OE5 | No iniciado |
| 5.1 Corrección de defectos y retroalimentación | 16 | OE5 | No iniciado |
| 5.2 Manual técnico y de despliegue; README final | 16 | OE5 | En curso: manual v1.0 escrito el 23-11 (docs/MANUAL_TECNICO.md); falta el README final al publicar el código |
| 5.3 Preparación de la presentación y la demostración | 17 | Todos | No iniciado |
| 5.4 Presentación final ante comisión | 17–18 | Todos | No iniciado |

---

## Historial del repositorio

El código se desarrolló entre el 01-09 y el 18-11-2026 en una carpeta local, con un único commit inicial («Estructura inicial del proyecto SIRFA», 01-09) que no se conservó en este repositorio. Se publicó aquí en la semana 16, al final de ese desarrollo y en commits por componente. La integración continua (GitHub Actions) está en `.github/workflows/ci.yml`, en la raíz del repositorio, y aún no se ha ejecutado en GitHub. **Las fechas de esos commits son las de la publicación; no reflejan cuándo se escribió cada parte.** La cronología real de las etapas (plan contra lo ocurrido) está en el Informe de Avance y en el Informe Final, y el estado del control de versiones durante el desarrollo se explica en el anexo F de este último (repositorio de documentos).

---

## Equipo

| Responsable | Rol | Contacto |
|---|---|---|
| Johao Ramírez | Análisis, arquitectura, desarrollo, datos, pruebas y documentación | — |

Proyecto individual, con desvinculación de equipo autorizada por el docente de la asignatura.

---

## Fuentes de datos

Todas públicas, gratuitas y des-identificadas:

| Fuente | Uso | Estado |
|---|---|---|
| [INPHARED](https://millardlab.org/bacteriophage-genomics/inphared/) | Genomas completos de fagos curados con metadatos de calidad | Cargada: tabla de metadatos de abril 2026 |
| [PhageScope](https://academic.oup.com/nar/article/52/D1/D756/7334092) | Anotación de ciclo de vida, rango de hospedador y taxonomía | Pendiente |
| [MVP](https://academic.oup.com/nar/article/46/D1/D700/4643372) | Interacciones fago–microbio curadas | Pendiente |
| [Conjunto de datos PhageHostLearn](https://www.nature.com/articles/s41467-024-48675-6) | Interacciones verificadas en *K. pneumoniae* (entrenamiento y validación) | Pendiente |
| NCBI Virus / RefSeq viral | Secuencias virales de referencia | Pendiente |
| BV-BRC | Genomas bacterianos y perfiles de resistencia | Pendiente |
| NCBI (genomas) | 13 genomas bacterianos de referencia de especie, genomas de prueba y los 200 genomas de los fagos del banco | Descargada |

## Referencias

- Boeckaerts, D. et al. (2024). *Prediction of Klebsiella phage-host specificity at the strain level*. Nature Communications. https://www.nature.com/articles/s41467-024-48675-6
- Cook, R. et al. (2026). *Bacteriophage genomics: What has five years of INPHARED taught us?* bioRxiv. https://www.biorxiv.org/content/10.64898/2026.05.06.722914v1
- Wang, R. et al. (2024). *PhageScope: a well-annotated bacteriophage database*. Nucleic Acids Research. https://academic.oup.com/nar/article/52/D1/D756/7334092
- Gao, N. et al. (2018). *MVP: a microbe–phage interaction database*. Nucleic Acids Research. https://academic.oup.com/nar/article/46/D1/D700/4643372
- MINSAL (2021). *Plan Nacional Contra la Resistencia a los Antimicrobianos, Chile 2021–2025*. https://diprece.minsal.cl/wp-content/uploads/2021/10/Plan-Nacional-Contra-la-Resistencia-a-los-Antimicrobianos-Chile-2021-2025.pdf
