"""Evidências de falhas com Playwright: vídeo, trace e captura, guardados só quando o teste falha.

Equivale a `--video retain-on-failure --tracing retain-on-failure --screenshot only-on-failure` do
pytest-playwright, mas funciona com as fixtures próprias (P0733) e com scripts autónomos (P0704), porque
instrumenta o Playwright (API sync) em vez de depender de fixtures:

- cada `browser.new_context()` passa a gravar vídeo (na pasta temporária do teste, salvo se o script já
  indicar `record_video_dir`) e a gravar trace (capturas, DOM e fontes);
- campos de password, PIN e código MFA ficam mascarados no ecrã (CSS `-webkit-text-security`), por isso não
  aparecem no vídeo nem nas imagens do trace;
- ao fechar o contexto, guarda uma captura de cada página, o trace e o vídeo;
- no fim do teste, `terminar(manter)` move os ficheiros para o pacote da falha (`manter=True`) ou apaga-os;
- antes de sair da pasta temporária, os traces e os textos são redigidos: segredos do ambiente (AW_SECRET,
  AW_PIN, ZWP, P0704_MW_APIKEY), valores escritos em campos de password/PIN, códigos MFA escritos no teclado,
  cabeçalhos apikey/authorization/cookie e chaves sensíveis em JSON e formulários passam a «***».

Uso (pytest): `instalar()` uma vez; `GRAVADOR.iniciar(pasta_tmp)` antes do teste; `GRAVADOR.terminar(falhou,
destino)` depois do teardown. Uso (script autónomo): `python -m automacao._comum.gravacao_falhas --artefactos
PASTA -- script.py args…`; o chamador decide depois, pelo resultado, se mantém ou apaga PASTA.
"""
import contextlib
import json
import os
import re
import runpy
import shutil
import sys
import urllib.parse
import zipfile
from pathlib import Path

VARIAVEIS_SECRETAS = ("AW_SECRET", "AW_PIN", "AW_PASS", "ZWP", "P0704_MW_APIKEY")
CSS_MASCARA = ('input[type=password],input[name=pass],input[name*=pin i],input[name*=senha i],input[name*=password i],'
               'input[id*=password i],input[autocomplete=one-time-code],[data-role="mfa-digit"]'
               '{-webkit-text-security:disc !important}')
JS_MASCARA = ("(()=>{const add=()=>{if(document.getElementById('__qa_mascara'))return;const s=document.createElement('style');"
              "s.id='__qa_mascara';s.textContent=" + json.dumps(CSS_MASCARA) + ";(document.head||document.documentElement).appendChild(s);};"
              "if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',add);else add();})();")
CAMPO_SECRETO = re.compile(r"pass|\bpin\b|senha|secret|segredo|apikey|api-key|token|codigo|mfa-digit|one-time-code", re.IGNORECASE)
METODOS_ESCRITA = ("fill", "type", "pressSequentially", "insertText", "keyboardType", "keyboardInsertText")
CHAVES = r"(?:password|passwd|pass|pin|secret|segredo|apikey|api_key|x-api-key|token|code|codigo|otp)"
REGRAS = [
    # cabeçalhos no trace.network: {"name": "X-API-Key", "value": "…"}
    (re.compile(r'("name"\s*:\s*"(?:x-api-key|apikey|authorization|cookie|set-cookie)"\s*,\s*"value"\s*:\s*")[^"]*', re.IGNORECASE), r"\1***"),
    # JSON: "password": "…" (também com aspas escapadas dentro de strings)
    (re.compile(r'(\\?"' + CHAVES + r'\\?"\s*:\s*\\?")[^"\\]*', re.IGNORECASE), r"\1***"),
    # formulários e URLs: password=…&
    (re.compile(r"((?:^|[?&\s\"])" + CHAVES + r"=)[^&\s\"]*", re.IGNORECASE), r"\1***"),
    # testrunner/ReadyAPI e logs: -Papikey=…, X-API-Key: …
    (re.compile(r"(-Papikey=|x-api-key:\s*|apikey:\s*)\S+", re.IGNORECASE), r"\1***"),
    # valores de campos nos instantâneos do DOM do trace (dígitos de OTP/PIN)
    (re.compile(r'(\["__playwright_value_"\s*,\s*")\d{1,8}(")'), r"\1*\2"),
]


