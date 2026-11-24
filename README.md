# Capstone — SIRFA

**SIRFA** (Sistema de Recomendación de Fagos frente a Antibiorresistencia) es el proyecto de título de Johao Ramírez, Ingeniería en Informática, Duoc UC sede San Joaquín (Capstone PTY4614 / APT122, segundo semestre 2026). Este repositorio contiene el código del sistema (carpeta `app/`) y los entregables y la documentación del curso (carpetas `Fase 1/`, `Fase 2/` y `Fase 3/`).

## Descripción

**¿Qué hace?** SIRFA es una plataforma web que apoya la selección de bacteriófagos frente a infecciones causadas por bacterias multirresistentes a antibióticos. Un laboratorio clínico registra un aislado resistente y carga su genoma; un pipeline lo procesa (control de calidad, especie, tipificación del locus K y predicción de genes); un modelo de aprendizaje automático predice qué fagos de un banco curado tienen probabilidad de infectarlo y entrega una lista priorizada con la explicación de cada puntaje; y un microbiólogo valida la recomendación antes de emitirla. Todo el ciclo queda trazado con control de acceso por rol y un registro de auditoría de solo adición, y un tablero muestra la cobertura del banco y las brechas terapéuticas. Una app móvil complementaria permite consultar solicitudes, recomendaciones emitidas y alertas.

**¿A quién va dirigido?** A cinco roles: técnico de laboratorio, microbiólogo o curador, clínico solicitante, epidemiólogo y administrador.

**¿Qué problema resuelve?** Cuando una infección no responde a los antibióticos, la terapia con fagos es una alternativa, pero cada fago infecta solo algunas cepas y hoy el adecuado se encuentra ensayándolos uno por uno en el laboratorio. SIRFA prioriza computacionalmente los candidatos que vale la pena ensayar.

> SIRFA no diagnostica ni prescribe: toda recomendación es una hipótesis priorizada que debe ensayarse en laboratorio antes de cualquier uso clínico.

## Estado (18-11-2026)

- Funciona el ciclo completo: registro del aislado, análisis, predicción, validación por el microbiólogo, recomendación y alertas. Son 47 operaciones de API, 5 roles y 20 de las 24 tablas diseñadas.
- 212 pruebas automáticas del sistema (211 con SQLite en memoria y 1 de concurrencia contra PostgreSQL real) y 29 de la lógica de la app móvil.
- Límites que importan: el modelo se entrenó con 200 cepas y 105 fagos del conjunto público PhageHostLearn y, ante un tipo de locus K que no vio, no supera a una línea base simple (lo marca de baja confianza); la web es JavaScript sin compilar, no Next.js; la app móvil es un primer corte verificado en el navegador, no en un teléfono, y sin notificaciones push.

El detalle está en [`app/README.md`](app/README.md).

## Tecnologías

| Área | Tecnologías |
|---|---|
| Backend y API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic, PyJWT, argon2-cffi |
| Bioinformática | Prodigal, Mash, Kaptive, Biopython, BLAST+ |
| Aprendizaje automático | XGBoost, SHAP, scikit-learn, embeddings ESM-2 del conjunto PhageHostLearn |
| Bases de datos | PostgreSQL 16 (dominio, cola de trabajos y auditoría), MongoDB 7 (salidas crudas del análisis) |
| Web | HTML, CSS y JavaScript sin compilar, servidos por la API |
| App móvil | React Native con Expo |
| Infraestructura y calidad | Docker, Docker Compose, pytest, GitHub Actions |

## Cómo ejecutarlo localmente

Requisitos: Docker Desktop (con Docker Compose) y conexión a internet la primera vez.

```bash
cd app
cp .env.example .env
docker compose up --build -d
```

En Windows también sirve el doble clic en `app/iniciar_sirfa.bat`. Luego se abre http://localhost:8000/ (web), http://localhost:8000/docs (documentación de la API) y http://localhost:8000/api/v1/salud (estado de las bases). El banco de fagos, las cuentas de demostración y las pruebas se explican en [`app/README.md`](app/README.md) y en el [Manual técnico y de despliegue](app/docs/MANUAL_TECNICO.md).

## Arquitectura

Monolito modular con workers en segundo plano, en cinco contenedores Docker: `postgres`, `mongo`, `api`, `worker-pipeline` y `worker-prediction`.

