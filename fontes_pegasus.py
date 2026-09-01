"""Consultas somente de leitura ao Pegasus B2B.

Os filtros reproduzem o DW. Este módulo nunca cria nem altera objetos na origem.
"""
from __future__ import annotations

import os
import re

import pandas as pd
import psycopg
import pyodbc


QUERY_PARCEIROS = """
SELECT
  a.cp_a001_id_instaladora::text AS id_wfm_b2b,
  a.a023_idinstaladora AS id_instaladora,
  a.a023_nome AS parceiro,
  a.a023_dtnasto AS data_nascimento,
  cid.cod_ibge
FROM tb023_gcinstaladoras a
LEFT JOIN tb_cidades cid ON cid.id = a.a023_idcidade
WHERE a.a023_tipo_operacao LIKE '%STARLINK%'
  AND a.a023_pessoa = 'J'
  AND a.a023_cpf_cnpj <> '123'
  AND a.cp_a001_id_instaladora IS NOT NULL
  AND TRIM(a.cp_a001_id_instaladora::text) <> '0'
  AND a.a023_idcidade IS NOT NULL
"""

QUERY_CONTATOS = """
SELECT a023_idinstaladora AS id_instaladora, a024_tipo AS tipo, a024_contato AS contato
FROM tb024_gccontatos
WHERE a024_tipo IN ('CELULAR/WHATSAPP', 'CELULAR', 'TELEFONE COMERCIAL', 'TELEFONE RESIDENCIAL')
"""

QUERY_VENDAS = """
SELECT CAST(a001_id_instaladora AS VARCHAR(80)) AS id_wfm_b2b, COUNT(*) AS vendas_starlink
FROM vw_cp_vendas_starlink
WHERE LOWER(TRIM(COALESCE(a144_account_status, ''))) <> 'cancelled'
GROUP BY a001_id_instaladora
"""


def _telefone(valor: object) -> str | None:
    """Aplica a limpeza básica já utilizada na dim_instaladora do DW."""
    if not isinstance(valor, str):
        return None
    for trecho in re.split(r"[/;]", valor):
        numero = re.sub(r"[^0-9]", "", trecho)
        if numero.startswith("55") and len(numero) in (12, 13):
            numero = numero[2:]
        if numero.startswith("0") and len(numero) in (11, 12):
            numero = numero[1:]
        if len(numero) in (10, 11) and 11 <= int(numero[:2]) <= 99:
            return numero
    return None


def parceiros() -> pd.DataFrame:
    """Cadastro Starlink PJ, na cidade-sede, com o melhor telefone disponível."""
    parametros = {
        "host": os.environ["PEGASUS_PG_HOST"], "port": os.getenv("PEGASUS_PG_PORT", "5432"),
        "dbname": os.environ["PEGASUS_PG_DATABASE"], "user": os.environ["PEGASUS_PG_USER"],
        "password": os.environ["PEGASUS_PG_PASSWORD"], "client_encoding": "latin1",
    }
    with psycopg.connect(**parametros) as conn:
        base = pd.read_sql(QUERY_PARCEIROS, conn)
        contatos = pd.read_sql(QUERY_CONTATOS, conn)
    contatos["telefone"] = contatos["contato"].map(_telefone)
    contatos["ordem"] = contatos["tipo"].map({
        "CELULAR/WHATSAPP": 1, "CELULAR": 2, "TELEFONE COMERCIAL": 3, "TELEFONE RESIDENCIAL": 4,
    })
    contatos = contatos.dropna(subset=["telefone"]).sort_values(["id_instaladora", "ordem"])
    melhor = contatos.drop_duplicates("id_instaladora")[["id_instaladora", "telefone"]]
    return base.merge(melhor, on="id_instaladora", how="left").drop(columns="id_instaladora")


def vendas() -> pd.DataFrame:
    """Vendas Starlink não canceladas, via a mesma view ODBC do DW."""
    with pyodbc.connect(f"DSN={os.environ['PEGASUS_ODBC_DSN']}", timeout=30) as conn:
        return pd.read_sql(QUERY_VENDAS, conn)
