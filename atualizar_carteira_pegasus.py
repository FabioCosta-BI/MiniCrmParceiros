"""Gera a carteira diária a partir do Pegasus e grava no PostgreSQL da TI."""
from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UFS_BRASIL = {"AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"}
GRUPOS_UF = {
    "Norte e Centro-Oeste": {"AC", "AM", "AP", "DF", "GO", "MA", "MS", "MT", "PA", "PI", "RO", "RR", "TO"},
    "Nordeste": {"AL", "BA", "CE", "PB", "PE", "RN", "SE"},
    "Sudeste e Sul": {"ES", "MG", "PR", "RJ", "RS", "SC", "SP"},
}
DETALHE_ESTRATEGICA = "A cidade compõe os primeiros 80% acumulados de acessos Starlink da UF, conforme ANATEL."


def caminho_ranking() -> Path:
    configurado = os.getenv("RANKING_ANATEL_PATH", "")
    return Path(configurado) if configurado else DATA_DIR / "Ranking de Cidades - Starlink.xlsx"


def cidades_estrategicas() -> set[int]:
    arquivo = caminho_ranking()
    if not arquivo.exists():
        raise FileNotFoundError(f"Arquivo ANATEL não encontrado: {arquivo}")
    ranking = pd.read_excel(arquivo, sheet_name="Ranking de Cidades - Starlink")
    ranking = ranking[["COD_IBGE", "UF", "ACESSOS STARLINK"]].copy()
    ranking["COD_IBGE"] = pd.to_numeric(ranking["COD_IBGE"], errors="coerce")
    ranking["ACESSOS STARLINK"] = pd.to_numeric(ranking["ACESSOS STARLINK"], errors="coerce").fillna(0)
    ranking = ranking[ranking["UF"].isin(UFS_BRASIL) & (ranking["ACESSOS STARLINK"] > 0)]
    ranking = ranking.sort_values(["UF", "ACESSOS STARLINK"], ascending=[True, False])
    ranking["acumulado"] = ranking.groupby("UF")["ACESSOS STARLINK"].cumsum()
    ranking["total"] = ranking.groupby("UF")["ACESSOS STARLINK"].transform("sum")
    return set(ranking.loc[ranking["acumulado"] - ranking["ACESSOS STARLINK"] < ranking["total"] * 0.8, "COD_IBGE"].dropna().astype(int))


def cidades_aniversariantes(hoje: date) -> set[int]:
    arquivo = DATA_DIR / "aniversarios_municipios_ibge.csv"
    if not arquivo.exists():
        raise FileNotFoundError(f"Arquivo de aniversários não encontrado: {arquivo}")
    dados = pd.read_csv(arquivo, encoding="utf-8-sig")
    dados["codigo_ibge"] = pd.to_numeric(dados["codigo_ibge"], errors="coerce")
    return set(dados.loc[(dados["dia"] == hoje.day) & (dados["mes"] == hoje.month), "codigo_ibge"].dropna().astype(int))


