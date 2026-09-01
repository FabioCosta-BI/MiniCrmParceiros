"""Gera a carteira inicial com parceiros reais do BigQuery, sem enviar e-mails.

O recorte inicial é por maior número de vendas Starlink, separado conforme a divisão
de UFs dos três consultores. As regras de aniversário e Pareto por cidade entrarão
na próxima etapa, quando a base municipal estiver disponível.
"""

from __future__ import annotations

import csv
import os
import argparse
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery

from postgres_contatos import controles, elegivel, registrar_oferta


BASE_DIR = Path(__file__).parent
ENV_LOCAL = BASE_DIR / ".env"
ENV_ORIGEM = BASE_DIR.parent / "PowerBI" / "Scripts" / "Indicador_campo_envio" / ".env"
OUTPUT_DIR = BASE_DIR / "data"
RANKING_ANATEL = BASE_DIR.parent / "PowerBI" / "Scripts" / "Indicador_campo_envio" / "Ranking de Cidades - Starlink.xlsx"
UFS_BRASIL = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
    "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]
CAMPOS = [
    "id_tarefa", "data_carteira", "consultor_responsavel", "uf", "id_wfm_b2b",
    "parceiro", "cidade", "telefone", "vendas_starlink", "motivos", "prioridade", "detalhe_regra",
]


def tabela(nome: str) -> str:
    return f"`{os.environ['BQ_PROJECT_ID']}.{os.environ['BQ_DATASET']}.{nome}`"


def buscar_parceiros() -> list[dict]:
    ufs = UFS_BRASIL
    query = f"""
        WITH vendas AS (
            SELECT CAST(id_instaladora AS STRING) AS id_wfm_b2b, COUNT(*) AS vendas_starlink
            FROM {tabela('fato_venda_starlink')}
            WHERE LOWER(TRIM(COALESCE(account_status, ''))) <> 'cancelled'
              AND SAFE_CAST(id_instaladora AS INT64) > 0
            GROUP BY 1
        ), parceiros AS (
            SELECT
                CAST(i.id_wfm_b2b AS STRING) AS id_wfm_b2b,
                i.nome_empresa AS parceiro,
                COALESCE(i.telefone_celular_whatsapp, i.telefone_celular,
                         i.telefone_comercial, i.telefone_residencial) AS telefone,
                d.municipio AS cidade, d.cod_ibge,
                d.uf,
                ROW_NUMBER() OVER (
                    PARTITION BY i.id_wfm_b2b
                    ORDER BY IF(c.tipo_vinculo = 'Sede', 0, 1), d.municipio
                ) AS linha
            FROM {tabela('fato_cobertura')} AS c
            JOIN {tabela('dim_instaladora')} AS i ON i.id_instaladora = c.id_instaladora
            JOIN {tabela('dim_cidade')} AS d ON d.cod_ibge = c.cod_ibge
            WHERE d.uf IN UNNEST(@ufs)
              AND i.id_wfm_b2b IS NOT NULL
              AND NULLIF(TRIM(COALESCE(i.telefone_celular_whatsapp, i.telefone_celular,
                  i.telefone_comercial, i.telefone_residencial)), '') IS NOT NULL
        )
        SELECT p.id_wfm_b2b, p.parceiro, p.telefone, p.cidade, p.cod_ibge, p.uf,
               COALESCE(v.vendas_starlink, 0) AS vendas_starlink
        FROM parceiros AS p
        LEFT JOIN vendas AS v USING (id_wfm_b2b)
        WHERE p.linha = 1
        ORDER BY vendas_starlink DESC, p.parceiro
    """
    client = bigquery.Client(project=os.environ["BQ_PROJECT_ID"])
    job = client.query(query, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("ufs", "STRING", ufs)]
    ))
    return [dict(row) for row in job.result()]


