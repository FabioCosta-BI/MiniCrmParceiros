# Mini CRM de Parceiros Starlink — documentação técnica

## Objetivo

Aplicação web interna para os consultores abrirem a carteira do dia por UF e registrarem o resultado de cada ligação. Não há autenticação nesta primeira versão: o consultor informa seu nome ao registrar a interação.

## Arquitetura

```text
Pegasus B2B (leitura) ──┐
Planilha ANATEL local ──┼─> rotina diária ─> PostgreSQL da TI ─> Mini CRM / Power BI
CSV aniversários local ─┘                         │
                                                   ├─ carteira_diaria
                                                   ├─ controle_contatos
                                                   └─ atendimentos_parceiros
```

O projeto não consulta BigQuery e não persiste carteira ou atendimentos em CSV. Os dois arquivos locais são apenas referências de negócio, copiados manualmente para o servidor.

## Origem dos dados

| Informação | Origem | Forma de acesso |
|---|---|---|
| Parceiro, cidade-sede e telefones | Pegasus: `tb023_gcinstaladoras`, `tb024_gccontatos`, `tb_cidades` | PostgreSQL, somente leitura |
| Vendas Starlink | Pegasus: `vw_cp_vendas_starlink` | ODBC, somente leitura |
| Cidades estratégicas | `Ranking de Cidades - Starlink.xlsx` | Arquivo local no servidor |
| Aniversário municipal | `aniversarios_municipios_ibge.csv` | Arquivo local no servidor |
| Carteira e interações | Banco PostgreSQL indicado pela TI | Leitura e escrita no schema do CRM |

As consultas do Pegasus replicam os filtros Starlink já usados no DW: pessoa jurídica, operação contendo `STARLINK` e exclusão do cadastro de teste de CNPJ `123`. Nenhuma tabela do Pegasus é criada ou alterada.

## Rotina diária

O comando `python3 atualizar_carteira_pegasus.py` consulta as fontes e seleciona, em cada um dos três blocos de UFs, sem repetir parceiro:

- 6 parceiros em destaque de vendas;
- 24 parceiros cuja cidade está nos primeiros 80% acumulados de acessos Starlink da UF, segundo ANATEL;
- até 5 aniversariantes de cidade como extras, em ordem de vendas.

Antes da seleção, a rotina consulta `controle_contatos`:

- parceiro ofertado hoje não é incluído novamente no mesmo dia nem no dia seguinte;
- `Não atendeu` pode retornar no segundo dia útil posterior;
- o limite é de três tentativas por mês;
- contato efetivo e terceira tentativa bloqueiam o parceiro até a próxima competência;
- `Número inválido` fica bloqueado até que o cadastro seja corrigido.

A rotina substitui somente a carteira da data executada e, em seguida, registra a oferta no controle de contatos. Ela deve ser agendada uma vez por dia antes do início dos atendimentos.

## Tabelas PostgreSQL

O arquivo [sql/postgresql_crm.sql](sql/postgresql_crm.sql) deve ser executado pela TI uma única vez, no banco e no schema destinados ao CRM.

| Tabela | Conteúdo |
|---|---|
| `carteira_diaria` | Lista gerada por data, UF, parceiro, motivo, telefone e vendas. |
| `controle_contatos` | Tentativas, resultado mais recente, próxima tentativa e bloqueio. |
| `atendimentos_parceiros` | Histórico imutável de todas as interações informadas pelos consultores. |

## Configuração

Criar o arquivo `.env` a partir de `.env.example`. Ele contém duas conexões distintas: `PEGASUS_*` é apenas leitura na origem; `CRM_PG_*` aponta para o banco da TI que receberá os dados do CRM. Não compartilhar nem versionar esse arquivo.

No Linux, a TI também precisa instalar e configurar o driver ODBC e o DSN informado em `PEGASUS_ODBC_DSN`, pois a view de vendas é acessada por ODBC. Caso exista uma view equivalente acessível diretamente por PostgreSQL, o conector pode ser simplificado depois.

Os arquivos abaixo devem existir no servidor e ficar fora do Git:

```text
data/aniversarios_municipios_ibge.csv
data/Ranking de Cidades - Starlink.xlsx
```

## Operação e segurança

- Executar o serviço com conta técnica própria, com leitura no Pegasus e somente as permissões necessárias no schema `starlink_crm`.
- Liberar a porta TCP 8787 apenas para a rede corporativa e para clientes conectados pela VPN; não publicar a aplicação na internet.
- A pasta do projeto não deve permitir escrita para os consultores.
- O Power BI consulta `carteira_diaria`, `atendimentos_parceiros` e `controle_contatos` diretamente no PostgreSQL da TI, preferencialmente com usuário somente leitura.
