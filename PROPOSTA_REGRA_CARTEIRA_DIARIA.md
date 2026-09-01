# Regra aprovada — carteira diária de parceiros

## Composição por bloco de UFs

Os blocos seguem a divisão usada no fluxo de Controle de Campo:

| Bloco | UFs | Destaque de vendas | Cidade estratégica | Aniversário da cidade |
|---|---|---:|---:|---:|
| Norte e Centro-Oeste | AC, AM, AP, DF, GO, MA, MS, MT, PA, PI, RO, RR, TO | 6 | 24 | até 5 extras de cidade + aniversariantes de parceiro |
| Nordeste | AL, BA, CE, PB, PE, RN, SE | 6 | 24 | até 5 extras de cidade + aniversariantes de parceiro |
| Sudeste e Sul | ES, MG, PR, RJ, RS, SC, SP | 6 | 24 | até 5 extras de cidade + aniversariantes de parceiro |

Assim, cada bloco terá 30 parceiros principais, até cinco extras de aniversário de cidade e todos os aniversariantes de parceiro do dia. Um parceiro nunca ocupa duas linhas na mesma carteira.

## Critérios

1. **Parceiro em destaque de vendas:** seis parceiros com maior quantidade de vendas Starlink da Vivensis no bloco, entre os elegíveis.
2. **Cidade estratégica:** 24 parceiros com maior quantidade de vendas Starlink da Vivensis, cuja cidade-sede está nos primeiros 80% acumulados de `ACESSOS STARLINK` da própria UF, conforme a referência ANATEL.
3. **Aniversário da cidade:** até cinco parceiros extras por bloco, com cidade-sede aniversariante na data. Se houver mais candidatos, entram os que têm mais vendas.
4. **Aniversário do parceiro:** todos os parceiros cuja data `a023_dtnasto` no cadastro Pegasus coincide com o dia e mês atuais; entram como extras, sem limite.

Os critérios são aplicados nessa ordem. Depois que um parceiro é escolhido, ele não pode ser escolhido novamente por outro critério no mesmo dia.

## Recorrência

| Situação | Tratamento |
|---|---|
| Incluído hoje | Não volta no dia seguinte. |
| `Não atendeu` | Pode retornar somente no segundo dia útil posterior. |
| Três tentativas no mês | Fica bloqueado até a próxima competência. |
| Contato efetivo | Fica fora até a próxima competência. |
| `Número inválido` | Permanece bloqueado até correção cadastral. |

## Persistência

A carteira do dia, o controle de tentativas e cada interação são armazenados exclusivamente no PostgreSQL da TI. O Pegasus é consultado somente para leitura; a planilha ANATEL e o CSV municipal permanecem como arquivos locais de referência no servidor.