class Gravador:
    def __init__(self):
        self.pasta: Path | None = None
        self.contextos: list = []
        self.segredos: set[str] = set()
        self.n = 0
        self._digitos = ""

    @property
    def ativo(self) -> bool:
        return self.pasta is not None

    def iniciar(self, pasta) -> None:
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.contextos, self.n = [], 0

    def segredo(self, valor) -> None:
        if isinstance(valor, str) and len(valor) >= 3:
            self.segredos.add(valor)

    def digito(self, valor) -> None:
        """Dígitos do código MFA escritos um a um ([data-role=mfa-digit]): ao 6.º, o código conta como segredo."""
        self._digitos = (self._digitos + valor)[-6:]
        if len(self._digitos) == 6:
            self.segredo(self._digitos)
            self._digitos = ""

    def todos_os_segredos(self) -> list[str]:
        s = set(self.segredos)
        for v in VARIAVEIS_SECRETAS:
            if len(os.environ.get(v, "")) >= 3:
                s.add(os.environ[v])
        return sorted(s, key=len, reverse=True)

    def fechar_pendentes(self) -> None:
        """Fecha os contextos que o teste deixou abertos (para gravar trace e vídeo)."""
        for ctx in list(self.contextos):
            with contextlib.suppress(Exception):
                ctx.close()

    def terminar(self, manter: bool, destino=None) -> list[Path]:
        """Fecha o que ficou aberto; se manter, redige e move os artefactos para destino; senão apaga-os."""
        if not self.ativo:
            return []
        self.fechar_pendentes()
        pasta, self.pasta = self.pasta, None
        movidos = []
        if manter and destino is not None:
            destino = Path(destino)
            destino.mkdir(parents=True, exist_ok=True)
            segredos = self.todos_os_segredos()
            for f in sorted(pasta.rglob("*")):
                if f.is_file() and f.stat().st_size and f.parent.name != "_video":
                    alvo = destino / f.name
                    shutil.move(str(f), alvo)
                    redigir_ficheiro(alvo, segredos)
                    movidos.append(alvo)
        shutil.rmtree(pasta, ignore_errors=True)
        return movidos


GRAVADOR = Gravador()


def redigir(texto: str, segredos=()) -> str:
    """Substitui segredos conhecidos e padrões sensíveis por ***."""
    for s in segredos:
        for forma in {s, json.dumps(s)[1:-1], urllib.parse.quote(s, safe=""), urllib.parse.quote_plus(s)}:
            texto = texto.replace(forma, "***")
    for rx, sub in REGRAS:
        texto = rx.sub(sub, texto)
    return texto


def _redigir_acoes(texto: str) -> str:
    """Linhas JSON do trace: o valor escrito em campos secretos (ou dígitos no teclado) passa a ***."""
    linhas = []
    for linha in texto.splitlines(keepends=True):
        try:
            ev = json.loads(linha)
        except ValueError:
            linhas.append(linha)
            continue
        params = ev.get("params") if isinstance(ev, dict) else None
        if isinstance(params, dict) and ev.get("method") in METODOS_ESCRITA:
            alvo = str(params.get("selector", ""))
            for chave in ("value", "text"):
                v = params.get(chave)
                if isinstance(v, str) and v and (CAMPO_SECRETO.search(alvo) or (
                        str(ev.get("method")).startswith("keyboard") and re.fullmatch(r"\d{1,8}", v))):
                    params[chave] = "***"
            linha = json.dumps(ev, ensure_ascii=False) + ("\n" if linha.endswith("\n") else "")
        linhas.append(linha)
    return "".join(linhas)


