"""Procedimentos genéricos sobre clientes, contas e serviços do middleware CRM (P0704-49).

Regra testada: só clientes Empresariais são expostos; a classificação lê-se na BD em tempo de execução.
Origem: r3_rotas.py e r4_143.py (run 6).
"""
import json
from . import bd


def classificacao(codigocliente: str, seccao="client") -> str | None:
    return bd.valor(f"SELECT classificacao FROM cliente WHERE codigocliente={bd.sql_str(codigocliente)} LIMIT 1", seccao=seccao)


def dono_da_conta(codigoconta: str, seccao="client") -> dict | None:
    l = bd.select("SELECT ct.codigoconta,ct.idcontatipo,cl.codigocliente,cl.classificacao FROM conta ct "
                  f"JOIN cliente cl ON cl.idcliente=ct.idcliente WHERE ct.codigoconta={bd.sql_str(codigoconta)} LIMIT 1",
                  seccao=seccao)
    return l[0] if l else None


def esperado_por_classificacao(classif: str | None) -> int:
    """Código HTTP esperado: 200 se Empresarial, 403 se existir e não for, 404 se não existir."""
    return 404 if classif is None else (200 if classif == "Empresarial" else 403)


def verificar_rota(mw, caminho: str, classif: str | None) -> dict:
    """Chama a rota e compara o código com o esperado pela classificação na BD."""
    st, corpo = mw.get(caminho)
    esp = esperado_por_classificacao(classif)
    return {"rota": caminho, "classificacao_bd": classif, "esperado": esp, "obtido": st,
            "ok": st == esp, "mensagem": " ".join(corpo[:200].split())}


def total_empresariais_desde(since: str, seccao="client") -> int:
    return int(bd.valor("SELECT count(*) FROM cliente WHERE classificacao='Empresarial' "
                        f"AND data_alteracao>={bd.sql_str(since)} LIMIT 1", seccao=seccao))


def codigos_empresariais_desde(since: str, seccao="client") -> list[str]:
    return [r["codigocliente"] for r in bd.select(
        "SELECT codigocliente FROM cliente WHERE classificacao='Empresarial' "
        f"AND data_alteracao>={bd.sql_str(since)} LIMIT 499", seccao=seccao)]


def telefones_bd(codigocliente: str, seccao="client") -> dict | None:
    l = bd.select("SELECT telefone,telemovel,email FROM cliente "
                  f"WHERE codigocliente={bd.sql_str(codigocliente)} LIMIT 1", seccao=seccao)
    return l[0] if l else None


def normalizar(numero) -> str | None:
    """Número da BD no formato da API (+indicativo...); vazio, 0 ou None dá None."""
    s = str(numero or "").strip()
    return None if s in ("", "0", "None") else "+" + s.lstrip("+")


def verificar_telefones(mw, codigocliente: str, seccao="client") -> dict:
    """phone = telemóvel e primary_contact = fixo, sem recorrer ao email (REQ-014)."""
    st, corpo = mw.get(f"/zw/clients/{codigocliente}")
    j = json.loads(corpo) if st == 200 else {}
    t = telefones_bd(codigocliente, seccao) or {}
    ep, ef = normalizar(t.get("telemovel")), normalizar(t.get("telefone"))
    return {"cliente": codigocliente, "http": st, "phone": j.get("phone"), "primary_contact": j.get("primary_contact"),
            "esperado_phone": ep, "esperado_primary_contact": ef,
            "ok": st == 200 and j.get("phone") == ep and j.get("primary_contact") == ef}


def contas_do_cliente(codigocliente: str, idcontatipo: int | None = None, seccao="client") -> list[str]:
    """Códigos das contas do cliente (opcionalmente só de um idcontatipo). Origem: P0704-46 caso 132."""
    filtro = f" AND ct.idcontatipo={int(idcontatipo)}" if idcontatipo is not None else ""
    return [r["codigoconta"] for r in bd.select(
        "SELECT ct.codigoconta FROM conta ct JOIN cliente cl ON cl.idcliente=ct.idcliente "
        f"WHERE cl.codigocliente={bd.sql_str(codigocliente)}{filtro} LIMIT 50", seccao=seccao)]


def faturas_da_conta(codigoconta: str, since: str, seccao="client") -> list[dict]:
    """Faturas da conta emitidas desde «since» (referência para ver se a API as expõe). Origem: P0704-46 caso 132."""
    return bd.select("SELECT f.numerofactura,f.dataemissao,f.total FROM factura f JOIN conta ct ON ct.idconta=f.idconta "
                     f"WHERE ct.codigoconta={bd.sql_str(codigoconta)} AND f.dataemissao>={bd.sql_str(since)} "
                     "ORDER BY f.dataemissao DESC LIMIT 100", seccao=seccao)
