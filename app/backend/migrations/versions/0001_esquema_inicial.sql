CREATE TABLE centro (
	id UUID NOT NULL, 
	codigo VARCHAR(40) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_centro PRIMARY KEY (id), 
	CONSTRAINT uq_centro_codigo UNIQUE (codigo)
);

CREATE TABLE fuente_datos (
	id UUID NOT NULL, 
	nombre VARCHAR(80) NOT NULL, 
	version VARCHAR(80) NOT NULL, 
	url VARCHAR(500), 
	descargado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_fuente_datos PRIMARY KEY (id), 
	CONSTRAINT uq_fuente_datos_nombre_version UNIQUE (nombre, version)
);

CREATE TABLE usuario (
	id UUID NOT NULL, 
	correo VARCHAR(254) NOT NULL, 
	nombre VARCHAR(200) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	rol VARCHAR(3) NOT NULL, 
	centro_id UUID NOT NULL, 
	activo BOOLEAN NOT NULL, 
	intentos_fallidos INTEGER NOT NULL, 
	bloqueado_hasta TIMESTAMP WITH TIME ZONE, 
	creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_usuario PRIMARY KEY (id), 
	CONSTRAINT ck_usuario_rol CHECK (rol IN ('TEC', 'MIC', 'CLI', 'EPI', 'ADM')), 
	CONSTRAINT uq_usuario_correo UNIQUE (correo), 
	CONSTRAINT fk_usuario_centro_id_centro FOREIGN KEY(centro_id) REFERENCES centro (id) ON DELETE RESTRICT
);

