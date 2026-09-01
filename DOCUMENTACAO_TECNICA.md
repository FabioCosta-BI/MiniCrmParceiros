# Mini CRM de Parceiros Starlink — documentação para TI

## Objetivo

Disponibilizar uma aplicação web interna e leve para que consultores consultem a carteira de parceiros por UF e registrem o resultado dos contatos comerciais.

O sistema não exige banco de dados dedicado. A carteira diária e o histórico são armazenados em arquivos CSV, permitindo baixo consumo de recursos no servidor.

## Fluxo da solução

```text
DW / BigQuery Starlink
        ↓
Rotina de geração da carteira diária
        ↓
CSV de carteira no servidor
        ↓
Consultor acessa o CRM pelo navegador
        ↓
Seleciona UF(s) e registra a ligação
        ↓
CSV de histórico atualizado
        ↓
Power BI lê carteira e histórico
```

## Atualizacao: historico no BigQuery

O CSV continua sendo usado para distribuir a carteira diaria. O registro de cada
ligacao agora e salvo oficialmente em `historico_ligacoes_crm` no BigQuery; o
arquivo `data/historico_ligacoes_backup.csv` e mantido apenas como contingencia
local. Esta secao substitui as referencias posteriores que descrevem o CSV como
historico oficial.

Na primeira execucao, o CRM cria a tabela automaticamente, se a conta de servico
tiver permissao de criar tabela no dataset. Ela precisa, no minimo, das permissoes
de criar tabela e inserir/ler dados nessa tabela. O Power BI deve usar a tabela
do BigQuery como fonte do historico de ligacoes.

## Uso pelos consultores

O consultor acessa a aplicação por um navegador, usando um endereço interno como:

```text
http://IP-DO-SERVIDOR:8787
```

Na tela, ele:

1. Seleciona uma ou mais UFs para trabalhar;
2. Visualiza parceiro, telefone, ID WFM B2B, quantidade de vendas e motivos do contato;
3. Registra a ação realizada;
4. Escolhe quem fez o contato;
5. Informa o resultado e uma observação opcional.

## Dados armazenados

Arquivos principais dentro da pasta `data`:

| Arquivo | Conteúdo |
|---|---|
| `carteira_AAAA-MM-DD.csv` | Parceiros selecionados para contato em cada dia, com UF, motivo e métricas de vendas. |
| `historico_ligacoes.csv` | Histórico cumulativo: cada ligação registrada acrescenta uma nova linha. |

O histórico contém data/hora, identificador da tarefa, ID WFM B2B, UF, parceiro, pessoa que registrou o contato, resultado e observação.

As cargas diárias não apagam o histórico. Isso permite análises históricas no Power BI.

## Regras atuais da carteira

Para cada UF, a rotina seleciona:

- Até 10 parceiros em cidades estratégicas: cidades que acumulam 80% dos acessos Starlink da UF, conforme a base ANATEL;
- Até 3 campeões de vendas: parceiros que estão dentro dos 80% acumulados de vendas da UF;
- Quando um parceiro se enquadra em mais de uma regra, ele aparece uma única vez com todos os motivos aplicáveis.

As regras de aniversário de parceiro e aniversário de cidade ainda não estão ativas, pois dependem de uma base de datas que não foi disponibilizada.

## Fontes dos dados

A geração da carteira utiliza os dados já existentes no DW/BigQuery Starlink:

- `dim_instaladora`: parceiro, ID WFM B2B e telefones;
- `fato_cobertura`: cidade e UF de atuação;
- `fato_venda_starlink`: vendas por parceiro;
- `Ranking de Cidades - Starlink.xlsx`: acessos Starlink/ANATEL por município.

O recomendado é executar a atualização da carteira em uma máquina já autorizada a acessar o BigQuery e copiar o CSV gerado para o servidor do CRM. Assim, credenciais do BigQuery não precisam ficar no servidor web.

## Requisitos do servidor

- Servidor Windows conectado à rede corporativa;
- Python 3.12 instalado;
- Pasta para hospedar a aplicação e seus arquivos de dados;
- Porta TCP `8787` liberada apenas para rede interna e/ou VPN;
- Backup diário da pasta `data`;
- Inicialização automática da aplicação após reinicialização do servidor.

Para iniciar manualmente, dentro da pasta da aplicação:

```powershell
py server.py
```

Os consultores acessam então:

```text
http://IP-DO-SERVIDOR:8787
```

## Segurança

A versão atual não possui login. A pessoa escolhe seu nome ao registrar a ligação. Portanto, a autoria é declarada, não autenticada.

Para o piloto interno:

- Não publicar a aplicação diretamente na internet;
- Restringir o acesso à rede corporativa ou VPN;
- Garantir que os consultores usem apenas a interface web, sem editar CSVs diretamente;
- Restringir a escrita na pasta `data` à conta que executa a aplicação e a administradores;
- Realizar backup diário da pasta `data`.

Se for necessário controle formal de identidade no futuro, o sistema pode receber autenticação corporativa sem alterar sua lógica de carteira e histórico.

## Integração com Power BI

O Power BI deve ler os arquivos da pasta `data`:

- A carteira diária indica quem foi selecionado, em qual UF e por qual regra;
- O histórico mostra as ações e resultados dos contatos;
- `id_tarefa` e `id_wfm_b2b` permitem relacionar histórico, parceiro e carteira.

Indicadores possíveis:

- Parceiros selecionados por UF e motivo;
- Ligações realizadas por pessoa;
- Contatos pendentes;
- Distribuição dos resultados de contato;
- Desempenho por UF, cidade estratégica e regra comercial.

## Arquivos da aplicação

```text
MiniCRMParceiros/
 ├─ server.py
 ├─ atualizar_carteira_bigquery.py
 ├─ index.html
 ├─ app.js
 ├─ arquivos .css
 ├─ data/
 │   ├─ carteira_AAAA-MM-DD.csv
 │   └─ historico_ligacoes.csv
 └─ Iniciar CRM.bat
```

O arquivo mais crítico para backup é `data/historico_ligacoes.csv`.
