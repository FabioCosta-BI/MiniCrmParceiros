-- Executar uma unica vez no BigQuery, substituindo PROJECT_ID e DATASET.
CREATE TABLE IF NOT EXISTS `PROJECT_ID.DATASET.crm_carteira_diaria` (
    id_tarefa STRING NOT NULL,
    data_carteira DATE NOT NULL,
    uf STRING NOT NULL,
    id_wfm_b2b STRING NOT NULL,
    parceiro STRING,
    cidade STRING,
    telefone STRING,
    vendas_starlink INT64,
    motivos STRING,
    prioridade STRING,
    detalhe_regra STRING,
    criado_em TIMESTAMP NOT NULL
)
PARTITION BY data_carteira
CLUSTER BY uf, id_wfm_b2b;
