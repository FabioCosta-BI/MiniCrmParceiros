"""Acesso ao PostgreSQL da TI: carteira, histórico e controle de tentativas."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


def configuracao() -> dict[str, str]:
    campos = ("CRM_PG_HOST", "CRM_PG_DATABASE", "CRM_PG_USER", "CRM_PG_PASSWORD")
    faltando = [campo for campo in campos if not os.getenv(campo)]
    if faltando:
        raise RuntimeError(f"PostgreSQL da TI não configurado: {', '.join(faltando)}")
    return {
        "host": os.environ["CRM_PG_HOST"], "port": os.getenv("CRM_PG_PORT", "5432"),
        "dbname": os.environ["CRM_PG_DATABASE"], "user": os.environ["CRM_PG_USER"],
        "password": os.environ["CRM_PG_PASSWORD"],
    }


def schema() -> str:
    return os.getenv("CRM_PG_SCHEMA", "starlink_crm")


def conexao():
    return psycopg.connect(**configuracao(), row_factory=dict_row)


def competencia(data: date) -> date:
    return data.replace(day=1)


def segundo_dia_util(data: date) -> date:
    proxima, uteis = data, 0
    while uteis < 2:
        proxima += timedelta(days=1)
        if proxima.weekday() < 5:
            uteis += 1
    return proxima


def controles(ids: list[str], hoje: date) -> dict[str, dict]:
    """Controle do mês e bloqueios persistentes por número inválido."""
    if not ids:
        return {}
    comando = f"""
        SELECT * FROM {schema()}.controle_contatos
        WHERE id_wfm_b2b = ANY(%s)
          AND (competencia = %s OR (status = 'bloqueado' AND ultimo_resultado = 'Número inválido'))
        ORDER BY competencia DESC
    """
    with conexao() as conn, conn.cursor() as cur:
        cur.execute(comando, (ids, competencia(hoje)))
        resultado: dict[str, dict] = {}
        for linha in cur.fetchall():
            resultado.setdefault(linha["id_wfm_b2b"], linha)
        return resultado


def elegivel(controle: dict | None, hoje: date) -> bool:
    if not controle:
        return True
    if controle["status"] in {"concluido", "bloqueado"}:
        return False
    if controle.get("data_ultima_oferta") == hoje:
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
        cur.executemany(comando, [
            (item["id_wfm_b2b"], competencia(hoje), hoje, segundo_dia_util(hoje)) for item in itens
        ])


def substituir_carteira(itens: list[dict], hoje: date) -> None:
    excluir = f"DELETE FROM {schema()}.carteira_diaria WHERE data_carteira = %s"
    inserir = f"""
        INSERT INTO {schema()}.carteira_diaria
        (id_tarefa, data_carteira, bloco_uf, uf, id_wfm_b2b, parceiro, cidade, cod_ibge,
         telefone, vendas_starlink, motivos, prioridade, detalhe_regra)
        VALUES (%(id_tarefa)s, %(data_carteira)s, %(bloco_uf)s, %(uf)s, %(id_wfm_b2b)s,
                %(parceiro)s, %(cidade)s, %(cod_ibge)s, %(telefone)s, %(vendas_starlink)s,
                %(motivos)s, %(prioridade)s, %(detalhe_regra)s)
    """
    with conexao() as conn, conn.cursor() as cur:
        cur.execute(excluir, (hoje,))
        if itens:
            cur.executemany(inserir, itens)


def existe_carteira(hoje: date) -> bool:
    with conexao() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT EXISTS (SELECT 1 FROM {schema()}.carteira_diaria WHERE data_carteira = %s) AS existe", (hoje,))
        return bool(cur.fetchone()["existe"])


def carteira_do_dia(ufs: list[str], hoje: date) -> list[dict]:
    comando = f"""
        SELECT * FROM {schema()}.carteira_diaria
        WHERE data_carteira = %s AND uf = ANY(%s)
        ORDER BY bloco_uf, prioridade DESC, vendas_starlink DESC, parceiro
    """
    with conexao() as conn, conn.cursor() as cur:
        cur.execute(comando, (hoje, ufs))
        return cur.fetchall()


def tarefa(id_tarefa: str) -> dict | None:
    with conexao() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {schema()}.carteira_diaria WHERE id_tarefa = %s", (id_tarefa,))
        return cur.fetchone()


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
    contato_realizado = resultado not in {"Não atendeu", "Número inválido"}
    numero_invalido = resultado == "Número inválido"
    atendimento = f"""
        INSERT INTO {schema()}.atendimentos_parceiros
        (id_atendimento, data_hora, id_tarefa, data_carteira, consultor, id_wfm_b2b,
         parceiro, uf, cidade, motivos, resultado, observacao)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    controle = f"""
        UPDATE {schema()}.controle_contatos SET
            tentativas_no_mes = CASE WHEN %s THEN 3 ELSE LEAST(tentativas_no_mes + 1, 3) END,
            data_ultima_tentativa = %s,
            data_proxima_tentativa = CASE WHEN %s OR %s THEN NULL WHEN tentativas_no_mes + 1 >= 3 THEN NULL ELSE %s END,
            status = CASE WHEN %s THEN 'concluido' WHEN %s OR tentativas_no_mes + 1 >= 3 THEN 'bloqueado' ELSE 'aguardando_tentativa' END,
            ultimo_resultado = %s, atualizado_em = CURRENT_TIMESTAMP
        WHERE id_wfm_b2b = %s AND competencia = %s
    """
    with conexao() as conn, conn.cursor() as cur:
        cur.execute(atendimento, (
            uuid4(), agora, item["id_tarefa"], item["data_carteira"], payload["consultor"],
            item["id_wfm_b2b"], item["parceiro"], item["uf"], item["cidade"], item["motivos"],
            resultado, payload.get("observacao", ""),
        ))
        cur.execute(controle, (
            contato_realizado, agora, contato_realizado, numero_invalido,
            segundo_dia_util(agora.date()), contato_realizado, numero_invalido, resultado,
            item["id_wfm_b2b"], competencia(item["data_carteira"]),
        ))
