"""Registo de passos de um caso (asserções 'soft' por passo).

Cada passo corre as suas asserções web-first (expect); uma falha fica registada e os passos seguintes
continuam (quando o caso o permite). No fim, `fechar()` falha o teste se algum passo falhou.
Escreve no stdout linhas «PASSO <caso> P<n> <estado> — <descrição> | <detalhe>» para o log e o Qase.
"""
from contextlib import contextmanager


class Passos:
    def __init__(self, caso):
        self.caso, self.res = caso, []

    @contextmanager
    def passo(self, n, descricao):
        try:
            yield
            self.res.append((n, "passed", descricao, ""))
        except AssertionError as e:
            self.res.append((n, "failed", descricao, str(e).splitlines()[0][:300]))
        finally:
            n_, st, d, det = self.res[-1]
            print(f"PASSO {self.caso} P{n_} {st} — {d} | {det}", flush=True)

    def nota(self, texto):
        print(f"NOTA {self.caso} — {texto}", flush=True)

    def fechar(self):
        falhas = [r for r in self.res if r[1] == "failed"]
        assert not falhas, "; ".join(f"P{n}: {det}" for n, _, _, det in falhas)


def saltar(ps: "Passos", n, descricao, motivo):
    """Regista um passo não executado (ex.: depende de um passo anterior que falhou)."""
    ps.res.append((n, "skipped", descricao, motivo))
    print(f"PASSO {ps.caso} P{n} skipped — {descricao} | {motivo}", flush=True)
