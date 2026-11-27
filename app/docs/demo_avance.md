# Demostración del Informe de Avance

> **Esta guía es del corte del 28-10-2026** (sin autenticación ni modelo). Sigue valiendo para levantar los servicios y cargar el banco y las
> referencias (pasos 1 a 3); para el recorrido completo con inicio de sesión, roles, predicción y validación, ver [demo_completa.md](demo_completa.md).
> Desde que hay autenticación, los comandos `curl` de esta guía necesitan un token (`POST /api/v1/auth/login`) en la cabecera `Authorization: Bearer …`.

Corte funcional: bases de datos, API, banco de fagos poblado, pipeline genómico sobre un genoma real y una web mínima
para usarlo (http://localhost:8000/). No incluía todavía el modelo de predicción ni la autenticación.

## Requisitos

- Docker Desktop en marcha y Git.
- Internet, para descargar la tabla de INPHARED y el genoma de referencia.

## 1. Levantar los servicios

```bash
cp .env.example .env
docker compose up --build -d
```

La API aplica las migraciones al iniciar. Comprobación (debe responder `"estado":"ok"`):

```bash
curl http://localhost:8000/api/v1/salud
```

La documentación OpenAPI queda en http://localhost:8000/docs.

## 2. Poblar el banco de fagos (RF-27, RF-28, RF-29)

Descarga la tabla de INPHARED (abril 2026, unos 0,7 MB) y carga 200 fagos de *Klebsiella*:

```bash
docker compose exec api python -m pipeline.seed_phage_bank --descargar --hospedador Klebsiella --limite 200
```

Verificar y comprobar que una segunda corrida no duplica nada:

```bash
docker compose exec postgres psql -U sirfa -d sirfa -c "select count(*), min(accesion), max(accesion) from fago;"
```

```bash
docker compose exec api python -m pipeline.seed_phage_bank --hospedador Klebsiella --limite 200
```

## 3. Referencias de especie (RF-20, RN-03)

El pipeline solo acepta *K. pneumoniae*. Para verificarlo compara el genoma con 13 genomas de referencia
(`pipeline/referencias.tsv`: 2 de *K. pneumoniae* y una por cada especie cercana o confundible) usando la distancia
de Mash. Se construyen una vez, descargando de NCBI unos 70 MB y tardando unos 30 s:

```bash
docker compose exec api python -m pipeline.referencias construir
```

Sin ese sketch el worker lo advierte en su log y la especie **no se verifica**: usa la declarada.

## 4. Pipeline sobre un genoma real (RF-09 a RF-26)

Genoma de la demostración: *Klebsiella pneumoniae* subsp. *pneumoniae* HS11286, ensamblado completo
GCF_000240185.1 de NCBI (5,68 Mb, 7 contigs). HS11286 es también una de las referencias de especie, así que su
verificación sería trivial (distancia 0); para mostrar la verificación se usan genomas que no están en las
referencias (ver abajo).

```powershell
New-Item -ItemType Directory -Force data\genomas | Out-Null
Invoke-WebRequest -Uri https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/240/185/GCF_000240185.1_ASM24018v2/GCF_000240185.1_ASM24018v2_genomic.fna.gz -OutFile data\genomas\HS11286.fna.gz
```

Registrar la solicitud (el worker la toma solo). Lo más simple es la web: abrir http://localhost:8000/, subir el
archivo, escribir un código y la pantalla se actualiza sola hasta mostrar «Análisis completo». Lo mismo por la API:

```bash
curl -X POST http://localhost:8000/api/v1/solicitudes -F "archivo=@data/genomas/HS11286.fna.gz" -F "codigo_interno=HS11286"
```

Seguir el procesamiento con el identificador que devuelve el comando anterior:

```bash
docker compose logs -f worker-pipeline
```

```bash
curl http://localhost:8000/api/v1/solicitudes/<uuid>
```

Resultado observado en una corrida real (27-10-2026, por consola), unos 45 s de punta a punta; por la web (28-10-2026) tardó unos 20 s:

- Calidad `aprobado`: 5.682.322 pb, 7 contigs, N50 5.333.942, GC 57,12 %.
- Prodigal: 5.455 genes. Kaptive 3.3.2: locus K `KL103`, confianza `Typeable`.
- Especie: en esa primera corrida todavía no había referencias, así que quedó **no verificada**.
- Análisis guardado en PostgreSQL (el resultado completo, en la columna JSONB `detalle`) y un trabajo `prediccion` encolado
  (el motor de predicción es de la etapa siguiente).

Caminos de rechazo: un archivo que no es FASTA de nucleótidos, o un genoma de otra especie, termina la solicitud en
`rechazada` con el motivo.

### Verificación de especie con genomas que no están en las referencias

Resultado observado el 27-10-2026 con tres genomas de NCBI, cada uno en menos de un minuto:

| Genoma | Resultado de la solicitud |
| --- | --- |
| *K. pneumoniae* MGH 78578 (GCF_000016305.1) | Aceptada. Especie verificada con Mash (distancia 0,0114 a HS11286), locus K `KL52`, 5.294 genes |
| *K. variicola* JCM 12419 (GCF_018324045.1) | `rechazada`: "especie detectada: Klebsiella variicola (Mash 0.0093 a GCF_020525545.1)" |
| *E. coli* O157:H7 Sakai (GCF_000008865.2) | `rechazada`: "especie detectada: Escherichia coli (Mash 0.0225 a GCF_000005845.2)" |

```bash
curl -X POST http://localhost:8000/api/v1/solicitudes -F "archivo=@data/pruebas_especie/GCF_000016305.1.fna.gz" -F "codigo_interno=MGH78578"
```

(Los FASTA de prueba se descargan de NCBI a `data/pruebas_especie/`, que Git ignora.)

Validación más amplia, con 8 genomas: 3 *K. pneumoniae*, 2 *K. variicola*, 2 *K. quasipneumoniae* y 1 *E. coli*; los 8
quedaron bien clasificados. **Dos de ellos (GCF_000828055.2 y GCF_020525925.1) son la misma cepa tipo que ya está en
las referencias**, con distancia 0,0000, así que no cuentan como independientes: la validación independiente es de 6
genomas. Distancias: *K. pneumoniae* a 0,011–0,013 de su referencia, y las otras especies del complejo a 0,048–0,056
de *K. pneumoniae*. Con un solo umbral de distancia no se separan (0,048 queda bajo 0,05): lo que decide es la
referencia más cercana.

## Límites de este corte, para decirlos tal cual

- **Especie:** se verifica solo si existe el sketch (`python -m pipeline.referencias construir`); sin él se usa la
  declarada y queda `parametros.especie_verificada = false`. La validación es pequeña (6 genomas independientes) y no
  es estadística. Especies del complejo sin referencia (por ejemplo *K. africana* o *K. variicola* subsp. *tropica*)
  podrían confundirse con la referencia más cercana.
- **Locus K:** probado con Kaptive 3.3.2 y la base `kpsc_k`. La línea de comandos cambia entre versiones; si falla,
  la solicitud reintenta 3 veces (espera de 30 y 60 s) y pasa a `error`. Ajustar `KAPTIVE_CMD` en `.env`.
- **Banco:** la tabla de INPHARED trae la longitud del genoma en KB redondeados. INPHARED pasó a INPHARED2
  (phagebank.uk) y aún no publica una tabla descargable.
- **Datos de prueba de la suite automatizada:** son sintéticos y están marcados como tales en las pruebas.

## Pruebas automatizadas

```bash
docker compose exec api pytest
```

Pasan 102 pruebas.
