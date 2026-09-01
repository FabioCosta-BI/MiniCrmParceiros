"""Servidor web do Mini CRM. Carteira e histórico ficam no PostgreSQL da TI."""
from __future__ import annotations

import json
import threading
import csv
import os
from datetime import date
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from psycopg import Error as PostgresError

from postgres_contatos import carteira_do_dia, registrar_atendimento, tarefa, ultimos_status


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOCK = threading.Lock()
load_dotenv(BASE_DIR / ".env")
MODO_TESTE_CSV = os.getenv("CRM_MODO_TESTE_CSV", "").strip().lower() in {"1", "true", "sim"}
INTERACOES_TESTE: dict[str, dict] = {}
UFS_BRASIL = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
    "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]
GRUPOS_UF = {
    "Norte e Centro-Oeste": ["AC", "AM", "AP", "DF", "GO", "MA", "MS", "MT", "PA", "PI", "RO", "RR", "TO"],
    "Nordeste": ["AL", "BA", "CE", "PB", "PE", "RN", "SE"],
    "Sudeste e Sul": ["ES", "MG", "PR", "RJ", "RS", "SC", "SP"],
}


def carteira(ufs: list[str]) -> list[dict]:
    if MODO_TESTE_CSV:
        arquivo = DATA_DIR / f"carteira_{date.today().isoformat()}.csv"
        if not arquivo.exists():
            raise RuntimeError(f"CSV de teste não encontrado: {arquivo.name}")
        with arquivo.open(encoding="utf-8-sig", newline="") as origem:
            tarefas = [item for item in csv.DictReader(origem) if item["uf"] in ufs]
        for item in tarefas:
            status = INTERACOES_TESTE.get(item["id_tarefa"])
            item["status"] = status["resultado"] if status else "Pendente"
            item["ultima_interacao"] = ""
        return tarefas
    tarefas = carteira_do_dia(ufs, date.today())
    ultimos = ultimos_status([item["id_tarefa"] for item in tarefas])
    for item in tarefas:
        status = ultimos.get(item["id_tarefa"])
        item["status"] = status["resultado"] if status else "Pendente"
        item["ultima_interacao"] = status["data_hora"].isoformat() if status else ""
    return tarefas


class CRMHandler(SimpleHTTPRequestHandler):
    def send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            self.send_json({"ufs": UFS_BRASIL, "grupos_uf": GRUPOS_UF, "data_carteira": date.today().isoformat()})
            return
        if parsed.path == "/api/carteira":
            ufs = [uf for uf in parse_qs(parsed.query).get("ufs", [""])[0].split(",") if uf]
            if not ufs or not set(ufs).issubset(UFS_BRASIL):
                self.send_json({"erro": "Selecione ao menos uma UF válida."}, HTTPStatus.BAD_REQUEST)
                return
            try:
                self.send_json({"tarefas": carteira(ufs)})
            except (RuntimeError, PostgresError) as erro:
                self.send_json({"erro": f"Carteira indisponível no PostgreSQL da TI: {erro}"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/interacoes":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            if any(not str(payload.get(campo, "")).strip() for campo in ("id_tarefa", "consultor", "resultado")):
                raise ValueError("Escolha quem realizou o contato e o resultado da ligação.")
            if MODO_TESTE_CSV:
                INTERACOES_TESTE[str(payload["id_tarefa"])] = payload
                self.send_json({"ok": True, "aviso": "Registro apenas em memória: modo de teste CSV."}, HTTPStatus.CREATED)
                return
            item = tarefa(str(payload["id_tarefa"]))
            if not item:
                raise ValueError("Tarefa não encontrada na carteira diária.")
            with LOCK:
                registrar_atendimento(item, payload)
            self.send_json({"ok": True}, HTTPStatus.CREATED)
        except (json.JSONDecodeError, ValueError, RuntimeError, PostgresError) as erro:
            self.send_json({"erro": str(erro)}, HTTPStatus.BAD_REQUEST)


if __name__ == "__main__":
    print("Mini CRM disponível em http://0.0.0.0:8787")
    ThreadingHTTPServer(("0.0.0.0", 8787), CRMHandler).serve_forever()
