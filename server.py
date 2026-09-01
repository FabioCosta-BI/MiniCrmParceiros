"""Protótipo local do CRM de parceiros.

Não usa banco de dados: a carteira diária e o histórico são CSVs em data/.
Execute com: py server.py
Depois abra: http://localhost:8787
"""

from __future__ import annotations

import csv
import json
import os
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from dotenv import load_dotenv
from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import TransportError
from google.cloud import bigquery


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
INTERACOES_FILE = DATA_DIR / "historico_ligacoes_backup.csv"
LOCK = threading.Lock()
load_dotenv(BASE_DIR / ".env")
BQ_PROJECT_ID = os.environ.get("BQ_PROJECT_ID", "")
BQ_DATASET = os.environ.get("BQ_DATASET", "")
BQ_HISTORICO_TABELA = os.environ.get("BQ_HISTORICO_TABELA", "historico_ligacoes_crm")
BQ_TABLE_ID = f"{BQ_PROJECT_ID}.{BQ_DATASET}.{BQ_HISTORICO_TABELA}"
BQ_CLIENT: bigquery.Client | None = None
UFS_BRASIL = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
    "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]

CARTEIRA_COLUNAS = [
    "id_tarefa", "data_carteira", "consultor_responsavel", "uf", "id_wfm_b2b",
    "parceiro", "cidade", "telefone", "motivos", "prioridade", "detalhe_regra",
]
INTERACAO_COLUNAS = [
    "id_interacao", "data_hora", "id_tarefa", "data_carteira", "consultor", "uf", "id_wfm_b2b",
    "parceiro", "cidade", "motivos", "resultado", "observacao", "proximo_retorno",
]


def bigquery_client() -> bigquery.Client:
    """Retorna uma conexão reutilizável e valida a configuração mínima."""
    global BQ_CLIENT
    if not BQ_PROJECT_ID or not BQ_DATASET:
        raise RuntimeError("BigQuery não configurado. Preencha BQ_PROJECT_ID e BQ_DATASET no arquivo .env.")
    if BQ_CLIENT is None:
        BQ_CLIENT = bigquery.Client(project=BQ_PROJECT_ID)
    return BQ_CLIENT


