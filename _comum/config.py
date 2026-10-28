"""Configuração comum da biblioteca de procedimentos de QA.

Todas as credenciais vêm de variáveis de ambiente; nada é gravado em ficheiro.
Os URL podem ser substituídos por variáveis de ambiente (ZW_URL, AW_URL).
"""
import os
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
QA_RUNNER = HOME / "GrokBot" / "qa-runner"
STATE_DIR = HOME / "GrokBot" / "zw"          # storage_state do Playwright (chmod 600)

ZW_URL_PP = "http://zwao.pp.zap.intra/"
ZW_URL_QA = "http://10.151.58.27/zwptrindade2/"
AW_URL_PP = "http://agentesarp2.pp.zap.intra"


# Segredos que podem vir do keyring do pc-pit (libsecret) quando não estão no ambiente.
# O Pit guarda-os com: secret-tool store --label="P0733 AW_SECRET" service p0733 name AW_SECRET
KEYRING = {"AW_SECRET": {"service": "p0733", "name": "AW_SECRET"}}


class SegredoIndisponivel(RuntimeError):
    """Erro sem valores: só diz que o segredo não foi encontrado e porquê."""


# Lido pelo python do sistema quando o processo corre num venv sem gi. O valor sai só pelo stdout do subprocess
# (capture_output, em memória); os argumentos são só os atributos.
_LER_GI = (
    "import sys,gi;gi.require_version('Secret','1');from gi.repository import Secret as S;"
    "a=sys.argv[1:];at=dict(zip(a[::2],a[1::2]));"
    "e=S.Schema.new('org.freedesktop.Secret.Generic',S.SchemaFlags.DONT_MATCH_NAME,{k:S.SchemaAttributeType.STRING for k in at});"
    "v=S.password_lookup_sync(e,at,None);sys.stdout.write(v+chr(10) if v else '')"
)


def _keyring(nome: str) -> str | None:
    """Lê o segredo do keyring em memória. Nunca imprime, regista nem grava o valor.

    1.º libsecret em processo (gi.repository.Secret; já instalado no pc-pit, sem sudo);
    2.º venv sem gi: /usr/bin/python3 com gi em subprocess; 3.º `secret-tool lookup` (subprocess com capture_output;
        os argumentos são só os atributos, nunca o valor).
    Guardar: scripts/keyring_aw_secret.py guardar (pede o valor sem eco).
    """
    atrib = KEYRING.get(nome)
    if not atrib:
        return None
    try:
        import gi
        gi.require_version("Secret", "1")
        from gi.repository import Secret
    except (ImportError, ValueError):
        Secret = None
    if Secret is not None:
        try:
            esquema = Secret.Schema.new("org.freedesktop.Secret.Generic", Secret.SchemaFlags.DONT_MATCH_NAME,
                                        {k: Secret.SchemaAttributeType.STRING for k in atrib})
            return Secret.password_lookup_sync(esquema, dict(atrib), None) or None
        except Exception as e:  # mensagem sem valores
            raise SegredoIndisponivel(f"{nome}: keyring inacessível ({type(e).__name__})") from None
    import shutil, subprocess
    if Path("/usr/bin/python3").exists():          # venv sem gi: o python do sistema tem gi.repository.Secret
        args = ["/usr/bin/python3", "-c", _LER_GI] + [x for k, v in atrib.items() for x in (k, v)]
    elif shutil.which("secret-tool"):
        args = ["secret-tool", "lookup"] + [x for k, v in atrib.items() for x in (k, v)]
    else:
        raise SegredoIndisponivel(f"{nome}: sem libsecret (gi) nem secret-tool")
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise SegredoIndisponivel(f"{nome}: o keyring não respondeu em 20 s (sessão bloqueada?)") from None
    valor = r.stdout[:-1] if r.stdout.endswith("\n") else r.stdout
    del r
    return valor or None


def env(nome: str) -> str:
    """Devolve a variável obrigatória (ambiente; para AW_SECRET, keyring como alternativa).

    Termina com mensagem clara, sem mostrar valores. O valor do keyring não é posto em os.environ,
    para não passar aos processos filhos (Chrome).
    """
    valor = os.environ.get(nome)
    if not valor:
        try:
            valor = _keyring(nome)
        except SegredoIndisponivel as e:
            raise SystemExit(f"Segredo indisponível: {e}") from None
    if not valor:
        onde = " nem no keyring (service/name: " + "/".join(KEYRING[nome].values()) + ")" if nome in KEYRING else ""
        raise SystemExit(f"Variável de ambiente em falta: {nome}{onde}")
    return valor


def novo_browser(p, headless: bool = True, slow_mo: int = 0):
    """Abre o Chrome do sistema com as opções usadas nos scripts existentes."""
    return p.chromium.launch(channel="chrome", headless=headless, slow_mo=slow_mo)


def guardar_estado(ctx, nome: str) -> Path:
    """Grava o storage_state com permissões 600."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    st = STATE_DIR / f"state_{nome}.json"
    ctx.storage_state(path=str(st))
    os.chmod(st, 0o600)
    return st