def buscar_cidades_estrategicas() -> set[int]:
    """Cidades dos primeiros 80% de acessos Starlink da ANATEL, por UF."""
    ranking = pd.read_excel(RANKING_ANATEL, sheet_name="Ranking de Cidades - Starlink")
    ranking = ranking[["COD_IBGE", "UF", "ACESSOS STARLINK"]].copy()
    ranking["COD_IBGE"] = pd.to_numeric(ranking["COD_IBGE"], errors="coerce")
    ranking["ACESSOS STARLINK"] = pd.to_numeric(ranking["ACESSOS STARLINK"], errors="coerce").fillna(0)
    ranking = ranking[ranking["UF"].isin(UFS_BRASIL)]
    ranking = ranking[ranking["ACESSOS STARLINK"] > 0].sort_values(["UF", "ACESSOS STARLINK"], ascending=[True, False])
    ranking["acumulado"] = ranking.groupby("UF")["ACESSOS STARLINK"].cumsum()
    ranking["total_uf"] = ranking.groupby("UF")["ACESSOS STARLINK"].transform("sum")
    # Inclui também a cidade que cruza a barreira dos 80%.
    return set(ranking.loc[ranking["acumulado"] - ranking["ACESSOS STARLINK"] < ranking["total_uf"] * 0.8, "COD_IBGE"].astype(int))


def cidades_aniversariantes_hoje() -> dict[int, dict[str, str]]:
    """Cidades com data histórica candidata para o aniversário de hoje."""
    arquivo = OUTPUT_DIR / "aniversarios_municipios_ibge.csv"
    if not arquivo.exists():
        return {}
    hoje = date.today()
    resultado: dict[int, dict[str, str]] = {}
    with arquivo.open(encoding="utf-8-sig", newline="") as origem:
        for linha in csv.DictReader(origem):
            try:
                codigo = int(str(linha.get("codigo_ibge", "")).strip())
                dia = int(str(linha.get("dia", "")).strip())
                mes = int(str(linha.get("mes", "")).strip())
            except ValueError:
                continue
            if dia == hoje.day and mes == hoje.month:
                resultado[codigo] = {
                    "criterio": linha.get("criterio", "histórico IBGE"),
                    "confianca": linha.get("confianca", ""),
                }
    return resultado


def montar_carteira(parceiros: list[dict], cidades_estrategicas: set[int]) -> list[dict[str, str]]:
    cidades_aniversariantes = cidades_aniversariantes_hoje()
    selecionados: dict[str, list[str]] = {}
    # Até três campeões por UF, dentro do Pareto de 80% das vendas daquela UF.
    for uf in UFS_BRASIL:
        parceiros_uf = [p for p in parceiros if p["uf"] == uf]
        total_vendas = sum(int(p["vendas_starlink"]) for p in parceiros_uf)
        acumulado = 0
        campeoes_pareto = []
        for parceiro in parceiros_uf:
            if acumulado >= total_vendas * 0.8:
                break
            campeoes_pareto.append(parceiro)
            acumulado += int(parceiro["vendas_starlink"])
        for parceiro in campeoes_pareto[:3]:
            selecionados.setdefault(parceiro["id_wfm_b2b"], []).append("Campeão de vendas")
    # Até dez contatos estratégicos por UF.
    for uf in UFS_BRASIL:
        elegiveis = [
            p for p in parceiros
            if p["uf"] == uf
            and int(p["cod_ibge"]) in cidades_estrategicas
            and int(p["vendas_starlink"]) > 0
        ]
        for parceiro in elegiveis[:10]:
            selecionados.setdefault(parceiro["id_wfm_b2b"], []).append("Cidade estratégica")
    for parceiro in parceiros:
        if int(parceiro["cod_ibge"]) in cidades_aniversariantes:
            selecionados.setdefault(parceiro["id_wfm_b2b"], []).append("Aniversário da cidade")
    hoje = date.today().isoformat()
    resultado = []
    for item in parceiros:
        motivos = selecionados.get(item["id_wfm_b2b"])
        if motivos:
            detalhes = []
            if "Campeão de vendas" in motivos:
                detalhes.append(f"Campeão de vendas: {item['vendas_starlink']} vendas Starlink no recorte atual.")
            if "Cidade estratégica" in motivos:
                detalhes.append(
                    "Parceiro em cidade estratégica: a cidade compõe os primeiros 80% acumulados "
                    "de acessos Starlink da UF, conforme ANATEL."
                )
            if "Aniversário da cidade" in motivos:
                dados_aniversario = cidades_aniversariantes[int(item["cod_ibge"])]
                detalhes.append(
                    f"Aniversário da cidade hoje: critério {dados_aniversario['criterio']} no histórico do IBGE."
                )
            resultado.append({
                "id_tarefa": f"{hoje.replace('-', '')}-{item['id_wfm_b2b']}", "data_carteira": hoje,
                "consultor_responsavel": "Sem atribuição", "uf": item["uf"], "id_wfm_b2b": item["id_wfm_b2b"],
                "parceiro": item["parceiro"], "cidade": item["cidade"], "telefone": item["telefone"],
                "vendas_starlink": item["vendas_starlink"],
                "motivos": "; ".join(motivos),
                "prioridade": "Alta" if "Campeão de vendas" in motivos else "Normal",
                "detalhe_regra": " ".join(detalhes),
            })
    return resultado


