# Imagen única de backend (decisión D-03): la usan la API y los workers con distinto comando.
# Contexto de construcción: la raíz del repositorio.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/backend

# Herramientas bioinformáticas imprescindibles para el pipeline.
RUN apt-get update \
    && apt-get install -y --no-install-recommends prodigal ncbi-blast+ minimap2 curl \
    && rm -rf /var/lib/apt/lists/*

# Mash (identificación de especie): opcional, el pipeline avisa si falta.
RUN apt-get update \
    && (apt-get install -y --no-install-recommends mash || echo "AVISO: mash no está disponible en esta imagen") \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Kaptive (tipificación del locus K). Si falla la instalación el pipeline lo informa al ejecutarse.
RUN (pip install --no-cache-dir kaptive biopython || echo "AVISO: kaptive no se pudo instalar")

COPY backend backend
COPY pipeline pipeline
COPY ml ml
COPY frontend frontend
COPY pytest.ini .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