CREATE TABLE aislado (
	id UUID NOT NULL, 
	codigo_interno VARCHAR(80) NOT NULL, 
	centro_id UUID NOT NULL, 
	fecha_aislamiento DATE NOT NULL, 
	especie_declarada VARCHAR(120) NOT NULL, 
	tipo_muestra VARCHAR(20) NOT NULL, 
	mecanismo_resistencia VARCHAR(20), 
	observaciones TEXT, 
	creado_por UUID NOT NULL, 
	creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_aislado PRIMARY KEY (id), 
	CONSTRAINT uq_aislado_centro_codigo UNIQUE (centro_id, codigo_interno), 
	CONSTRAINT ck_aislado_tipo_muestra CHECK (tipo_muestra IN ('sangre', 'orina', 'respiratoria', 'herida', 'otra')), 
	CONSTRAINT ck_aislado_mecanismo_resistencia CHECK (mecanismo_resistencia IN ('KPC', 'NDM', 'OXA-48', 'VIM', 'IMP', 'otro', 'ninguno', 'desconocido')), 
	CONSTRAINT fk_aislado_centro_id_centro FOREIGN KEY(centro_id) REFERENCES centro (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_aislado_creado_por_usuario FOREIGN KEY(creado_por) REFERENCES usuario (id) ON DELETE RESTRICT
);

CREATE TABLE fago (
	id UUID NOT NULL, 
	accesion VARCHAR(40) NOT NULL, 
	nombre VARCHAR(300) NOT NULL, 
	familia VARCHAR(120), 
	genero VARCHAR(120), 
	ciclo_vida VARCHAR(12) NOT NULL, 
	longitud_pb INTEGER, 
	completitud VARCHAR(40), 
	hospedador_declarado VARCHAR(200), 
	estado_curaduria VARCHAR(12) NOT NULL, 
	curado_por UUID, 
	curado_en TIMESTAMP WITH TIME ZONE, 
	documento_id VARCHAR(40), 
	creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_fago PRIMARY KEY (id), 
	CONSTRAINT ck_fago_ciclo_vida CHECK (ciclo_vida IN ('litico', 'templado', 'desconocido')), 
	CONSTRAINT ck_fago_estado_curaduria CHECK (estado_curaduria IN ('pendiente', 'aprobado', 'descartado')), 
	CONSTRAINT uq_fago_accesion UNIQUE (accesion), 
	CONSTRAINT fk_fago_curado_por_usuario FOREIGN KEY(curado_por) REFERENCES usuario (id) ON DELETE RESTRICT
);

CREATE INDEX ix_fago_nombre ON fago (nombre);

CREATE TABLE fago_origen (
	fago_id UUID NOT NULL, 
	fuente_id UUID NOT NULL, 
	id_externo VARCHAR(80) NOT NULL, 
	version_origen VARCHAR(80) NOT NULL, 
	descargado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_fago_origen PRIMARY KEY (fago_id, fuente_id), 
	CONSTRAINT fk_fago_origen_fago_id_fago FOREIGN KEY(fago_id) REFERENCES fago (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_fago_origen_fuente_id_fuente_datos FOREIGN KEY(fuente_id) REFERENCES fuente_datos (id) ON DELETE RESTRICT
);

CREATE TABLE genoma (
	id UUID NOT NULL, 
	aislado_id UUID NOT NULL, 
	ruta_archivo VARCHAR(500) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	tamano_bytes BIGINT NOT NULL, 
	nombre_original VARCHAR(255) NOT NULL, 
	qc_longitud BIGINT, 
	qc_contigs INTEGER, 
	qc_n50 INTEGER, 
	qc_gc FLOAT, 
	qc_prop_ambiguas FLOAT, 
	qc_resultado VARCHAR(12), 
	cargado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_genoma PRIMARY KEY (id), 
	CONSTRAINT uq_genoma_aislado_sha256 UNIQUE (aislado_id, sha256), 
	CONSTRAINT ck_genoma_qc_resultado CHECK (qc_resultado IN ('aprobado', 'advertencia', 'rechazado')), 
	CONSTRAINT fk_genoma_aislado_id_aislado FOREIGN KEY(aislado_id) REFERENCES aislado (id) ON DELETE RESTRICT
);

CREATE TABLE interaccion_conocida (
	id UUID NOT NULL, 
	fago_id UUID NOT NULL, 
	especie_hospedador VARCHAR(120) NOT NULL, 
	cepa VARCHAR(120), 
	locus_k_tipo VARCHAR(20), 
	resultado VARCHAR(12) NOT NULL, 
	fuente_id UUID NOT NULL, 
	referencia VARCHAR(300), 
	CONSTRAINT pk_interaccion_conocida PRIMARY KEY (id), 
	CONSTRAINT ck_interaccion_conocida_resultado CHECK (resultado IN ('infecta', 'no_infecta')), 
	CONSTRAINT fk_interaccion_conocida_fago_id_fago FOREIGN KEY(fago_id) REFERENCES fago (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_interaccion_conocida_fuente_id_fuente_datos FOREIGN KEY(fuente_id) REFERENCES fuente_datos (id) ON DELETE RESTRICT
);

CREATE INDEX ix_interaccion_conocida_fago_id ON interaccion_conocida (fago_id);

CREATE INDEX ix_interaccion_conocida_locus_k_tipo ON interaccion_conocida (locus_k_tipo);

CREATE TABLE solicitud (
	id UUID NOT NULL, 
	aislado_id UUID NOT NULL, 
	genoma_id UUID NOT NULL, 
	centro_id UUID NOT NULL, 
	solicitante_id UUID NOT NULL, 
	creada_por UUID NOT NULL, 
	asignada_a UUID, 
	estado VARCHAR(20) NOT NULL, 
	motivo_estado TEXT, 
	creada_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	actualizada_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_solicitud PRIMARY KEY (id), 
	CONSTRAINT ck_solicitud_estado CHECK (estado IN ('registrada', 'en_analisis', 'prediccion_lista', 'en_validacion', 'emitida', 'cerrada', 'rechazada', 'anulada', 'error')), 
	CONSTRAINT fk_solicitud_aislado_id_aislado FOREIGN KEY(aislado_id) REFERENCES aislado (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_solicitud_genoma_id_genoma FOREIGN KEY(genoma_id) REFERENCES genoma (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_solicitud_centro_id_centro FOREIGN KEY(centro_id) REFERENCES centro (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_solicitud_solicitante_id_usuario FOREIGN KEY(solicitante_id) REFERENCES usuario (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_solicitud_creada_por_usuario FOREIGN KEY(creada_por) REFERENCES usuario (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_solicitud_asignada_a_usuario FOREIGN KEY(asignada_a) REFERENCES usuario (id) ON DELETE RESTRICT
);

CREATE INDEX ix_solicitud_asignada_estado ON solicitud (asignada_a, estado);

CREATE INDEX ix_solicitud_centro_estado ON solicitud (centro_id, estado, creada_en);

CREATE TABLE analisis_genomico (
	id UUID NOT NULL, 
	solicitud_id UUID NOT NULL, 
	especie_detectada VARCHAR(120), 
	distancia_especie FLOAT, 
	locus_k_tipo VARCHAR(20), 
	locus_k_confianza VARCHAR(40), 
	n_genes INTEGER, 
	n_proteinas INTEGER, 
	versiones_herramientas JSONB NOT NULL, 
	parametros JSONB NOT NULL, 
	documento_id VARCHAR(40), 
	creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_analisis_genomico PRIMARY KEY (id), 
	CONSTRAINT fk_analisis_genomico_solicitud_id_solicitud FOREIGN KEY(solicitud_id) REFERENCES solicitud (id) ON DELETE RESTRICT
);

CREATE INDEX ix_analisis_genomico_solicitud_id ON analisis_genomico (solicitud_id);

CREATE TABLE solicitud_historial (
	id UUID NOT NULL, 
	solicitud_id UUID NOT NULL, 
	estado_anterior VARCHAR(20), 
	estado_nuevo VARCHAR(20) NOT NULL, 
	usuario_id UUID, 
	motivo TEXT, 
	creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_solicitud_historial PRIMARY KEY (id), 
	CONSTRAINT fk_solicitud_historial_solicitud_id_solicitud FOREIGN KEY(solicitud_id) REFERENCES solicitud (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_solicitud_historial_usuario_id_usuario FOREIGN KEY(usuario_id) REFERENCES usuario (id) ON DELETE RESTRICT
);

CREATE INDEX ix_solicitud_historial_solicitud_id ON solicitud_historial (solicitud_id);

CREATE TABLE trabajo (
	id UUID NOT NULL, 
	tipo VARCHAR(12) NOT NULL, 
	solicitud_id UUID, 
	estado VARCHAR(12) NOT NULL, 
	intentos INTEGER NOT NULL, 
	siguiente_intento_en TIMESTAMP WITH TIME ZONE, 
	bloqueado_por VARCHAR(120), 
	error TEXT, 
	creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	terminado_en TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_trabajo PRIMARY KEY (id), 
	CONSTRAINT ck_trabajo_tipo CHECK (tipo IN ('pipeline', 'prediccion', 'ingesta')), 
	CONSTRAINT ck_trabajo_estado CHECK (estado IN ('pendiente', 'en_curso', 'ok', 'fallido')), 
	CONSTRAINT fk_trabajo_solicitud_id_solicitud FOREIGN KEY(solicitud_id) REFERENCES solicitud (id) ON DELETE RESTRICT
);

CREATE INDEX ix_trabajo_pendientes ON trabajo (tipo, siguiente_intento_en) WHERE estado = 'pendiente';