```
Navegador ─┐
           ├─► API (FastAPI): JWT, roles, auditoría ──► PostgreSQL (dominio, cola de trabajos, auditoría)
App móvil ─┘                                                ▲
                                                            ├── worker-pipeline ──► Mash · Kaptive · Prodigal ──► MongoDB (salidas crudas)
                                                            └── worker-prediction ──► BLAST · XGBoost · SHAP
```

La API no hace el trabajo pesado: pone un trabajo en una cola que vive en PostgreSQL (con `FOR UPDATE SKIP LOCKED`) y responde de inmediato. Los diagramas del diseño están en [`app/docs/`](app/docs/README.md).

## Metodología de trabajo

Cascada tradicional (modelo secuencial por etapas, desarrollador único), con puertas de control entre las etapas, prioridad (Alta, Media o Baja) en cada requisito, pruebas escritas junto con cada módulo y control de cambios con solicitudes registradas. Se eligió porque los requisitos podían especificarse completos desde el inicio y porque el curso exige artefactos formales: SRS, Documento de Diseño, Plan de Pruebas con evidencias y Manual técnico.

## Integrantes y roles

| Responsable | Rol |
|---|---|
| Johao Ramírez | Desarrollador y arquitecto (API, pipeline, modelo, web, móvil y bases de datos); analista, QA y documentación |

Proyecto individual, autorizado por el docente de la asignatura.

## Estructura del repositorio

```
Capstone/
├── app/                      # Código del sistema: backend, pipeline, ml, frontend, mobile, docs y docker-compose.yml
├── .github/workflows/        # Integración continua (pruebas de la API y de la app móvil)
├── Fase 1/                   # Definición del proyecto
├── Fase 2/                   # Desarrollo: informes de avance y final, presentación
│   └── Evidencias Proyecto/  # Evidencias de documentación (SRS, diseño, manual, plan de pruebas) y de sistema (base de datos)
└── Fase 3/                   # Presentación final: diario, autoevaluación y presentación
```

## Fases

| Fase | Estado | Descripción |
|------|--------|-------------|
| Fase 1 | ✅ Completada | Definición del proyecto, autoevaluaciones, diario de reflexión, Carta Gantt y presentación |
| Fase 2 | ✅ Entregada | Informe de Avance e Informe Final, SRS v0.3, Documento de Diseño v0.3, Manual técnico y de despliegue v1.0, Plan de Pruebas y evidencias v1.0 y presentación del avance |
| Fase 3 | 🔄 En curso | Presentación final ante la comisión: diario de reflexión, autoevaluación y presentación de 14 láminas |

## Documentos principales

| Documento | Archivo |
|---|---|
| Informe de Avance | `Fase 2/2.4_APT122_InformeAvance_JohaoRamirez.docx` |
| Informe Final | `Fase 2/2.6_APT122_InformeFinal_JohaoRamirez.docx` |
| Especificación de Requisitos (SRS) v0.3 | `Fase 2/Evidencias Proyecto/Evidencias de documentación/Adjunto_A_SRS_SIRFA_v0.3.docx` |
| Documento de Diseño v0.3 | `Fase 2/Evidencias Proyecto/Evidencias de documentación/Adjunto_B_Documento_de_Diseno_SIRFA_v0.3.docx` |
| Manual técnico y de despliegue v1.0 | `Fase 2/Evidencias Proyecto/Evidencias de documentación/Adjunto_C_Manual_Tecnico_y_Despliegue_SIRFA_v1.0.docx` |
| Plan de Pruebas y evidencias v1.0 | `Fase 2/Evidencias Proyecto/Evidencias de documentación/Adjunto_D_Plan_de_Pruebas_y_Evidencias_SIRFA_v1.0.docx` |
| Presentación final | `Fase 3/3.4_APT122_PresentacionFinal_JohaoRamirez.pptx` |

## Historial del repositorio

Los documentos se versionan en este repositorio desde el inicio del curso. El código se desarrolló entre el 01-09 y el 18-11-2026 en una carpeta local, con un único commit inicial que no se conservó aquí, y se publicó en la semana 16 en commits por componente. **Las fechas de los commits del código son las de la publicación; no reflejan cuándo se escribió cada parte.**

## Autor

Johao Ramírez — [johaito@gmail.com](mailto:johaito@gmail.com)
