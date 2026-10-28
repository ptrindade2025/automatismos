"""Registo de passos de um caso (asserções 'soft' por passo) e evidência autoexplicativa por passo.

Cada passo corre as suas asserções web-first (expect); uma falha fica registada e os passos seguintes
continuam (quando o caso o permite). No fim, `fechar()` falha o teste se algum passo falhou.
Escreve no stdout linhas «PASSO <caso> P<n> <estado> — <descrição> | <detalhe>» para o log.

Evidência: se a variável EVIDENCIAS_DIR estiver definida (o correr_tudo.py define-a), cada passo gera um
ficheiro <EVIDENCIAS_DIR>/<caso>/P<n>.md em PT-PT com: caso e passo, script, data/hora, ambiente,
pedido (segredos mascarados), esperado vs obtido, resposta formatada, estado e notas.

    with ps.passo(2, "Enviar código", esperado="«Introduza o código…» e 6 campos") as r:
        r.pedido("POST", "/login/mfa/send", {"channel": "email"})
        ...
        r.obtido("mensagem «Introduza o código…»; 6 campos")
        r.resposta(200, corpo)
"""
import inspect
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Lisbon")
except Exception:  # noqa: BLE001
    _TZ = None

CHAVES_SECRETAS = re.compile(r"pass|pin|token|secret|segredo|codigo|code|csrf|cookie|session", re.IGNORECASE)
VARIAVEIS_SECRETAS = ("AW_SECRET", "AW_PIN")


