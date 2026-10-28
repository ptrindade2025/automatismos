"""Leitura da BD do ZW para os testes do middleware CRM, sempre através do dbq.py.

O dbq.py só aceita SELECT e abre a sessão READ ONLY; aqui exige-se ainda LIMIT.
A secção de ~/GrokBot/secrets/mysql_zap.cnf escolhe o ambiente (ex.: «client» = BD QA usada no run 6).
Origem: db() de mw.py (run 6 da P0704-49); reutiliza sql_str de _comum/bd.py.
"""
import subprocess
from ._registo import REGISTO_SQL
from .._comum.bd import sql_str  # noqa: F401  (reexportado para os scripts)
from .._comum.config import QA_RUNNER


def select(sql: str, seccao: str = "client", schema: str = "zapweb", timeout: int = 120) -> list[dict]:
    """Executa a consulta e devolve uma lista de dicionários (máx. 500 linhas, limite do dbq.py)."""
    if " limit " not in f" {sql.lower()} ":
        raise ValueError("Regra QA: todas as consultas levam LIMIT.")
    r = subprocess.run([str(QA_RUNNER / "dbq.py"), "-m", seccao, sql, schema],
                       capture_output=True, text=True, timeout=timeout)
    REGISTO_SQL.append("SQL: " + " ".join(sql.split()))
    if r.returncode != 0:
        raise SystemExit(f"dbq.py falhou: {(r.stderr or r.stdout).strip()[-400:]}")
    linhas = [l for l in r.stdout.splitlines() if l]
    if not linhas:
        return []
    cols = linhas[0].split("\t")
    return [dict(zip(cols, l.split("\t"))) for l in linhas[1:]]


def valor(sql: str, **kw):
    """Primeiro campo da primeira linha (útil para COUNT)."""
    linhas = select(sql, **kw)
    return next(iter(linhas[0].values())) if linhas else None
