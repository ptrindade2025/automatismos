"""Apoio aos testes que alteram a ficha do seller (P0733-20/26/27): estado por SELECT e código SMS por destino.
Só leitura na BD. Telefones só se mostram mascarados (mascarar)."""
import time  # só para a sondagem da BD (exceção aprovada), não sincroniza a UI
from automacao._comum.bd import select_raw, sql_str

SMS = ("zwppdb00_3306", "middleware-contactos")
AGENTES = ("zwppdb00_3306", "msagentes")


def _linhas(sql, alvo):
    return [l.split("\t") for l in select_raw(sql, *alvo).strip().splitlines()[1:]]


def estado_seller(utilizador: str) -> dict:
    """{'phone': str|None, 'email': str|None} tal como está na BD (NULL → None)."""
    r = _linhas(f"SELECT IFNULL(phone,'\\\\N'), IFNULL(email,'\\\\N') FROM seller WHERE username={sql_str(utilizador)} LIMIT 1", AGENTES)
    f = lambda v: None if v in ("\\N", "NULL") else v
    return {"phone": f(r[0][0]), "email": f(r[0][1])}


def mascarar(v):
    return "NULL" if v is None else ("''" if v == "" else (v[:4] + "***" + v[-3:] if v.isdigit() else v))


def max_sms_id(telefone: str) -> int:
    r = _linhas(f"SELECT IFNULL(MAX(id),0) FROM notification_sms WHERE `to`={sql_str(telefone)} LIMIT 1", SMS)
    return int(r[0][0])


def codigo_sms(telefone: str, depois_de_id: int, espera: int = 60):
    """Código de 6 dígitos do 1.º SMS «zapagentes WEB» para `telefone` com id > depois_de_id, ou None."""
    fim = time.monotonic() + espera
    while time.monotonic() < fim:
        r = _linhas(f"SELECT TRIM(SUBSTRING_INDEX(text, ':', -1)) FROM notification_sms WHERE `to`={sql_str(telefone)} "
                    f"AND id>{int(depois_de_id)} AND text LIKE '%zapagentes WEB%' ORDER BY id DESC LIMIT 1", SMS)
        if r and r[0][0].strip().isdigit():
            return r[0][0].strip()
        time.sleep(3)
    return None
