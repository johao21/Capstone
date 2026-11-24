CREATE TABLE auditoria (
	seq BIGSERIAL NOT NULL, 
	ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	usuario_id UUID, 
	correo VARCHAR(254), 
	rol VARCHAR(3), 
	accion VARCHAR(60) NOT NULL, 
	entidad VARCHAR(60), 
	entidad_id VARCHAR(64), 
	resultado VARCHAR(10) NOT NULL, 
	origen VARCHAR(64), 
	modelo_version VARCHAR(40), 
	detalle JSONB NOT NULL, 
	hash_previo VARCHAR(64) NOT NULL, 
	hash VARCHAR(64) NOT NULL, 
	CONSTRAINT pk_auditoria PRIMARY KEY (seq)
);

CREATE INDEX ix_auditoria_accion ON auditoria (accion);

CREATE INDEX ix_auditoria_ts ON auditoria (ts);

CREATE INDEX ix_auditoria_usuario_id ON auditoria (usuario_id);

CREATE TABLE modelo_prediccion (
	id UUID NOT NULL, 
	version VARCHAR(40) NOT NULL, 
	algoritmo VARCHAR(120) NOT NULL, 
	entrenado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	n_entrenamiento INTEGER, 
	metricas JSONB NOT NULL, 
	parametros JSONB NOT NULL, 
	ruta_artefacto VARCHAR(300), 
	activo BOOLEAN NOT NULL, 
	CONSTRAINT pk_modelo_prediccion PRIMARY KEY (id), 
	CONSTRAINT uq_modelo_prediccion_version UNIQUE (version)
);

CREATE TABLE sesion_revocada (
	sid VARCHAR(40) NOT NULL, 
	expira_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_sesion_revocada PRIMARY KEY (sid)
);

CREATE TABLE alerta (
	id UUID NOT NULL, 
	usuario_id UUID NOT NULL, 
	solicitud_id UUID NOT NULL, 
	tipo VARCHAR(20) NOT NULL, 
	mensaje TEXT NOT NULL, 
	leida BOOLEAN NOT NULL, 
	creada_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_alerta PRIMARY KEY (id), 
	CONSTRAINT ck_alerta_tipo CHECK (tipo IN ('emitida', 'rechazada', 'prediccion_lista')), 
	CONSTRAINT fk_alerta_usuario_id_usuario FOREIGN KEY(usuario_id) REFERENCES usuario (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_alerta_solicitud_id_solicitud FOREIGN KEY(solicitud_id) REFERENCES solicitud (id) ON DELETE RESTRICT
);

CREATE INDEX ix_alerta_usuario_leida ON alerta (usuario_id, leida);

CREATE TABLE prediccion (
	id UUID NOT NULL, 
	solicitud_id UUID NOT NULL, 
	modelo_id UUID NOT NULL, 
	locus_k_tipo VARCHAR(20), 
	baja_confianza BOOLEAN NOT NULL, 
	motivo_baja_confianza TEXT, 
	detalle JSONB NOT NULL, 
	generada_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_prediccion PRIMARY KEY (id), 
	CONSTRAINT fk_prediccion_solicitud_id_solicitud FOREIGN KEY(solicitud_id) REFERENCES solicitud (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_prediccion_modelo_id_modelo_prediccion FOREIGN KEY(modelo_id) REFERENCES modelo_prediccion (id) ON DELETE RESTRICT
);

CREATE INDEX ix_prediccion_solicitud_id ON prediccion (solicitud_id);

CREATE TABLE prediccion_fago (
	prediccion_id UUID NOT NULL, 
	fago_id UUID NOT NULL, 
	puntaje FLOAT NOT NULL, 
	rango INTEGER NOT NULL, 
	explicacion JSONB NOT NULL, 
	CONSTRAINT pk_prediccion_fago PRIMARY KEY (prediccion_id, fago_id), 
	CONSTRAINT fk_prediccion_fago_prediccion_id_prediccion FOREIGN KEY(prediccion_id) REFERENCES prediccion (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_prediccion_fago_fago_id_fago FOREIGN KEY(fago_id) REFERENCES fago (id) ON DELETE RESTRICT
);

CREATE TABLE recomendacion_emitida (
	id UUID NOT NULL, 
	solicitud_id UUID NOT NULL, 
	version INTEGER NOT NULL, 
	prediccion_id UUID NOT NULL, 
	validador_id UUID NOT NULL, 
	estado VARCHAR(12) NOT NULL, 
	observacion TEXT, 
	advertencia TEXT NOT NULL, 
	emitida_en TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_recomendacion_emitida PRIMARY KEY (id), 
	CONSTRAINT uq_recomendacion_solicitud_version UNIQUE (solicitud_id, version), 
	CONSTRAINT ck_recomendacion_emitida_estado CHECK (estado IN ('vigente', 'reemplazada')), 
	CONSTRAINT fk_recomendacion_emitida_solicitud_id_solicitud FOREIGN KEY(solicitud_id) REFERENCES solicitud (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_recomendacion_emitida_prediccion_id_prediccion FOREIGN KEY(prediccion_id) REFERENCES prediccion (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_recomendacion_emitida_validador_id_usuario FOREIGN KEY(validador_id) REFERENCES usuario (id) ON DELETE RESTRICT
);

CREATE INDEX ix_recomendacion_emitida_solicitud_id ON recomendacion_emitida (solicitud_id);

CREATE TABLE recomendacion_candidato (
	recomendacion_id UUID NOT NULL, 
	fago_id UUID NOT NULL, 
	rango INTEGER NOT NULL, 
	puntaje FLOAT NOT NULL, 
	descartado BOOLEAN NOT NULL, 
	justificacion TEXT, 
	resultado_ensayo VARCHAR(12) NOT NULL, 
	CONSTRAINT pk_recomendacion_candidato PRIMARY KEY (recomendacion_id, fago_id), 
	CONSTRAINT ck_recomendacion_candidato_resultado_ensayo CHECK (resultado_ensayo IN ('infecta', 'no_infecta', 'no_ensayado')), 
	CONSTRAINT fk_recomendacion_candidato_recomendacion_id_recomendaci_b6f1 FOREIGN KEY(recomendacion_id) REFERENCES recomendacion_emitida (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_recomendacion_candidato_fago_id_fago FOREIGN KEY(fago_id) REFERENCES fago (id) ON DELETE RESTRICT
);