def mascarar_segredos(valor):
    """Devolve uma cópia com os valores de chaves sensíveis e os segredos do ambiente substituídos por ***."""
    if isinstance(valor, dict):
        return {k: ("***" if CHAVES_SECRETAS.search(str(k)) and v not in (None, "") else mascarar_segredos(v))
                for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [mascarar_segredos(v) for v in valor]
    if isinstance(valor, str):
        for nome in VARIAVEIS_SECRETAS:
            s = os.environ.get(nome)
            if s and len(s) >= 3:
                valor = valor.replace(s, "***")
        return re.sub(r"(?<!\d)\d{6}(?!\d)", "******", valor) if "codigo" in valor.lower() else valor
    return valor


def _formatar(valor):
    if valor is None:
        return "—"
    if isinstance(valor, (dict, list)):
        return "```json\n" + json.dumps(mascarar_segredos(valor), ensure_ascii=False, indent=2) + "\n```"
    texto = str(valor)
    try:
        return "```json\n" + json.dumps(mascarar_segredos(json.loads(texto)), ensure_ascii=False, indent=2) + "\n```"
    except (ValueError, TypeError):
        return "```\n" + mascarar_segredos(texto)[:4000] + "\n```"


def codigo_caso(caso):
    """1192 -> 'SZA-1192'; '1284a' -> 'SZA-1284a'; o resto fica como está."""
    s = str(caso)
    return f"SZA-{s}" if re.fullmatch(r"\d+[a-z]?", s) else s


class Registo:
    """Dados de evidência de um passo (todos opcionais)."""

    def __init__(self, esperado=None):
        self.esperado, self._obtido, self._pedidos, self._respostas, self.notas, self.anexos = esperado, [], [], [], [], []

    def pedido(self, metodo, url, corpo=None):
        self._pedidos.append((metodo, mascarar_segredos(url), corpo))

    def resposta(self, estado_http, corpo=None):
        self._respostas.append((estado_http, corpo))

    def obtido(self, texto):
        self._obtido.append(str(texto))

    def anexo(self, caminho):
        self.anexos.append(str(caminho))


class Passos:
    def __init__(self, caso, script=None):
        self.caso, self.res = caso, []
        self.script = script or _script_chamador()
        self._atual = None

    @contextmanager
    def passo(self, n, descricao, esperado=None):
        r = Registo(esperado or descricao)
        self._atual = r
        estado, detalhe = "passed", ""
        try:
            yield r
        except AssertionError as e:
            estado, detalhe = "failed", str(e).splitlines()[0][:300] if str(e) else "asserção falhou"
        except Exception as e:  # erro inesperado: regista e volta a lançar (o teste falha com o traceback)
            estado, detalhe = "failed", f"erro {type(e).__name__}: {str(e).splitlines()[0][:250] if str(e) else ''}"
            self._registar(n, estado, descricao, detalhe, r)
            raise
        self._registar(n, estado, descricao, detalhe, r)

    def _registar(self, n, estado, descricao, detalhe, r):
        self.res.append((n, estado, descricao, detalhe))
        self._atual = None
        print(f"PASSO {self.caso} P{n} {estado} — {descricao} | {mascarar_segredos(detalhe)}", flush=True)
        escrever_evidencia(self, n, estado, descricao, detalhe, r)

    def nota(self, texto):
        if self._atual is not None:
            self._atual.notas.append(str(texto))
        print(f"NOTA {self.caso} — {mascarar_segredos(str(texto))}", flush=True)

    def fechar(self):
        falhas = [r for r in self.res if r[1] == "failed"]
        assert not falhas, "; ".join(f"P{n}: {det}" for n, _, _, det in falhas)


def saltar(ps: "Passos", n, descricao, motivo):
    """Regista um passo não executado (ex.: depende de um passo anterior que falhou)."""
    ps.res.append((n, "skipped", descricao, motivo))
    print(f"PASSO {ps.caso} P{n} skipped — {descricao} | {motivo}", flush=True)
    escrever_evidencia(ps, n, "skipped", descricao, motivo, Registo())


def _script_chamador():
    for f in inspect.stack()[2:]:
        if "passos.py" not in f.filename:
            return f.filename
    return "?"


ESTADOS_PT = {"passed": "PASSOU", "failed": "FALHOU", "skipped": "NÃO EXECUTADO"}


def escrever_evidencia(ps, n, estado, descricao, detalhe, r):
    raiz = os.environ.get("EVIDENCIAS_DIR")
    if not raiz:
        return None
    agora = datetime.now(_TZ) if _TZ else datetime.now()
    caso = codigo_caso(ps.caso)
    pasta = Path(raiz) / re.sub(r"[^\w.-]+", "_", caso)
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        script = str(Path(ps.script).resolve().relative_to(Path(os.environ.get("EVIDENCIAS_RAIZ_SCRIPTS", "/")).resolve()))
    except ValueError:
        script = ps.script
    pedidos = "\n\n".join(f"`{m} {u}`\n\n{_formatar(c)}" for m, u, c in r._pedidos) or "— (passo de interface; ver «Obtido» e anexos)"
    respostas = "\n\n".join(f"HTTP {s}\n\n{_formatar(c)}" for s, c in r._respostas) or "—"
    obtido = "\n".join(f"- {mascarar_segredos(o)}" for o in r._obtido) or (f"- {mascarar_segredos(detalhe)}" if detalhe else
                                                                         "- conforme o esperado (todas as verificações do passo passaram)")
    linhas = [
        f"# {caso} · Passo {n} — {ESTADOS_PT.get(estado, estado)}",
        "",
        "| Campo | Valor |", "|---|---|",
        f"| Caso | {caso} |",
        f"| Passo | P{n} — {descricao} |",
        f"| Script | {script} |",
        f"| Data/hora | {agora:%d/%m/%Y %H:%M:%S} (hora de Lisboa) |",
        f"| Ambiente | {os.environ.get('AMBIENTE', 'PP')} |",
        f"| Estado | {ESTADOS_PT.get(estado, estado)} |",
        "", "## Pedido", "", pedidos,
        "", "## Esperado", "", str(r.esperado or descricao),
        "", "## Obtido", "", obtido,
        "", "## Resposta", "", respostas,
    ]
    if r.notas:
        linhas += ["", "## Notas", ""] + [f"- {mascarar_segredos(t)}" for t in r.notas]
    if detalhe and estado != "passed":
        linhas += ["", "## Motivo", "", mascarar_segredos(detalhe)]
    if r.anexos:
        linhas += ["", "## Anexos", ""] + [f"- {a}" for a in r.anexos]
    f = pasta / f"P{n}.md"
    f.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return f
