# Mini CRM de Parceiros — protótipo

Protótipo local sem banco de dados. A aplicação salva o histórico de cada ligação em
`data/historico_ligacoes.csv`; a carteira do dia fica em `data/carteira_2026-08-31.csv`.

## Abrir

No Windows, dentro desta pasta, execute:

```powershell
py server.py
```

Abra `http://localhost:8787` no navegador.

## Para o Power BI

Conecte a pasta `data` como fonte e consolide os CSVs de histórico. A coluna
`id_tarefa` permite relacionar cada ligação à carteira, ao motivo e ao parceiro.

## Historico oficial no BigQuery

Ao registrar uma ligacao, o CRM grava a interacao na tabela
`BQ_PROJECT_ID.BQ_DATASET.historico_ligacoes_crm`. O arquivo
`data/historico_ligacoes_backup.csv` e apenas uma copia local de seguranca.

Na primeira inicializacao, o CRM cria essa tabela automaticamente. A conta de
servico precisa ter permissao para criar e inserir dados no dataset. Para levar
o historico antigo de `data/historico_ligacoes.csv` para a tabela, execute uma vez:

```powershell
py migrar_historico_csv_bigquery.py
```

No Power BI, use a tabela do BigQuery como fonte do historico de ligacoes.

## Atualizar com BigQuery

Para gerar uma carteira inicial com parceiros reais, execute:

```powershell
py atualizar_carteira_bigquery.py
```

Essa rotina consulta somente os parceiros com telefone e vendas Starlink, sem disparar
e-mails. Nesta primeira versão ela cria até 10 contatos por consultor, por volume de
vendas. Ela não substitui uma carteira já criada para o mesmo dia, protegendo os registros
dos consultores. As regras de aniversário e de concentração por cidade serão acrescentadas depois.

## Próxima integração

O gerador da carteira diária deve substituir o CSV de exemplo por uma nova carteira
com base no BigQuery/Starlink e manter os CSVs anteriores como histórico.
