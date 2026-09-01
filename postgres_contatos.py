"""Acesso ao PostgreSQL da TI para atendimentos e controle de tentativas."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


def configuracao() -> dict[str, str]:
    campos = ("PG_HOST", "PG_DATABASE", "PG_USER", "PG_PASSWORD")
    faltando = [campo for campo in campos if not os.getenv(campo)]
    if faltando:
        raise RuntimeError(f"PostgreSQL não configurado: {', '.join(faltando)}")
    return {
        "host": os.environ["PG_HOST"], "port": os.getenv("PG_PORT", "5432"),
        "dbname": os.environ["PG_DATABASE"], "user": os.environ["PG_USER"],
        "password": os.environ["PG_PASSWORD"],
    }


def schema() -> str:
    return os.getenv("PG_SCHEMA", "starlink_crm")


def conexao():
    return psycopg.connect(**configuracao(), row_factory=dict_row)


def competencia(data: date) -> date:
    return data.replace(day=1)


def segundo_dia_util(data: date) -> date:
    proxima = data
    uteis = 0
    while uteis < 2:
        proxima += timedelta(days=1)
        if proxima.weekday() < 5:
            uteis += 1
    return proxima


def controles(ids: list[str], hoje: date) -> dict[str, dict]:
    if not ids:
        return {}
    comando = f"""
        SELECT * FROM {schema()}.controle_contatos
        WHERE competencia = %s AND id_wfm_b2b = ANY(%s)
    """
    with conexao() as conn, conn.cursor() as cur:
        cur.execute(comando, (competencia(hoje), ids))
        return {linha["id_wfm_b2b"]: linha for linha in cur.fetchall()}


def elegivel(controle: dict | None, hoje: date) -> bool:
    if not controle:
        return True
    if controle["status"] in {"concluido", "bloqueado"}:
        return False
    proxima = controle["data_proxima_tentativa"]
    return bool(proxima and proxima <= hoje and controle["tentativas_no_mes"] < 3)


def registrar_oferta(itens: list[dict], hoje: date) -> None:
    if not itens:
        return
    comando = f"""
        INSERT INTO {schema()}.controle_contatos
            (id_wfm_b2b, competencia, data_ultima_oferta, data_proxima_tentativa, status)
        VALUES (%s, %s, %s, %s, 'aguardando_tentativa')
        ON CONFLICT (id_wfm_b2b, competencia) DO UPDATE SET
            data_ultima_oferta = EXCLUDED.data_ultima_oferta,
            data_proxima_tentativa = EXCLUDED.data_proxima_tentativa,
            status = CASE WHEN {schema()}.controle_contatos.status = 'elegivel'
                          THEN 'aguardando_tentativa' ELSE {schema()}.controle_contatos.status END,
            atualizado_em = CURRENT_TIMESTAMP
    """
    with conexao() as conn, conn.cursor() as cur:
        cur.executemany(comando, [(x["id_wfm_b2b"], competencia(hoje), hoje, segundo_dia_util(hoje)) for x in itens])


def ultimos_status(ids_tarefa: list[str]) -> dict[str, dict]:
    if not ids_tarefa:
        return {}
    comando = f"""
        SELECT DISTINCT ON (id_tarefa) id_tarefa, data_hora, resultado
        FROM {schema()}.atendimentos_parceiros
        WHERE id_tarefa = ANY(%s)
        ORDER BY id_tarefa, data_hora DESC
    """
    with conexao() as conn, conn.cursor() as cur:
        cur.execute(comando, (ids_tarefa,))
        return {linha["id_tarefa"]: linha for linha in cur.fetchall()}


def registrar_atendimento(item: dict, payload: dict) -> None:
    agora = datetime.now().astimezone()
    resultado = payload["resultado"]
    contato_realizado = resultado != "Não atendeu"
    comando_atendimento = f"""
        INSERT INTO {schema()}.atendimentos_parceiros
        (id_atendimento, data_hora, id_tarefa, data_carteira, consultor, id_wfm_b2b,
         parceiro, uf, cidade, motivos, resultado, observacao)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    comando_controle = f"""
        UPDATE {schema()}.controle_contatos SET
            tentativas_no_mes = CASE WHEN %s THEN 3 ELSE LEAST(tentativas_no_mes + 1, 3) END,
            data_ultima_tentativa = %s,
            data_proxima_tentativa = CASE WHEN %s THEN NULL WHEN tentativas_no_mes + 1 >= 3 THEN NULL ELSE %s END,
            status = CASE WHEN %s THEN 'concluido' WHEN tentativas_no_mes + 1 >= 3 THEN 'bloqueado' ELSE 'aguardando_tentativa' END,
            ultimo_resultado = %s, atualizado_em = CURRENT_TIMESTAMP
        WHERE id_wfm_b2b = %s AND competencia = %s
    """
    from uuid import uuid4
    with conexao() as conn, conn.cursor() as cur:
        cur.execute(comando_atendimento, (uuid4(), agora, item["id_tarefa"], item["data_carteira"], payload["consultor"], item["id_wfm_b2b"], item["parceiro"], item["uf"], item["cidade"], item["motivos"], resultado, payload.get("observacao", "")))
        cur.execute(comando_controle, (contato_realizado, agora, contato_realizado, segundo_dia_util(agora.date()), contato_realizado, resultado, item["id_wfm_b2b"], competencia(agora.date())))
