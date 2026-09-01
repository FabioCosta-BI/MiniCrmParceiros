"""Migra o histórico CSV legado para o BigQuery uma única vez.

Execute: py migrar_historico_csv_bigquery.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from server import BQ_TABLE_ID, bigquery_client, garantir_tabela_historico


ARQUIVO_LEGADO = Path(__file__).parent / "data" / "historico_ligacoes.csv"


def main() -> None:
    if not ARQUIVO_LEGADO.exists():
        print("Não há histórico CSV legado para migrar.")
        return

    garantir_tabela_historico()
    existentes = {
        row["id_interacao"]
        for row in bigquery_client().list_rows(BQ_TABLE_ID, retry=None, timeout=15)
    }

    with ARQUIVO_LEGADO.open("r", encoding="utf-8-sig", newline="") as arquivo:
        legado = list(csv.DictReader(arquivo))

    linhas = []
    for item in legado:
        if not item.get("id_interacao") or item["id_interacao"] in existentes:
            continue
        linhas.append({
            "id_interacao": item["id_interacao"],
            "data_hora": item.get("data_hora"),
            "id_tarefa": item.get("id_tarefa"),
            "data_carteira": None,
            "consultor": item.get("consultor"),
            "uf": item.get("uf"),
            "id_wfm_b2b": item.get("id_wfm_b2b"),
            "parceiro": None,
            "cidade": None,
            "motivos": None,
            "resultado": item.get("resultado"),
            "observacao": item.get("observacao"),
            "proximo_retorno": item.get("proximo_retorno") or None,
        })

    if not linhas:
        print("Histórico já está no BigQuery.")
        return

    erros = bigquery_client().insert_rows_json(
        BQ_TABLE_ID, linhas, row_ids=[linha["id_interacao"] for linha in linhas], retry=None, timeout=15
    )
    if erros:
        raise RuntimeError(f"Falha ao migrar histórico: {erros}")
    print(f"{len(linhas)} interação(ões) migrada(s) para o BigQuery.")


if __name__ == "__main__":
    main()