def _redigir_bytes(dados: bytes, segredos, nome: str = "") -> bytes:
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError:
        return dados                      # imagens/vídeo: o mascaramento é feito no ecrã (CSS)
    if nome.endswith(".trace"):
        texto = _redigir_acoes(texto)
    return redigir(texto, segredos).encode("utf-8")


def redigir_ficheiro(f: Path, segredos=None) -> None:
    segredos = GRAVADOR.todos_os_segredos() if segredos is None else segredos
    f = Path(f)
    if f.suffix == ".zip":
        tmp = f.with_suffix(".tmp.zip")
        with zipfile.ZipFile(f) as zi, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
            for m in zi.infolist():
                zo.writestr(m, _redigir_bytes(zi.read(m), segredos, m.filename))
        tmp.replace(f)
    elif f.suffix.lower() in (".md", ".txt", ".log", ".json", ".xml", ".yaml", ".yml", ".tsv", ".html", ".har"):
        f.write_bytes(_redigir_bytes(f.read_bytes(), segredos))


def _nota(texto: str) -> None:
    if GRAVADOR.pasta is not None:
        with (GRAVADOR.pasta / "notas_gravacao.txt").open("a", encoding="utf-8") as h:
            h.write(texto + "\n")


_INSTALADO = False


def instalar() -> None:
    """Instrumenta o Playwright (sync). Idempotente. Sem GRAVADOR.iniciar() não grava nada."""
    global _INSTALADO
    if _INSTALADO:
        return
    from playwright.sync_api import Browser, BrowserContext, Keyboard, Locator, Page

    orig_new_context, orig_close = Browser.new_context, BrowserContext.close

    def new_context(self, *args, **kw):
        g = GRAVADOR
        if not g.ativo:
            return orig_new_context(self, *args, **kw)
        proprio = bool(kw.get("record_video_dir"))
        if not proprio:
            kw["record_video_dir"] = str(g.pasta / "_video")
            if kw.get("viewport"):
                kw.setdefault("record_video_size", kw["viewport"])
        ctx = orig_new_context(self, *args, **kw)
        try:
            ctx.add_init_script(script=JS_MASCARA)
            ctx.tracing.start(screenshots=True, snapshots=True, sources=True)
            ctx._qa_trace = True
        except Exception as e:  # noqa: BLE001
            _nota(f"trace não iniciado: {type(e).__name__}")
        g.contextos.append(ctx)
        return ctx

    def close(self, *args, **kw):
        g = GRAVADOR
        if self not in g.contextos or g.pasta is None:
            return orig_close(self, *args, **kw)
        g.contextos.remove(self)
        g.n += 1
        n, pasta = g.n, g.pasta
        videos = []
        for i, pg in enumerate(self.pages, 1):
            try:
                if not pg.is_closed():
                    pg.screenshot(path=str(pasta / f"captura_final_contexto{n}_pagina{i}.png"), full_page=True, timeout=5000)
            except Exception as e:  # noqa: BLE001
                _nota(f"captura do contexto {n} falhou: {type(e).__name__}")
            if pg.video:
                videos.append(pg.video)
        if getattr(self, "_qa_trace", False):
            try:
                self.tracing.stop(path=str(pasta / f"trace_contexto{n}.zip"))
            except Exception as e:  # noqa: BLE001
                _nota(f"trace do contexto {n} não gravado: {type(e).__name__}")
        r = orig_close(self, *args, **kw)
        for i, v in enumerate(videos, 1):
            try:
                origem = Path(v.path())
                if origem.exists():
                    shutil.copy2(origem, pasta / f"video_contexto{n}_pagina{i}.webm")
            except Exception as e:  # noqa: BLE001
                _nota(f"vídeo do contexto {n} não copiado: {type(e).__name__}")
        return r

    def _seletor(loc) -> str:
        return str(getattr(getattr(loc, "_impl_obj", None), "_selector", ""))

    def _guardar_se_secreto(alvo: str, valor, teclado: bool = False) -> None:
        if not isinstance(valor, str):
            return
        if "mfa-digit" in alvo and re.fullmatch(r"\d", valor):
            GRAVADOR.digito(valor)
        elif CAMPO_SECRETO.search(alvo) or (teclado and re.fullmatch(r"\d{4,8}", valor)):
            GRAVADOR.segredo(valor)

    orig_loc_fill, orig_loc_type, orig_loc_ps = Locator.fill, Locator.type, Locator.press_sequentially
    orig_pg_fill, orig_pg_type, orig_kb_type, orig_kb_insert = Page.fill, Page.type, Keyboard.type, Keyboard.insert_text

    def loc_fill(self, value, *a, **k):
        _guardar_se_secreto(_seletor(self), value)
        return orig_loc_fill(self, value, *a, **k)

    def loc_type(self, text, *a, **k):
        _guardar_se_secreto(_seletor(self), text)
        return orig_loc_type(self, text, *a, **k)

    def loc_ps(self, text, *a, **k):
        _guardar_se_secreto(_seletor(self), text)
        return orig_loc_ps(self, text, *a, **k)

    def pg_fill(self, selector, value, *a, **k):
        _guardar_se_secreto(selector, value)
        return orig_pg_fill(self, selector, value, *a, **k)

    def pg_type(self, selector, text, *a, **k):
        _guardar_se_secreto(selector, text)
        return orig_pg_type(self, selector, text, *a, **k)

    def kb_type(self, text, *a, **k):
        _guardar_se_secreto("", text, teclado=True)   # teclado: códigos MFA (só dígitos) contam como segredo
        return orig_kb_type(self, text, *a, **k)

    def kb_insert(self, text, *a, **k):
        _guardar_se_secreto("", text, teclado=True)
        return orig_kb_insert(self, text, *a, **k)

    Browser.new_context, BrowserContext.close = new_context, close
    Locator.fill, Locator.type, Locator.press_sequentially = loc_fill, loc_type, loc_ps
    Page.fill, Page.type, Keyboard.type, Keyboard.insert_text = pg_fill, pg_type, kb_type, kb_insert
    _INSTALADO = True