def garantir_tabela_historico() -> None:
    """Cria a tabela de histórico caso ela ainda não exista."""
    client = bigquery_client()
    schema = [
        bigquery.SchemaField("id_interacao", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("data_hora", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("id_tarefa", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("data_carteira", "DATE"),
        bigquery.SchemaField("consultor", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("uf", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("id_wfm_b2b", "STRING"),
        bigquery.SchemaField("parceiro", "STRING"),
        bigquery.SchemaField("cidade", "STRING"),
        bigquery.SchemaField("motivos", "STRING"),
        bigquery.SchemaField("resultado", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("observacao", "STRING"),
        bigquery.SchemaField("proximo_retorno", "DATE"),
    ]
    table = bigquery.Table(BQ_TABLE_ID, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(field="data_hora")
    client.create_table(table, exists_ok=True, retry=None, timeout=15)


def interacoes_bigquery() -> list[dict[str, str]]:
    """Lê as interações oficiais para indicar o último status de cada tarefa."""
    garantir_tabela_historico()
    rows = bigquery_client().list_rows(BQ_TABLE_ID, retry=None, timeout=15)
    return [
        {
            "id_tarefa": row["id_tarefa"],
            "data_hora": row["data_hora"].isoformat() if row["data_hora"] else "",
            "resultado": row["resultado"],
            "proximo_retorno": row["proximo_retorno"].isoformat() if row["proximo_retorno"] else "",
        }
        for row in rows
    ]


def salvar_interacao_bigquery(row: dict[str, str]) -> None:
    garantir_tabela_historico()
    erros = bigquery_client().insert_rows_json(
        BQ_TABLE_ID, [row], row_ids=[row["id_interacao"]], retry=None, timeout=15
    )
    if erros:
        raise RuntimeError(f"Não foi possível gravar a ligação no BigQuery: {erros[0].get('errors', erros)}")


def seed_files() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not list(DATA_DIR.glob("carteira_*.csv")):
        carteira_file = DATA_DIR / "carteira_2026-08-31.csv"
        rows = [
            ["20260831-001", "2026-08-31", "Ana Martins", "BA", "51001", "Bahia Conecta", "Salvador", "(71) 99921-4830", "Campeão de vendas", "Alta", "Top parceiros: 80% das vendas Vivensis"],
            ["20260831-002", "2026-08-31", "Ana Martins", "CE", "51002", "Ceará Sat", "Fortaleza", "(85) 99877-1021", "Cidade estratégica", "Alta", "Fortaleza compõe os primeiros 80% das vendas do estado"],
            ["20260831-003", "2026-08-31", "Ana Martins", "PE", "51003", "Nordeste Link", "Recife", "(81) 99141-6550", "Aniversário da cidade", "Normal", "Data comemorativa municipal"],
            ["20260831-004", "2026-08-31", "Ana Martins", "PB", "51004", "PB Tecnologia", "João Pessoa", "(83) 98891-4302", "Aniversário do parceiro", "Normal", "Data de aniversário do contato"],
            ["20260831-005", "2026-08-31", "Bruno Lima", "SP", "52001", "São Paulo Digital", "São Paulo", "(11) 99742-0175", "Campeão de vendas; Cidade estratégica", "Alta", "Parceiro e cidade prioritários"],
            ["20260831-006", "2026-08-31", "Bruno Lima", "MG", "52002", "Minas Conecta", "Uberlândia", "(34) 99215-8231", "Cidade estratégica", "Alta", "Uberlândia compõe os primeiros 80% das vendas do estado"],
            ["20260831-007", "2026-08-31", "Bruno Lima", "RJ", "52003", "Rio Star Serviços", "Niterói", "(21) 99856-1194", "Aniversário da cidade", "Normal", "Data comemorativa municipal"],
            ["20260831-008", "2026-08-31", "Bruno Lima", "GO", "52004", "Centro Oeste Sat", "Goiânia", "(62) 99106-3012", "Aniversário do parceiro", "Normal", "Data de aniversário do contato"],
            ["20260831-009", "2026-08-31", "Carla Souza", "PR", "53001", "Paraná Conexões", "Curitiba", "(41) 99724-6014", "Campeão de vendas", "Alta", "Top parceiros: 80% das vendas Vivensis"],
            ["20260831-010", "2026-08-31", "Carla Souza", "SC", "53002", "Sul Link", "Joinville", "(47) 99148-7602", "Cidade estratégica", "Alta", "Joinville compõe os primeiros 80% das vendas do estado"],
            ["20260831-011", "2026-08-31", "Carla Souza", "PA", "53003", "Amazônia Sat", "Belém", "(91) 99623-3310", "Aniversário da cidade", "Normal", "Data comemorativa municipal"],
            ["20260831-012", "2026-08-31", "Carla Souza", "AM", "53004", "Norte Digital", "Manaus", "(92) 99201-8900", "Aniversário do parceiro", "Normal", "Data de aniversário do contato"],
        ]
        with carteira_file.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(CARTEIRA_COLUNAS)
            writer.writerows(rows)
    if not INTERACOES_FILE.exists():
        with INTERACOES_FILE.open("w", newline="", encoding="utf-8-sig") as file:
            csv.DictWriter(file, fieldnames=INTERACAO_COLUNAS).writeheader()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def carteira_file_atual() -> Path:
    arquivos = sorted(DATA_DIR.glob("carteira_*.csv"))
    if not arquivos:
        raise FileNotFoundError("Nenhuma carteira diária encontrada.")
    return arquivos[-1]


def carteira(ufs: set[str]) -> list[dict[str, str]]:
    tasks = [row for row in read_csv(carteira_file_atual()) if row["uf"] in ufs]
    interactions = interacoes_bigquery()
    latest: dict[str, dict[str, str]] = {}
    for row in interactions:
        task_id = row["id_tarefa"]
        if task_id not in latest or row["data_hora"] > latest[task_id]["data_hora"]:
            latest[task_id] = row
    for task in tasks:
        interaction = latest.get(task["id_tarefa"])
        task["status"] = interaction["resultado"] if interaction else "Pendente"
        task["ultima_interacao"] = interaction["data_hora"] if interaction else ""
        task["proximo_retorno"] = interaction["proximo_retorno"] if interaction else ""
    return tasks


class CRMHandler(SimpleHTTPRequestHandler):
    def send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            self.send_json({"ufs": UFS_BRASIL})
            return
        if parsed.path == "/api/carteira":
            ufs = {uf for uf in parse_qs(parsed.query).get("ufs", [""])[0].split(",") if uf}
            if not ufs or not ufs.issubset(UFS_BRASIL):
                self.send_json({"erro": "Selecione ao menos uma UF válida."}, HTTPStatus.BAD_REQUEST)
                return
            try:
                self.send_json({"tarefas": carteira(ufs)})
            except (RuntimeError, GoogleAPICallError, TransportError) as error:
                self.send_json({"erro": f"Histórico BigQuery indisponível: {error}"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/interacoes":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            required = ["id_tarefa", "consultor", "resultado"]
            if any(not str(payload.get(field, "")).strip() for field in required):
                raise ValueError("Preencha o resultado da ligação.")
            task = next((item for item in read_csv(carteira_file_atual()) if item["id_tarefa"] == payload["id_tarefa"]), None)
            if not task:
                raise ValueError("Tarefa não encontrada.")
            row = {
                "id_interacao": str(uuid4()), "data_hora": datetime.now().astimezone().isoformat(timespec="seconds"),
                "id_tarefa": task["id_tarefa"], "consultor": payload["consultor"], "uf": task["uf"],
                "id_wfm_b2b": task["id_wfm_b2b"], "resultado": payload["resultado"],
                "data_carteira": task["data_carteira"], "parceiro": task["parceiro"],
                "cidade": task["cidade"], "motivos": task["motivos"],
                "observacao": str(payload.get("observacao", "")).strip(),
                "proximo_retorno": str(payload.get("proximo_retorno", "")).strip() or None,
            }
            with LOCK:
                salvar_interacao_bigquery(row)
                # BOM só é necessário na criação do arquivo. Em modo append ele poderia
                # entrar no meio do CSV e quebrar a próxima leitura.
                with INTERACOES_FILE.open("a", newline="", encoding="utf-8") as file:
                    csv.DictWriter(file, fieldnames=INTERACAO_COLUNAS).writerow(row)
            self.send_json({"ok": True, "interacao": row}, HTTPStatus.CREATED)
        except (json.JSONDecodeError, ValueError, RuntimeError, GoogleAPICallError, TransportError) as error:
            self.send_json({"erro": str(error)}, HTTPStatus.BAD_REQUEST)


if __name__ == "__main__":
    seed_files()
    print("Mini CRM disponível em http://localhost:8787")
    ThreadingHTTPServer(("0.0.0.0", 8787), CRMHandler).serve_forever()
