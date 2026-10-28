"""Evidências legíveis em PT-PT: um ficheiro por passo, com cabeçalho e só depois a resposta.

Formato: caso Qase e passo, script e versão, data/hora (Lisboa), ambiente, pedido (método + URL,
apikey mascarada), resultado esperado, resultado obtido (Passou/Falhou) e, no fim, a resposta
formatada (JSON indentado ou tabela alinhada). Nome do ficheiro: <caso>_passo<n>_<descricao>.txt
Casos que a usam: P0704-49 (scripts em projetos/P0704 - CRM-middleware/scripts/P0704-49/).
"""
import datetime
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

LISBOA = ZoneInfo("Europe/Lisbon")


def tabela(linhas: list[dict], colunas: list[str] | None = None) -> str:
    """Tabela de texto com colunas alinhadas."""
    if not linhas:
        return "(sem linhas)"
    colunas = colunas or list(linhas[0].keys())
    larg = {c: max(len(c), *(len(str(l.get(c, ""))) for l in linhas)) for c in colunas}
    sep = "  "
    cab = sep.join(c.ljust(larg[c]) for c in colunas)
    return "\n".join([cab, sep.join("-" * larg[c] for c in colunas)] +
                     [sep.join(str(l.get(c, "")).ljust(larg[c]) for c in colunas) for l in linhas])


def _formatar(resposta) -> str:
    if resposta is None:
        return "(sem resposta)"
    if isinstance(resposta, str):
        try:
            return json.dumps(json.loads(resposta), ensure_ascii=False, indent=2)
        except ValueError:
            return resposta
    if isinstance(resposta, list) and resposta and all(isinstance(x, dict) for x in resposta) \
            and all(not isinstance(v, (dict, list)) for x in resposta for v in x.values()):
        return tabela(resposta)
    return json.dumps(resposta, ensure_ascii=False, indent=2, default=str)


def escrever(pasta, caso: int | str, passo: int, descricao: str, *, script: str, versao: str, ambiente: str,
             pedido: str, esperado: str, obtido: str, passou: bool, resposta=None, mascarar=lambda s: s) -> Path:
    """Escreve a evidência de um passo e devolve o caminho do ficheiro."""
    nome = f"{caso}_passo{passo}_{re.sub(r'[^a-z0-9]+', '_', descricao.lower()).strip('_')}.txt"
    agora = datetime.datetime.now(LISBOA).strftime("%d/%m/%Y %H:%M:%S (hora de Lisboa)")
    texto = "\n".join([
        f"Caso Qase: {caso}   Passo: {passo} — {descricao}",
        f"Script:    {script} (versão {versao})",
        f"Data/hora: {agora}",
        f"Ambiente:  {ambiente}",
        f"Pedido:    {pedido}",
        "",
        f"Resultado esperado: {esperado}",
        f"Resultado obtido:   {obtido}",
        f"Veredicto:          {'Passou' if passou else 'Falhou'}",
        "",
        "=" * 72,
        "Resposta / dados de suporte",
        "=" * 72,
        _formatar(resposta),
        "",
    ])
    p = Path(pasta) / nome
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mascarar(texto), encoding="utf-8")
    return p