def preparar_base() -> pd.DataFrame:
    base = parceiros().merge(vendas(), on="id_wfm_b2b", how="left")
    base["vendas_starlink"] = pd.to_numeric(base["vendas_starlink"], errors="coerce").fillna(0).astype(int)
    base["cod_ibge"] = pd.to_numeric(base["cod_ibge"], errors="coerce")
    base["data_nascimento"] = pd.to_datetime(base["data_nascimento"], errors="coerce")
    municipios = pd.read_csv(DATA_DIR / "aniversarios_municipios_ibge.csv", encoding="utf-8-sig", usecols=["codigo_ibge", "municipio", "uf"])
    municipios = municipios.rename(columns={"codigo_ibge": "cod_ibge", "municipio": "cidade"})
    municipios["cod_ibge"] = pd.to_numeric(municipios["cod_ibge"], errors="coerce")
    base = base.merge(municipios.drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
    base = base[base["uf"].isin(UFS_BRASIL) & base["telefone"].notna() & base["cod_ibge"].notna()].copy()
    base["cod_ibge"] = base["cod_ibge"].astype(int)
    return base.drop_duplicates("id_wfm_b2b").sort_values(["vendas_starlink", "parceiro"], ascending=[False, True])


def item(linha: pd.Series, hoje: date, bloco: str, motivo: str) -> dict:
    detalhe = {
        "Parceiro em destaque de vendas": f"Parceiro selecionado entre os maiores volumes de vendas Starlink do bloco. {linha.vendas_starlink} vendas no recorte atual.",
        "Cidade estratégica": DETALHE_ESTRATEGICA,
        "Aniversário da cidade": "Aniversário da cidade-sede na data de hoje, conforme histórico municipal local.",
        "Aniversário do parceiro": "Aniversário do parceiro na data de hoje, conforme cadastro no Pegasus B2B.",
    }[motivo]
    return {
        "id_tarefa": f"{hoje:%Y%m%d}-{linha.id_wfm_b2b}", "data_carteira": hoje, "bloco_uf": bloco,
        "uf": linha.uf, "id_wfm_b2b": str(linha.id_wfm_b2b), "parceiro": linha.parceiro,
        "cidade": linha.cidade, "cod_ibge": int(linha.cod_ibge), "telefone": linha.telefone,
        "vendas_starlink": int(linha.vendas_starlink), "motivos": motivo,
        "prioridade": "Alta" if motivo == "Parceiro em destaque de vendas" else "Normal", "detalhe_regra": detalhe,
    }


def montar_carteira(base: pd.DataFrame, hoje: date, aplicar_controle: bool = True) -> list[dict]:
    if aplicar_controle:
        from postgres_contatos import controles, elegivel

        estado = controles(base["id_wfm_b2b"].astype(str).tolist(), hoje)
        base = base[base["id_wfm_b2b"].astype(str).map(lambda chave: elegivel(estado.get(chave), hoje))].copy()
    estrategicas, aniversariantes = cidades_estrategicas(), cidades_aniversariantes(hoje)
    limite_destaque = int(os.getenv("LIMITE_CAMPEOES_GRUPO", "6"))
    limite_estrategica = int(os.getenv("LIMITE_CIDADES_ESTRATEGICAS_GRUPO", "24"))
    limite_aniversario = int(os.getenv("LIMITE_ANIVERSARIOS_GRUPO", "5"))
    resultado: list[dict] = []
    for bloco, ufs in GRUPOS_UF.items():
        grupo = base[base["uf"].isin(ufs)].sort_values(["vendas_starlink", "parceiro"], ascending=[False, True])
        usados: set[str] = set()
        for motivo, candidatos, limite in (
            ("Parceiro em destaque de vendas", grupo, limite_destaque),
            ("Cidade estratégica", grupo[grupo["cod_ibge"].isin(estrategicas)], limite_estrategica),
            ("Aniversário da cidade", grupo[grupo["cod_ibge"].isin(aniversariantes)], limite_aniversario),
            ("Aniversário do parceiro", grupo[(grupo["data_nascimento"].dt.day == hoje.day) & (grupo["data_nascimento"].dt.month == hoje.month)], None),
        ):
            for _, linha in candidatos.iterrows():
                chave = str(linha.id_wfm_b2b)
                if chave not in usados:
                    resultado.append(item(linha, hoje, bloco, motivo))
                    usados.add(chave)
                    if limite is not None and sum(1 for x in resultado if x["bloco_uf"] == bloco and x["motivos"] == motivo) >= limite:
                        break
    return resultado


def gerar_teste_csv(hoje: date) -> None:
    """Recompõe um CSV já existente para validar a interface sem banco da TI.

    É apenas um recurso de desenvolvimento: produção sempre grava no PostgreSQL.
    """
    destino = DATA_DIR / f"carteira_{hoje.isoformat()}.csv"
    if not destino.exists():
        raise FileNotFoundError(f"Base de teste não encontrada: {destino}")
    base = pd.read_csv(destino, encoding="utf-8-sig")
    base["vendas_starlink"] = pd.to_numeric(base["vendas_starlink"], errors="coerce").fillna(0).astype(int)
    resultado: list[dict] = []
    for bloco, ufs in GRUPOS_UF.items():
        grupo = base[base["uf"].isin(ufs)].sort_values(["vendas_starlink", "parceiro"], ascending=[False, True])
        usados: set[str] = set()
        regras = (
            ("Parceiro em destaque de vendas", grupo, 6),
            ("Cidade estratégica", grupo[grupo["motivos"].str.contains("Cidade estratégica", na=False)], 24),
            ("Aniversário da cidade", grupo[grupo["motivos"].str.contains("Aniversário da cidade", na=False)], 5),
        )
        for motivo, candidatos, limite in regras:
            quantidade = 0
            for _, linha in candidatos.iterrows():
                chave = str(linha["id_wfm_b2b"])
                if chave in usados:
                    continue
                item_teste = linha.to_dict()
                item_teste["bloco_uf"] = bloco
                item_teste["motivos"] = motivo
                item_teste["prioridade"] = "Alta" if motivo == "Parceiro em destaque de vendas" else "Normal"
                item_teste["detalhe_regra"] = (
                    f"Parceiro selecionado entre os maiores volumes de vendas Starlink do bloco. {linha['vendas_starlink']} vendas no recorte atual."
                    if motivo == "Parceiro em destaque de vendas" else DETALHE_ESTRATEGICA
                    if motivo == "Cidade estratégica" else "Aniversário da cidade-sede na data de hoje."
                )
                resultado.append(item_teste)
                usados.add(chave)
                quantidade += 1
                if quantidade == limite:
                    break
    colunas = ["id_tarefa", "data_carteira", "bloco_uf", "consultor_responsavel", "uf", "id_wfm_b2b", "parceiro", "cidade", "telefone", "vendas_starlink", "motivos", "prioridade", "detalhe_regra"]
    pd.DataFrame(resultado).reindex(columns=colunas).to_csv(destino, index=False, encoding="utf-8-sig")
    print(f"TESTE: {len(resultado)} parceiros gravados em {destino.name}.")


def gerar_teste_pegasus(hoje: date) -> None:
    """Gera CSV local com fonte real, reaproveitando a configuração local do DW."""
    env_dw = BASE_DIR.parent / "DW" / ".env"
    if not env_dw.exists():
        raise FileNotFoundError(f"Configuração do DW não encontrada: {env_dw}")
    load_dotenv(env_dw, override=False)
    equivalencias = {
        "PEGASUS_PG_HOST": "PGHOST", "PEGASUS_PG_PORT": "PGPORT",
        "PEGASUS_PG_DATABASE": "PGDATABASE", "PEGASUS_PG_USER": "PGUSER",
        "PEGASUS_PG_PASSWORD": "PGPASSWORD", "PEGASUS_ODBC_DSN": "ODBC_DSN",
    }
    for destino, origem in equivalencias.items():
        if not os.getenv(destino) and os.getenv(origem):
            os.environ[destino] = os.environ[origem]
    global parceiros, vendas
    from fontes_pegasus import parceiros, vendas

    carteira = montar_carteira(preparar_base(), hoje, aplicar_controle=False)
    for item_carteira in carteira:
        item_carteira["consultor_responsavel"] = "Sem atribuição"
    destino = DATA_DIR / f"carteira_{hoje.isoformat()}.csv"
    colunas = ["id_tarefa", "data_carteira", "bloco_uf", "consultor_responsavel", "uf", "id_wfm_b2b", "parceiro", "cidade", "telefone", "vendas_starlink", "motivos", "prioridade", "detalhe_regra"]
    pd.DataFrame(carteira).reindex(columns=colunas).to_csv(destino, index=False, encoding="utf-8-sig")
    print(f"TESTE PEGASUS: {len(carteira)} parceiros gravados em {destino.name}.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--substituir", action="store_true", help="recria a carteira da data informada")
    parser.add_argument("--data", type=date.fromisoformat, default=date.today(), help="AAAA-MM-DD; padrão: hoje")
    parser.add_argument("--teste-csv", action="store_true", help="recompõe o CSV existente apenas para validar a interface")
    parser.add_argument("--teste-pegasus", action="store_true", help="gera CSV de teste com fonte real, sem gravar no PostgreSQL")
    args = parser.parse_args()
    load_dotenv(BASE_DIR / ".env")
    hoje = args.data
    if args.teste_csv:
        gerar_teste_csv(hoje)
        return
    if args.teste_pegasus:
        gerar_teste_pegasus(hoje)
        return
    from fontes_pegasus import parceiros, vendas
    from postgres_contatos import existe_carteira, registrar_oferta, substituir_carteira
    if existe_carteira(hoje) and not args.substituir:
        raise RuntimeError("Já existe carteira para esta data. Use --substituir somente se ela ainda não foi trabalhada.")
    carteira = montar_carteira(preparar_base(), hoje)
    if not carteira:
        raise RuntimeError("Nenhum parceiro elegível foi encontrado para a carteira.")
    substituir_carteira(carteira, hoje)
    registrar_oferta(carteira, hoje)
    print(f"OK: {len(carteira)} parceiros gravados no PostgreSQL para {hoje:%d/%m/%Y}.")


if __name__ == "__main__":
    main()
