"""Gera uma base auditável de datas de aniversário dos municípios a partir do IBGE.

Fonte: https://servicodados.ibge.gov.br/api/v1/biblioteca?aspas=3&codmun=<codigo_ibge>

O IBGE oferece textos históricos, e não um campo pronto chamado "aniversário".
Por isso, este script extrai uma data candidata e preserva a frase de origem,
o critério e a confiança para revisão posterior.

Exemplos:
    py gerar_aniversarios_municipios_ibge.py --codigo 4106902 --sem-salvar
    py gerar_aniversarios_municipios_ibge.py --uf PR
    py gerar_aniversarios_municipios_ibge.py
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DEFAULT = BASE_DIR / "data" / "aniversarios_municipios_ibge.csv"
URL_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
URL_HISTORICO = "https://servicodados.ibge.gov.br/api/v1/biblioteca?aspas=3&codmun={}"
MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto or "")
    return "".join(char for char in texto if unicodedata.category(char) != "Mn").lower()


def requisitar_json(url: str) -> object:
    request = Request(url, headers={"User-Agent": "MiniCRMParceiros/1.0"})
    with urlopen(request, timeout=45) as response:
        conteudo = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            conteudo = gzip.decompress(conteudo)
        return json.loads(conteudo.decode("utf-8"))


def obter_uf(registro: dict) -> str:
    """Compatível com a estrutura atual e com versões anteriores do endpoint."""
    try:
        return registro["microrregiao"]["mesorregiao"]["UF"]["sigla"]
    except (KeyError, TypeError):
        try:
            return registro["regiao-imediata"]["regiao-intermediaria"]["UF"]["sigla"]
        except (KeyError, TypeError):
            return ""


def obter_municipios(uf: str | None, codigo: str | None, limite: int | None) -> list[dict]:
    municipios = requisitar_json(URL_MUNICIPIOS)
    resultado = []
    for municipio in municipios:
        codigo_ibge = str(municipio.get("id", ""))
        uf_municipio = obter_uf(municipio)
        if codigo and codigo_ibge != codigo:
            continue
        if uf and uf_municipio != uf.upper():
            continue
        resultado.append({
            "codigo_ibge": codigo_ibge,
            "municipio": municipio.get("nome", ""),
            "uf": uf_municipio,
        })
    return resultado[:limite] if limite else resultado


def frases(texto: str) -> list[str]:
    texto = re.sub(r"\s+", " ", texto or "").strip()
    return [frase.strip() for frase in re.split(r"(?<=[.!?])\s+", texto) if frase.strip()]


def datas_na_frase(frase: str) -> list[tuple[datetime, int]]:
    achadas: list[tuple[datetime, int]] = []
    for match in re.finditer(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", frase):
        dia, mes, ano = map(int, match.groups())
        try:
            achadas.append((datetime(ano, mes, dia), match.start()))
        except ValueError:
            pass
    for match in re.finditer(r"\b(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})\b", normalizar(frase)):
        dia, mes_nome, ano = match.groups()
        if mes_nome in MESES:
            achadas.append((datetime(int(ano), MESES[mes_nome], int(dia)), match.start()))
    return achadas


def data_mais_proxima(frase: str, posicao: int) -> datetime | None:
    datas = datas_na_frase(frase)
    if not datas:
        return None
    return min(datas, key=lambda item: abs(item[1] - posicao))[0]


REGRAS = [
    ("fundacao", "alta", r"\b(?:fundad[oa]|fundacao|aniversario)\b"),
    ("elevacao_vila", "alta", r"elevad[oa].{0,55}categoria de vila"),
    ("elevacao_municipio", "media", r"elevad[oa].{0,65}categoria de municipio"),
    ("instalacao", "baixa", r"\binstalad[oa]\b"),
]


def extrair_aniversario(historico: str, formacao: str) -> dict | None:
    """Retorna a melhor data candidata, sem esconder a evidência textual."""
    fontes = [("historico", historico), ("formacao_administrativa", formacao)]
    for criterio, confianca, padrao in REGRAS:
        regex = re.compile(padrao, re.IGNORECASE)
        for origem, texto in fontes:
            for frase in frases(texto):
                match = regex.search(normalizar(frase))
                if not match:
                    continue
                data = data_mais_proxima(frase, match.start())
                if data:
                    return {
                        "data": data,
                        "criterio": criterio,
                        "confianca": confianca,
                        "campo_origem": origem,
                        "frase_origem": frase,
                    }
    return None


def buscar_historico(codigo_ibge: str) -> dict:
    resposta = requisitar_json(URL_HISTORICO.format(codigo_ibge))
    return resposta.get(codigo_ibge, {}) if isinstance(resposta, dict) else {}


def executar(args: argparse.Namespace) -> list[dict]:
    municipios = obter_municipios(args.uf, args.codigo, args.limite)
    if not municipios:
        raise RuntimeError("Nenhum município encontrado para os filtros informados.")

    print(f"Municípios a consultar: {len(municipios)}")
    resultados: list[dict] = []
    for indice, municipio in enumerate(municipios, start=1):
        codigo = municipio["codigo_ibge"]
        try:
            dado = buscar_historico(codigo)
            extraido = extrair_aniversario(
                dado.get("HISTORICO", ""),
                dado.get("FORMACAO_ADMINISTRATIVA", ""),
            )
            resultado = {
                **municipio,
                "dia": extraido["data"].day if extraido else "",
                "mes": extraido["data"].month if extraido else "",
                "data_referencia": extraido["data"].strftime("%d/%m/%Y") if extraido else "",
                "criterio": extraido["criterio"] if extraido else "nao_identificado",
                "confianca": extraido["confianca"] if extraido else "sem_data",
                "campo_origem": extraido["campo_origem"] if extraido else "",
                "frase_origem": extraido["frase_origem"] if extraido else "",
                "fonte_historico": dado.get("HISTORICO_FONTE", ""),
                "status_consulta": "ok" if dado else "sem_historico",
            }
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as erro:
            resultado = {
                **municipio,
                "dia": "", "mes": "", "data_referencia": "",
                "criterio": "erro_consulta", "confianca": "sem_data",
                "campo_origem": "", "frase_origem": "", "fonte_historico": "",
                "status_consulta": f"erro: {erro}",
            }
        resultados.append(resultado)
        print(f"[{indice}/{len(municipios)}] {municipio['uf']} - {municipio['municipio']}: {resultado['criterio']}")
        if args.pausa:
            time.sleep(args.pausa)
    return resultados


def salvar(resultados: list[dict], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    campos = [
        "codigo_ibge", "municipio", "uf", "dia", "mes", "data_referencia",
        "criterio", "confianca", "campo_origem", "frase_origem",
        "fonte_historico", "status_consulta",
    ]
    with caminho.open("w", newline="", encoding="utf-8-sig") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=campos)
        writer.writeheader()
        writer.writerows(resultados)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uf", help="Processa apenas uma UF, por exemplo PR.")
    parser.add_argument("--codigo", help="Processa um único código IBGE, para teste.")
    parser.add_argument("--limite", type=int, help="Limita a quantidade de municípios processados.")
    parser.add_argument("--pausa", type=float, default=0.15, help="Pausa entre requisições (padrão: 0,15 s).")
    parser.add_argument("--saida", type=Path, default=OUTPUT_DEFAULT, help="Caminho do CSV gerado.")
    parser.add_argument("--sem-salvar", action="store_true", help="Exibe o resultado sem gravar CSV.")
    args = parser.parse_args()

    try:
        resultados = executar(args)
    except RuntimeError as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1

    encontrados = sum(1 for item in resultados if item["criterio"] != "nao_identificado")
    print(f"Datas candidatas encontradas: {encontrados}/{len(resultados)}")
    if not args.sem_salvar:
        salvar(resultados, args.saida)
        print(f"Arquivo gerado: {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
