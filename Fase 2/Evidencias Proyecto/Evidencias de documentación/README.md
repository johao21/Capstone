# Evidencias de documentación — SIRFA

Documentos de ingeniería del proyecto (metodología en cascada). Cada uno corresponde a una etapa:

| Etapa | Documento | Archivo |
|---|---|---|
| 1. Análisis y requisitos | Especificación de Requisitos de Software (SRS) v0.3: 66 requisitos funcionales, 33 no funcionales, 18 historias de usuario y 12 reglas | `Adjunto_A_SRS_SIRFA_v0.3.docx` |
| 2. Diseño | Documento de Diseño v0.3: arquitectura, modelo de datos (24 tablas diseñadas y 12 construidas, en una sola base de datos), 4 diagramas UML, 60 casos de prueba y diferencias con lo construido | `Adjunto_B_Documento_de_Diseno_SIRFA_v0.3.docx` |
| 5. Despliegue | Manual técnico y de despliegue v1.0: servicios, variables de entorno, operación y solución de problemas | `Adjunto_C_Manual_Tecnico_y_Despliegue_SIRFA_v1.0.docx` |
| 4. Pruebas | Plan de Pruebas y evidencias v1.0: casos de prueba, resultados y lo que no se probó | `Adjunto_D_Plan_de_Pruebas_y_Evidencias_SIRFA_v1.0.docx` |

El Informe de Avance y el Informe Final están en la carpeta `Fase 2/`.

## Diagramas

Están como imágenes en `app/docs/` (y dentro del Documento de Diseño):

| Diagrama | Archivo |
|---|---|
| Casos de uso (UML) | `app/docs/uml/casos_de_uso.png` |
| Clases del dominio (UML) | `app/docs/uml/clases_del_dominio.png` |
| Secuencia del flujo principal (UML) | `app/docs/uml/secuencia_flujo_principal.png` |
| Componentes (UML) | `app/docs/arquitectura/componentes_uml.png` |
| Vista de despliegue | `app/docs/arquitectura/vista_de_despliegue.png` |
| Modelo entidad-relación: núcleo de solicitudes | `app/docs/modelo-datos/er_nucleo_solicitudes.png` |
| Modelo entidad-relación: banco de fagos y predicción | `app/docs/modelo-datos/er_banco_fagos_y_prediccion.png` |

Los diagramas de arquitectura son los del diseño: muestran 5 contenedores con la web en Next.js, y lo construido son 4 servicios con la web en JavaScript sin compilar (la diferencia está registrada en la SRS v0.3 y en el Documento de Diseño v0.3). Los dos diagramas entidad-relación también son los del diseño (24 tablas); lo construido son 12 tablas en una sola base de datos, PostgreSQL (solicitudes de cambio SC-06 y SC-07, iniciadas el 12-11-2026).