def main() -> None:
    argumentos = argparse.ArgumentParser()
    argumentos.add_argument("--substituir", action="store_true", help="substitui a carteira já criada para hoje")
    args = argumentos.parse_args()
    # No servidor, o CRM usa seu próprio .env. O arquivo legado só mantém
    # compatibilidade com a instalação de desenvolvimento atual.
    load_dotenv(ENV_LOCAL if ENV_LOCAL.exists() else ENV_ORIGEM)
    faltando = [chave for chave in ("BQ_PROJECT_ID", "BQ_DATASET") if not os.environ.get(chave)]
    if faltando:
        raise RuntimeError(f"Configuração BigQuery ausente: {', '.join(faltando)}")
    parceiros = buscar_parceiros()
    carteira = montar_carteira(parceiros, buscar_cidades_estrategicas())
    hoje = date.today()
    estado = controles([item["id_wfm_b2b"] for item in carteira], hoje)
    disponiveis = [item for item in carteira if elegivel(estado.get(item["id_wfm_b2b"]), hoje)]
    limite_campeoes = int(os.getenv("LIMITE_CAMPEOES_DIA", "3"))
    limite_estrategicos = int(os.getenv("LIMITE_CIDADES_ESTRATEGICAS_DIA", "10"))
    campeoes = sorted((item for item in disponiveis if "Campeão de vendas" in item["motivos"]), key=lambda item: int(item["vendas_starlink"]), reverse=True)[:limite_campeoes]
    ja_selecionados = {item["id_wfm_b2b"] for item in campeoes}
    estrategicos = sorted((item for item in disponiveis if "Cidade estratégica" in item["motivos"] and item["id_wfm_b2b"] not in ja_selecionados), key=lambda item: int(item["vendas_starlink"]), reverse=True)[:limite_estrategicos]
    aniversariantes = [item for item in disponiveis if "Aniversário da cidade" in item["motivos"] and item["id_wfm_b2b"] not in ja_selecionados]
    carteira = campeoes + estrategicos + aniversariantes
    if not carteira:
        raise RuntimeError("A consulta não retornou parceiros com telefone e vendas.")
    tabela_carteira = tabela(os.getenv("BQ_CARTEIRA_TABELA", "crm_carteira_diaria"))
    client = bigquery.Client(project=os.environ["BQ_PROJECT_ID"])
    client.query(f"DELETE FROM {tabela_carteira} WHERE data_carteira = @data", job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("data", "DATE", hoje)])).result()
    linhas = [{**item, "criado_em": datetime.now().astimezone().isoformat()} for item in carteira]
    erros = client.insert_rows_json(tabela_carteira, linhas, row_ids=[item["id_tarefa"] for item in linhas])
    if erros:
        raise RuntimeError(f"Falha ao gravar carteira no BigQuery: {erros}")
    registrar_oferta(carteira, hoje)
    print(f"OK: {len(carteira)} parceiros gravados em {tabela_carteira}")


if __name__ == "__main__":
    main()
