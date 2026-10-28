"""Leitura da BD Zap, sempre através de ~/GrokBot/qa-runner/dbq.py.

O dbq.py recusa tudo o que não seja SELECT/SHOW/DESCRIBE/EXPLAIN/WITH e abre a sessão em
READ ONLY. As credenciais ficam em ~/GrokBot/secrets/mysql_zap.cnf e nunca são lidas aqui.
Origem: _comum/scripts/zw_bd.py e funções dbq() dos scripts P0733 (mfa_707_712.py).
"""
import subprocess
from .config import QA_RUNNER

SECCOES_PERMITIDAS = {"zwppdb00_3306", "zwppdb00_3308"}


def sql_str(valor) -> str:
    """Literal SQL seguro para massa de teste (letras, dígitos, espaço e . _ @ -)."""
    v = str(valor)
    if not all(c.isalnum() or c in " ._@-" for c in v):
        raise ValueError(f"valor com caracteres não permitidos: {v!r}")
    return "'" + v + "'"


def select_raw(sql: str, seccao: str, schema: str | None = None, timeout: int = 90) -> str:
    """Executa a consulta e devolve o texto TSV do dbq.py (cabeçalho na 1.ª linha)."""
    if seccao not in SECCOES_PERMITIDAS:
        raise SystemExit(f"secção de BD não permitida: {seccao}")
    if " limit " not in f" {sql.lower()} ":
        raise ValueError("Regra QA: todas as consultas levam LIMIT.")
    cmd = [str(QA_RUNNER / ".venv/bin/python"), "dbq.py", "-m", seccao, sql]
    if schema:
        cmd.append(schema)
    r = subprocess.run(cmd, cwd=QA_RUNNER, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise SystemExit(f"dbq.py falhou: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def select(sql: str, seccao: str = "zwppdb00_3308", schema: str | None = "zapweb") -> list[dict]:
    """Executa a consulta e devolve uma lista de dicionários."""
    linhas = [l for l in select_raw(sql, seccao, schema).splitlines() if l]
    if not linhas:
        return []
    cols = linhas[0].split("\t")
    return [dict(zip(cols, l.split("\t"))) for l in linhas[1:]]
