-- Executar uma unica vez no banco PostgreSQL definido pela TI.
CREATE SCHEMA IF NOT EXISTS starlink_crm;

CREATE TABLE IF NOT EXISTS starlink_crm.carteira_diaria (
    id_tarefa              VARCHAR(120) PRIMARY KEY,
    data_carteira          DATE NOT NULL,
    bloco_uf               VARCHAR(80) NOT NULL,
    uf                     CHAR(2) NOT NULL,
    id_wfm_b2b             VARCHAR(80) NOT NULL,
    parceiro               VARCHAR(250),
    cidade                 VARCHAR(150),
    cod_ibge               BIGINT,
    telefone               VARCHAR(40),
    vendas_starlink        INTEGER NOT NULL DEFAULT 0,
    motivos                VARCHAR(300) NOT NULL,
    prioridade             VARCHAR(30) NOT NULL,
    detalhe_regra          TEXT,
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_carteira_diaria_data_uf
    ON starlink_crm.carteira_diaria (data_carteira, uf);

CREATE TABLE IF NOT EXISTS starlink_crm.controle_contatos (
    id_wfm_b2b             VARCHAR(80) NOT NULL,
    competencia            DATE NOT NULL,
    tentativas_no_mes      SMALLINT NOT NULL DEFAULT 0 CHECK (tentativas_no_mes BETWEEN 0 AND 3),
    data_ultima_tentativa  TIMESTAMPTZ,
    data_proxima_tentativa DATE,
    data_ultima_oferta     DATE,
    status                 VARCHAR(30) NOT NULL DEFAULT 'elegivel'
                           CHECK (status IN ('elegivel', 'aguardando_tentativa', 'concluido', 'bloqueado')),
    ultimo_resultado       VARCHAR(80),
    atualizado_em          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_wfm_b2b, competencia)
);

CREATE INDEX IF NOT EXISTS ix_controle_contatos_fila
    ON starlink_crm.controle_contatos (competencia, status, data_proxima_tentativa);

CREATE TABLE IF NOT EXISTS starlink_crm.atendimentos_parceiros (
    id_atendimento         UUID PRIMARY KEY,
    data_hora              TIMESTAMPTZ NOT NULL,
    id_tarefa              VARCHAR(120) NOT NULL,
    data_carteira          DATE NOT NULL,
    consultor              VARCHAR(120) NOT NULL,
    id_wfm_b2b             VARCHAR(80) NOT NULL,
    parceiro               VARCHAR(250),
    uf                     CHAR(2),
    cidade                 VARCHAR(150),
    motivos                VARCHAR(300),
    resultado              VARCHAR(80) NOT NULL,
    observacao             TEXT,
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_atendimentos_tarefa_data
    ON starlink_crm.atendimentos_parceiros (id_tarefa, data_hora DESC);

CREATE INDEX IF NOT EXISTS ix_atendimentos_parceiro_data
    ON starlink_crm.atendimentos_parceiros (id_wfm_b2b, data_hora DESC);