def main(argv=None) -> int:
    """Corre um script autónomo com a gravação ligada.

    python -m automacao._comum.gravacao_falhas --artefactos PASTA [--redigir OUTRA ...] -- script.py args…
    No fim, redige (segredos escritos no browser + variáveis secretas) tudo em PASTA e em cada --redigir.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv:
        argv.append("--")
    corte = argv.index("--")
    opcoes, resto = argv[:corte], argv[corte + 1:]
    pasta, extra = None, []
    for chave, valor in zip(opcoes[::2], opcoes[1::2]):
        if chave == "--artefactos":
            pasta = Path(valor)
        elif chave == "--redigir":
            extra.append(Path(valor))
    if pasta is None or not resto or len(opcoes) % 2:
        print("uso: python -m automacao._comum.gravacao_falhas --artefactos PASTA [--redigir OUTRA] -- script.py [args…]",
              file=sys.stderr)
        return 64
    script, resto = resto[0], resto[1:]
    instalar()
    GRAVADOR.iniciar(pasta)
    sys.argv = [script, *resto]
    sys.path.insert(0, str(Path(script).resolve().parent))
    codigo = 0
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit as e:
        codigo = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if e.code is not None and not isinstance(e.code, int):
            print(e.code, file=sys.stderr)
    finally:
        GRAVADOR.fechar_pendentes()
        segredos = GRAVADOR.todos_os_segredos()
        for raiz in (pasta, *extra):
            for f in (raiz.rglob("*") if raiz.exists() else []):
                if f.is_file() and "_video" not in f.parts:
                    redigir_ficheiro(f, segredos)
        shutil.rmtree(pasta / "_video", ignore_errors=True)
        GRAVADOR.pasta = None
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
