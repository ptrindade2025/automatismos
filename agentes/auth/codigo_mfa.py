"""Leitura do código MFA do Zap Agentes PP na BD (só leitura, secção zwppdb00_3306,
schema `middleware-contactos`).

Origem: P0733-seguranca-zap-agentes/scripts/mfa_707_712.py (max_email_id, get_email_code)
e _comum/scripts/ultimo_codigo_aw.sh (SMS).

## max_email_id(endereco)
- **Objetivo:** marcar o último email antes de pedir um código, para não ler códigos antigos.
## ler_codigo_email(endereco, depois_de_id, espera)
- **Objetivo:** esperar pelo email «Código de acesso zapagentes WEB» e devolver (código, id).
- **Resultado esperado:** código de 6 dígitos, ou (None, depois_de_id) em caso de timeout.
## ultimo_codigo_sms()
- **Objetivo:** devolver o último código SMS «zapagentes WEB» (linha TSV com destino mascarado).
- **Casos que o usam:** SZA-701, 707, 709, 712 (suite 263) e restantes casos MFA do P0733.
"""
import re
import time  # só para a sondagem da BD (não sincroniza a UI); exceção documentada na MIGRACAO_NORMA_2026-10-24.md
from automacao._comum.bd import select_raw, sql_str

SECCAO = "zwppdb00_3306"
SCHEMA = "middleware-contactos"
ASSUNTO = "Código de acesso zapagentes WEB"


def max_email_id(endereco: str) -> int:
    o = select_raw(f"SELECT IFNULL(MAX(id),0) FROM notification_email "
                   f"WHERE group_identifier={sql_str(endereco)} LIMIT 1", SECCAO, SCHEMA)
    for l in o.strip().splitlines()[1:]:
        if l.strip().isdigit():
            return int(l.strip())
    return 0


def max_email_id_global() -> int:
    """Último id de email de código MFA (qualquer destinatário); para endereços inválidos que não passam no sql_str."""
    o = select_raw(f"SELECT IFNULL(MAX(id),0) FROM notification_email WHERE subject='{ASSUNTO}' LIMIT 1", SECCAO, SCHEMA)
    for l in o.strip().splitlines()[1:]:
        if l.strip().isdigit():
            return int(l.strip())
    return 0


def ler_codigo_email(endereco: str, depois_de_id: int = 0, espera: int = 25):
    sql = ("SELECT id, TRIM(SUBSTRING_INDEX(IFNULL(text_plain,text_html),':',-1)) AS codigo "
           f"FROM notification_email WHERE subject='{ASSUNTO}' "
           f"AND group_identifier={sql_str(endereco)} AND id>{int(depois_de_id)} "
           "ORDER BY id DESC LIMIT 1")
    t0 = time.monotonic()
    while time.monotonic() - t0 < espera:
        linhas = [l for l in select_raw(sql, SECCAO, SCHEMA).strip().splitlines()[1:] if l]
        if linhas:
            partes = linhas[0].split("\t")
            if len(partes) >= 2 and re.fullmatch(r"\d{6}", partes[1].strip()):
                return partes[1].strip(), int(partes[0])
        time.sleep(1)  # intervalo de sondagem da BD, não espera de UI
    return None, depois_de_id


def ultimo_codigo_sms() -> str:
    sql = ("SELECT TRIM(SUBSTRING_INDEX(text, ':', -1)) AS codigo, "
           "CONCAT('***', RIGHT(`to`,3)) AS para_mascarado, created_at AS criado_utc "
           "FROM notification_sms WHERE text LIKE '%zapagentes WEB%' "
           "ORDER BY created_at DESC LIMIT 1")
    return select_raw(sql, SECCAO, SCHEMA)
