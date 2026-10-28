"""Procedimentos genéricos sobre faturas do middleware CRM (P0704-49).

Regra testada: a fatura é enviada se o cliente for Empresarial e a loja da aquisição
estiver em sistema.CRM_LOJAS_EMPRESARIAL. As referências calculam-se na BD em tempo de execução,
por isso funcionam com qualquer valor da configuração e qualquer data «since».
Origem: r1_dados.py, r2_faturas.py, r7_152.py, r8_153.py, r11_156.py, r12_reposicao.py (run 6).
"""
import collections
import re
from . import bd

CAMPOS_LOJA = ("store", "loja", "shop", "branch")
SQL_BASE = ("FROM factura f JOIN aquisicao a ON a.idfactura=f.idfactura "
            "JOIN conta ct ON ct.idconta=f.idconta JOIN cliente cl ON cl.idcliente=ct.idcliente ")
COLUNAS = ("f.idfactura,f.numerofactura,f.dataemissao,f.datacriacao,f.total,a.idaquisicao,a.idloja,"
           "a.contratocrm,cl.codigocliente,cl.classificacao,ct.codigoconta,ct.idcontatipo")


def config_lojas(seccao="client") -> str | None:
    """Valor atual de CRM_LOJAS_EMPRESARIAL."""
    return bd.valor("SELECT valor FROM sistema WHERE config='CRM_LOJAS_EMPRESARIAL' LIMIT 1", seccao=seccao)


def codigos_da_config(valor: str | None) -> list[str]:
    """Códigos L... da configuração, aceitando vírgulas, ponto e vírgula, espaços e repetidos."""
    return sorted(set(c for c in re.split(r"[\s,;]+", valor or "") if c))


def idlojas_por_codigo(codigos: list[str], seccao="client") -> dict[str, str]:
    """Converte códigos L... em idloja (o código está no fim do nome: «ZLOJ Loja ZAP Empresas  - L0004000236»).
    Códigos inexistentes ficam de fora."""
    res = {}
    for c in codigos:
        if not re.fullmatch(r"L\d{6,12}", c):
            continue
        linhas = bd.select(f"SELECT idloja,nome FROM loja WHERE nome LIKE '%- {c}' LIMIT 2", seccao=seccao)
        if len(linhas) == 1:
            res[c] = linhas[0]["idloja"]
    return res


def faturas_bd(since: str, idlojas, filtro_extra: str = "", seccao="client") -> list[dict]:
    """Faturas da BD emitidas desde «since» nas lojas indicadas (todas as classificações)."""
    idlojas = [str(int(i)) for i in idlojas]
    if not idlojas:
        return []
    return bd.select(f"SELECT {COLUNAS} {SQL_BASE} WHERE f.dataemissao>={bd.sql_str(since)} "
                     f"AND a.idloja IN ({','.join(idlojas)}) {filtro_extra} LIMIT 499", seccao=seccao)


def esperadas(linhas_bd: list[dict], idlojas=None) -> list[dict]:
    """Subconjunto que a regra manda enviar: cliente Empresarial e (se indicado) loja em «idlojas»."""
    ids = {str(i) for i in idlojas} if idlojas is not None else None
    return [b for b in linhas_bd if b["classificacao"] == "Empresarial" and (ids is None or b["idloja"] in ids)]


def associar(api: list[dict], linhas_bd: list[dict]):
    """Associa cada fatura da API à linha da BD: pelo número (name) ou, sem número,
    por cliente + total + data de criação ao minuto. Devolve (pares, sem_par)."""
    por_numero = {b["numerofactura"]: b for b in linhas_bd if b["numerofactura"] not in ("None", "")}
    pares, sem_par = [], []
    for x in api:
        b = por_numero.get(x.get("name") or "")
        if not b:
            c = [y for y in linhas_bd if y["codigocliente"] == (x.get("customer") or {}).get("client_code")
                 and abs(float(y["total"]) - float(x.get("total_amount") or 0)) < 0.01
                 and y["datacriacao"][:16].replace(" ", "T") == (x.get("created_at") or "")[:16]]
            b = c[0] if len(c) == 1 else None
        if b:
            pares.append((x, b))
        else:
            sem_par.append(x)
    return pares, sem_par


def duplicados(api: list[dict], chave: str = "id") -> list:
    """Valores de «chave» repetidos na resposta da API."""
    c = collections.Counter(x.get(chave) for x in api)
    return [k for k, v in c.items() if v > 1 and k is not None]


