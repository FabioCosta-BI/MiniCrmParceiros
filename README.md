# Mini CRM de Parceiros

Aplicacao web interna para os consultores consultarem a carteira de parceiros por
UF e registrarem o resultado de cada ligacao.

## Onde os dados ficam

- `data/carteira_AAAA-MM-DD.csv`: carteira diaria gerada para os consultores.
- BigQuery, tabela `historico_ligacoes_crm`: historico oficial dos contatos.

O CRM nao cria arquivo CSV de historico. O arquivo `.env` e o
`service-account.json` sao privados e nunca devem ser enviados ao GitHub.

## Abrir o CRM

No Windows, dentro desta pasta, execute:

```powershell
py server.py
```

Abra `http://localhost:8787` no navegador ou use o endereco interno do servidor.

Na primeira utilizacao, a tabela de historico e criada no BigQuery, caso a conta
de servico tenha permissao para criar, ler e inserir dados no dataset.

## Atualizar a carteira diaria

Para gerar a carteira com dados reais do BigQuery/Starlink:

```powershell
py atualizar_carteira_bigquery.py
```

A rotina cria um novo CSV diario e nao substitui uma carteira ja existente para a
mesma data. Assim, os registros dos consultores permanecem consistentes.

## Power BI

Use duas fontes:

- os CSVs de carteira da pasta `data`;
- a tabela `historico_ligacoes_crm` no BigQuery.

As colunas `id_tarefa` e `id_wfm_b2b` permitem relacionar a carteira, o parceiro,
os motivos e o resultado de cada contato.

## Dependencias

```powershell
py -m pip install -r requirements.txt
```

## Configuracao

Copie `.env.example` como `.env` e preencha as credenciais do ambiente. No
servidor, o caminho de `GOOGLE_APPLICATION_CREDENTIALS` deve apontar para o
`service-account.json` mantido localmente e protegido.
