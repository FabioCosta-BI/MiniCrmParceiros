# Mini CRM de Parceiros Starlink

Aplicação interna para consultar uma carteira diária de parceiros por UF e registrar as ligações. Não usa BigQuery nem salva carteira ou histórico em CSV.

## Fontes e destino

- **Pegasus B2B (somente leitura):** cadastro Starlink, cidade-sede, telefones e vendas não canceladas. O cadastro é acessado por PostgreSQL; as vendas usam a mesma view ODBC do DW, `vw_cp_vendas_starlink`.
- **Arquivos locais do servidor:** `data/aniversarios_municipios_ibge.csv` e `data/Ranking de Cidades - Starlink.xlsx`. Eles não são enviados ao GitHub.
- **PostgreSQL da TI:** destino da carteira, histórico de atendimentos e controle de tentativas.

## Regra da carteira

Há três blocos de UFs: Norte/Centro-Oeste, Nordeste e Sudeste/Sul. Para cada bloco, a rotina seleciona, sem repetir parceiro:

- 6 parceiros em destaque de vendas, pelos maiores volumes Starlink da Vivensis;
- 24 parceiros em cidades estratégicas, cuja cidade está nos primeiros 80% acumulados de acessos Starlink da respectiva UF, conforme a planilha ANATEL;
- até 5 extras de aniversário de cidade, priorizados por vendas;
- todos os aniversariantes de parceiro, conforme `a023_dtnasto` no Pegasus B2B.

Antes de selecionar, a rotina verifica `controle_contatos`: parceiros ofertados hoje não voltam amanhã; `Não atendeu` só volta no segundo dia útil posterior; são permitidas até três tentativas no mês. Após contato efetivo ou a terceira tentativa, o parceiro sai da lista até o mês seguinte. `Número inválido` permanece bloqueado até correção cadastral.

## Tabelas que a TI cria

Executar uma vez [sql/postgresql_crm.sql](sql/postgresql_crm.sql) no banco PostgreSQL destinado ao CRM. O arquivo cria no schema `starlink_crm`:

- `carteira_diaria` — parceiros disponibilizados a cada data;
- `controle_contatos` — tentativas, próxima ação e bloqueios;
- `atendimentos_parceiros` — histórico completo de cada ligação.

## Configuração no servidor

1. Copiar `.env.example` para `.env` e preencher as credenciais fornecidas pela TI. O arquivo não deve ir ao Git.
2. Copiar os dois arquivos de referência para `data/` ou definir `RANKING_ANATEL_PATH` com o caminho correto.
3. Instalar dependências:

   ```bash
   python3 -m pip install -r requirements.txt
   ```

4. Gerar a carteira do dia:

   ```bash
   python3 atualizar_carteira_pegasus.py
   ```

5. Iniciar o sistema:

   ```bash
   python3 server.py
   ```

O Mini CRM ficará na porta `8787`. A rotina deve ser executada diariamente antes do início dos contatos.
