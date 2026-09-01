# Mini CRM de Parceiros Starlink - documentação técnica

## Finalidade

Aplicação web interna usada pelos consultores para trabalhar uma carteira diária de
parceiros Starlink. O consultor seleciona as UFs que irá atender, visualiza os
dados do parceiro e registra o resultado da ligação.

Não há login nesta primeira versão. No registro, a pessoa informa qual consultor
realizou o contato. Portanto, a autoria é declarada e não uma autenticação formal.

## Arquitetura

```text
BigQuery / DW                         Servidor interno
---------------                       -------------------------
Dados Starlink -> carteira diária ->  arquivo CSV de carteira
                                      Mini CRM (Python)
                                      histórico de contatos -> BigQuery
                                                            -> Power BI
```


## Funcionamento diário

1. A rotina `atualizar_carteira_bigquery.py` gera um arquivo
   `data/carteira_AAAA-MM-DD.csv`.
2. O consultor abre o CRM, seleciona uma ou mais UFs e consulta a carteira.
3. Após o contato, seleciona seu nome, o resultado e, se necessário, registra uma
   observação.
4. O CRM grava a interação na tabela `historico_ligacoes_crm` no BigQuery.
5. Ao abrir a carteira novamente, o CRM consulta essa tabela para indicar o último
   status registrado para cada tarefa.

Uma carteira já criada para a mesma data não é substituída pela rotina de geração.

## Regras da carteira

Para cada UF, a seleção considera:

- até 10 parceiros em cidade estratégica: cidades que acumulam 80% dos acessos
  Starlink da UF, conforme a base ANATEL;
- até 3 campeões de vendas: parceiros dentro dos 80% acumulados de vendas
  Starlink/Vivensis da UF;
- parceiros cuja cidade-sede faz aniversário na data, quando houver correspondência
  com a base municipal carregada.

O mesmo parceiro aparece uma vez, mesmo que se enquadre em mais de uma regra. Os
motivos são exibidos juntos na carteira.

## Dados gravados no BigQuery

A tabela é criada com o nome abaixo, usando as variáveis do `.env`:

```text
BQ_PROJECT_ID.BQ_DATASET.historico_ligacoes_crm
```

Campos principais:

| Campo | Uso |
|---|---|
| `id_interacao` | Identificador único do registro. |
| `data_hora` | Data e hora do registro. |
| `id_tarefa` | Identificador da tarefa da carteira diária. |
| `data_carteira` | Data da carteira de origem. |
| `consultor` | Pessoa que declarou o contato. |
| `uf`, `cidade`, `parceiro`, `id_wfm_b2b` | Identificação do parceiro atendido. |
| `motivos` | Motivo ou motivos que colocaram o parceiro na carteira. |
| `resultado` | Resultado informado pelo consultor. |
| `observacao` | Comentário opcional. |

O Power BI deve considerar o registro mais recente de cada `id_tarefa` para mostrar
o status atual, mantendo todos os registros para análises históricas.

## Requisitos do servidor

- Windows com Python 3.12 ou superior;
- acesso à rede corporativa e às fontes do BigQuery;
- porta TCP 8787 liberada somente para a rede interna e/ou VPN;
- proxy corporativo, quando existir, configurado para a conta ou serviço que
  executa o CRM;
- pasta da aplicação com permissão de leitura e execução para a conta do serviço.

Para instalar as dependências:

```powershell
py -m pip install -r requirements.txt
```

Para iniciar manualmente:

```powershell
py server.py
```

O acesso é feito pelo navegador em um endereço como:

```text
http://IP-DO-SERVIDOR:8787
```

## Credenciais e permissões

O arquivo `service-account.json` é a credencial usada para o BigQuery. Ele deve
ficar apenas no servidor, com acesso restrito à conta que executa a aplicação.
Nunca deve ser enviado ao GitHub, anexado em e-mail ou compartilhado por mensageria.

O arquivo `.env` aponta para essa credencial e contém, no mínimo:

```text
BQ_PROJECT_ID=
BQ_DATASET=
GOOGLE_APPLICATION_CREDENTIALS=C:\caminho\service-account.json
```

A conta de serviço precisa ler e inserir dados em `historico_ligacoes_crm`. Caso a
tabela seja criada automaticamente pelo CRM, ela também precisa criar tabelas no
dataset. Para gerar a carteira, permanecem necessárias as permissões de leitura e
consulta já usadas pelo processo Starlink.

## Segurança

- A aplicação não deve ser publicada diretamente na internet.
- O firewall deve aceitar a porta 8787 apenas de redes corporativas e da VPN.
- Recomenda-se executar o processo com uma conta de serviço Windows própria.
- A pasta do projeto não deve conceder escrita aos consultores; eles registram
  informações pela interface web.
- O repositório GitHub deve ser privado e não deve conter CSVs de carteira, `.env`
  ou `service-account.json`.
- Para uso fora da VPN ou para auditoria de autoria, a próxima evolução deve ser
  autenticação corporativa.

## Power BI

O relatório deve combinar:

- os CSVs de carteira diária, para entender quem foi selecionado e por qual regra;
- a tabela `historico_ligacoes_crm`, para medir contatos, resultados e desempenho.

As chaves `id_tarefa` e `id_wfm_b2b` permitem relacionar as duas fontes. Indicadores
esperados incluem contatos realizados, pendências, resultado das ligações,
produtividade por consultor, UF e motivo de seleção.

## Arquivos do projeto

```text
MiniCRMParceiros/
├─ server.py                         aplicação web e integração do histórico
├─ atualizar_carteira_bigquery.py    geração da carteira diária
├─ gerar_aniversarios_municipios_ibge.py
├─ index.html, app.js e arquivos CSS interface web
├─ requirements.txt                  dependências Python
├─ .env.example                      modelo de configuração
├─ data/                             carteiras diárias e base municipal
└─ service-account.json              somente no servidor; ignorado pelo Git
```
