# Documentación

Índice de lo que hay en esta carpeta y de dónde están los documentos formales del curso.

## En esta carpeta

| Archivo o carpeta | Qué contiene |
|---|---|
| [MANUAL_TECNICO.md](MANUAL_TECNICO.md) | Manual técnico y de despliegue: requisitos, servicios, variables de entorno, instalación paso a paso, operación, pruebas y solución de problemas |
| [demo_completa.md](demo_completa.md) | Recorrido de demostración por los cinco roles |
| [demo_avance.md](demo_avance.md) | Guía de la demostración del Informe de Avance, con la misma prueba por la API |
| [arquitectura/](arquitectura) | Vista de despliegue y diagrama de componentes |
| [modelo-datos/](modelo-datos) | Diagramas entidad-relación de PostgreSQL |
| [uml/](uml) | Casos de uso, clases del dominio y secuencia del flujo principal |

## Los diagramas son los del diseño

Las imágenes de `arquitectura/`, `modelo-datos/` y `uml/` salen del Documento de Diseño v0.3 (línea base de la etapa 2). **Muestran el diseño, no siempre lo construido.** Las diferencias que conviene tener presentes:

- El diseño prevé la web en **Next.js** (`:3000`) y **cinco contenedores** (web, API, dos workers y PostgreSQL); se construyó una web de HTML y JavaScript sin compilar que sirve la propia API, y son **cuatro contenedores** (`postgres`, `api`, `worker-pipeline` y `worker-prediction`).
- Los diagramas entidad-relación cubren 16 de las **24 tablas** diseñadas; el esquema construido tiene **12** (solicitud de cambio SC-07, iniciada el 12-11-2026, el mismo día que SC-06). Las tablas de detalle pasaron a columnas o a JSON de la tabla a la que pertenecen: el genoma está en `aislado`; el análisis genómico y su detalle JSONB, en `solicitud`; el origen de cada fago, en `fago.origenes`; la ficha del modelo, en `prediccion.modelo`; los candidatos emitidos, en `recomendacion_emitida.candidatos`; las sesiones cerradas, en `usuario.sesiones_revocadas`; y el historial de estados se lee de la auditoría. Además hay una sola base de datos (SC-06).
- El diseño usa embeddings ESM-2 calculados por el sistema; se usan los precalculados del conjunto PhageHostLearn.
- La app móvil (React Native con Expo) se conecta a la API por HTTP en la red local; el diseño supone HTTPS, que aún no está configurado.

El detalle de cada diferencia, con su solicitud de cambio, está en la SRS v0.3 (anexo B y sección 9.2) y en el Documento de Diseño v0.3 (sección 10).

## Documentos del curso

La SRS, el Documento de Diseño, los informes de avance y final, los diarios y las autoevaluaciones están en las carpetas `Fase 1/`, `Fase 2/` y `Fase 3/` de este mismo repositorio (https://github.com/johao21/Capstone).

- SRS v0.3: `Fase 2/Evidencias Proyecto/Evidencias de documentación/Adjunto_A_SRS_SIRFA_v0.3.docx`
- Documento de Diseño v0.3: `Fase 2/Evidencias Proyecto/Evidencias de documentación/Adjunto_B_Documento_de_Diseno_SIRFA_v0.3.docx`
- Manual técnico y de despliegue: este mismo repositorio ([MANUAL_TECNICO.md](MANUAL_TECNICO.md)) y `Fase 2/Evidencias Proyecto/Evidencias de documentación/Adjunto_C_Manual_Tecnico_y_Despliegue_SIRFA_v1.0.docx`