def comparar(api: list[dict], linhas_bd: list[dict], so_cliente: str | None = None, so_conta: str | None = None, idlojas=None) -> dict:
    """Comparação API × BD: em falta, fora da regra, sem par, duplicados, contagem por loja e contrato."""
    pares, sem_par = associar(api, linhas_bd)
    esp_l = [b for b in esperadas(linhas_bd, idlojas)
             if (not so_cliente or b["codigocliente"] == so_cliente) and (not so_conta or b["codigoconta"] == so_conta)]
    esp = {b["idfactura"] for b in esp_l}
    vistas = {b["idfactura"] for _, b in pares}
    return {
        "api": len(api), "esperadas_bd": len(esp), "associadas": len(pares),
        "em_falta": sorted(esp - vistas), "fora_da_regra": sorted(vistas - esp),
        "sem_par": [(x.get("name"), (x.get("customer") or {}).get("client_code")) for x in sem_par],
        # duplicados: pelo número (name) e, para faturas sem número, pela linha da BD associada
        "duplicados": duplicados(api, "name") + [k for k, v in collections.Counter(b["idfactura"] for _, b in pares).items() if v > 1],
        "por_loja": dict(collections.Counter(b["idloja"] for _, b in pares)),
        "contrato_diferente": [(b["idfactura"], x.get("crm_contract_number"), b["contratocrm"])
                               for x, b in pares if (x.get("crm_contract_number") or "None") != b["contratocrm"]],
    }


def comparacao_ok(r: dict) -> bool:
    return not (r["em_falta"] or r["fora_da_regra"] or r["sem_par"] or r["duplicados"] or r["contrato_diferente"])


def campos_loja(api: list[dict]) -> list[str]:
    """Campos da fatura cujo nome sugere a loja (REQ-013)."""
    chaves = set().union(*[x.keys() for x in api]) if api else set()
    return sorted(k for k in chaves if any(w in k.lower() for w in CAMPOS_LOJA))


def nomes_lojas(idlojas, seccao="client") -> dict[str, str]:
    """idloja -> nome da loja na BD (formato aprovado do campo store: «<nome ZW> - <código>», REQ-013)."""
    ids = [str(int(i)) for i in idlojas]
    if not ids:
        return {}
    return {l["idloja"]: l["nome"] for l in bd.select(
        f"SELECT idloja,nome FROM loja WHERE idloja IN ({','.join(ids)}) LIMIT 100", seccao=seccao)}


def verificar_store(api: list[dict], linhas_bd: list[dict], nomes: dict[str, str]) -> dict:
    """Compara o campo «store» de cada fatura da API com o nome da loja da aquisição na BD, agrupado por loja."""
    pares, sem_par = associar(api, linhas_bd)
    por_loja, diferentes = {}, []
    for x, b in pares:
        esp = nomes.get(b["idloja"])
        d = por_loja.setdefault(b["idloja"], {"loja": esp, "faturas": 0, "iguais": 0})
        d["faturas"] += 1
        if x.get("store") == esp:
            d["iguais"] += 1
        else:
            diferentes.append({"fatura": x.get("name") or x.get("id"), "idloja": b["idloja"], "esperado": esp, "obtido": x.get("store")})
    return {"api": len(api), "associadas": len(pares), "sem_par": len(sem_par), "por_loja": por_loja, "diferentes": diferentes}


def validar_schema(resposta: dict, caminho_schema) -> list[str]:
    """Erros de validação (jsonschema) da resposta contra o schema; lista vazia = válido."""
    import json, jsonschema
    from pathlib import Path
    sch = json.loads(Path(caminho_schema).read_text(encoding="utf-8"))
    v = jsonschema.validators.validator_for(sch)(sch)
    return [f"{'/'.join(map(str, e.absolute_path)) or '(raiz)'}: {e.message}" for e in v.iter_errors(resposta)][:50]


# --- Vendas cruzadas (cliente × loja), acrescentado 23/10/2026 ---
def contagem_cruzada(since: str, idlojas, dentro: bool, filtro_cliente: str, seccao="client") -> list[dict]:
    """Faturas desde «since» agrupadas por loja e classificação.
    dentro=True: só nas lojas «idlojas»; False: fora delas. filtro_cliente: condição SQL sobre cl."""
    ids = ",".join(str(int(i)) for i in idlojas)
    op = "IN" if dentro else "NOT IN"
    return bd.select("SELECT a.idloja,l.nome AS loja,IFNULL(NULLIF(cl.classificacao,''),'(vazio)') AS classificacao,"
                     "COUNT(DISTINCT f.idfactura) AS faturas,COUNT(DISTINCT cl.idcliente) AS clientes "
                     f"{SQL_BASE} JOIN loja l ON l.idloja=a.idloja WHERE f.dataemissao>={bd.sql_str(since)} "
                     f"AND a.idloja {op} ({ids}) AND ({filtro_cliente}) GROUP BY a.idloja,l.nome,3 "
                     "ORDER BY faturas DESC LIMIT 200", seccao=seccao)


def faturas_cruzadas(since: str, idlojas, dentro: bool, filtro_cliente: str, seccao="client") -> list[dict]:
    """Linhas das faturas (máx. 499) com o mesmo critério de contagem_cruzada."""
    ids = ",".join(str(int(i)) for i in idlojas)
    op = "IN" if dentro else "NOT IN"
    return bd.select(f"SELECT {COLUNAS} {SQL_BASE} WHERE f.dataemissao>={bd.sql_str(since)} "
                     f"AND a.idloja {op} ({ids}) AND ({filtro_cliente}) ORDER BY f.dataemissao DESC LIMIT 499", seccao=seccao)


NAO_EMPRESARIAL = "IFNULL(cl.classificacao,'')<>'Empresarial'"
EMPRESARIAL = "cl.classificacao='Empresarial'"
