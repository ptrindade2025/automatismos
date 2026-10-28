"""Cliente HTTP só de leitura (GET) para o middleware CRM.

Objetivo: chamar as rotas /zw/... com a X-API-Key, sem nunca a escrever em disco nem nos registos.
Apikey: variável de ambiente P0704_MW_APIKEY ou, se não existir, o ficheiro
~/.config/p0704/mwkey (chmod 600, apagado com shred no fim da execução).
Origem: mw.py do run 6 da P0704-49 (23/10/2026).
Casos que o usam: P0704-49 (136-165).
"""
import datetime
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

AMBIENTES = {
    "pp": {"base": "http://middleware-crm.pp.zap.intra/api", "host": "middleware_crm.pp.zap.intra"},
}
FICHEIRO_APIKEY = Path(os.path.expanduser("~/.config/p0704/mwkey"))


def ler_apikey() -> str:
    """Lê a apikey da variável de ambiente ou do ficheiro protegido; nunca a mostra."""
    k = os.environ.get("P0704_MW_APIKEY", "").strip()
    if not k and FICHEIRO_APIKEY.exists():
        if FICHEIRO_APIKEY.stat().st_mode & 0o077:
            raise SystemExit(f"{FICHEIRO_APIKEY} tem de ter permissões 600.")
        k = FICHEIRO_APIKEY.read_text().strip()
    if not k:
        raise SystemExit("Apikey em falta: definir P0704_MW_APIKEY ou criar ~/.config/p0704/mwkey (chmod 600).")
    return k


class MiddlewareCRM:
    """GET ao middleware CRM com registo mascarado de cada pedido."""

    def __init__(self, ambiente: str = "pp", timeout: int = 180):
        if ambiente not in AMBIENTES:
            raise SystemExit(f"Ambiente desconhecido: {ambiente} (disponíveis: {', '.join(AMBIENTES)})")
        self.base = AMBIENTES[ambiente]["base"]
        self.host = AMBIENTES[ambiente]["host"]
        self._k = ler_apikey()
        self.timeout = timeout
        self.registo: list[str] = []

    def mascarar(self, texto: str) -> str:
        return texto.replace(self._k, "****")

    def get(self, caminho: str) -> tuple[int, str]:
        """Devolve (estado HTTP, corpo em texto, já mascarado)."""
        rq = urllib.request.Request(self.base + caminho, headers={
            "Host": self.host, "X-API-Key": self._k, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(rq, timeout=self.timeout) as r:
                st, corpo = r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            st, corpo = e.code, e.read().decode()
        self.registo.append(f"{datetime.datetime.now():%d/%m/%Y %H:%M:%S} GET {caminho} (X-API-Key: ****) -> {st}")
        return st, self.mascarar(corpo)

    def get_json(self, caminho: str) -> tuple[int, dict]:
        st, corpo = self.get(caminho)
        try:
            return st, json.loads(corpo)
        except ValueError:
            return st, {"_texto": corpo[:500]}

    def paginar(self, caminho: str, max_paginas: int = 200) -> tuple[int, list, dict]:
        """Segue o next_cursor e devolve (estado, todos os registos, última resposta)."""
        st, j = self.get_json(caminho)
        dados = list(j.get("data", [])) if st == 200 else []
        n = 0
        while st == 200 and j.get("pagination", {}).get("next_cursor") and n < max_paginas:
            sep = "&" if "?" in caminho else "?"
            st, j = self.get_json(f"{caminho}{sep}cursor={j['pagination']['next_cursor']}")
            dados += j.get("data", [])
            n += 1
        return st, dados, j

    def total(self, caminho: str) -> int | None:
        """pagination.total com limit=1 (contagem rápida)."""
        sep = "&" if "?" in caminho else "?"
        st, j = self.get_json(f"{caminho}{sep}limit=1")
        return j.get("pagination", {}).get("total") if st == 200 else None
