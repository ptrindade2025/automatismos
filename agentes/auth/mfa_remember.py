"""Cookie mfa_remember (MFA_REMEMBER_TTL). O valor vem cifrado pelo Laravel: nunca é escrito, só o tamanho."""
import time
from playwright.sync_api import expect


def cookie_remember(ctx, nome="mfa_remember"):
    return next((c for c in ctx.cookies() if c["name"] == nome), None)


def verificar_cookie(ps, ctx, cfg):
    """Asserta httpOnly, SameSite Lax, path / e expiração em (ttl - margem, ttl]; nota com o valor mascarado."""
    r = cfg["mfa_remember"]
    c = cookie_remember(ctx, r["cookie"])
    assert c, "cookie mfa_remember não existe"
    resta = c["expires"] - time.time()
    v = c["value"]
    ps.nota(f"cookie {c['name']}: valor {'=' + v if v.isdigit() else 'cifrado (' + str(len(v)) + ' car., mascarado)'}; "
            f"httpOnly={c['httpOnly']}; SameSite={c['sameSite']}; path={c['path']}; expira em {resta / 60:.1f} min")
    assert c["httpOnly"] and c["sameSite"] == "Lax" and c["path"] == "/", c["name"]
    assert r["ttl_s"] - r["margem_s"] < resta <= r["ttl_s"] + 5, f"expiração {resta:.0f} s fora de ~{r['ttl_s']} s"
    return c


def mfa_config(cfg):
    """Bloco mfa_config do yaml, com sobreposição pelas variáveis de ambiente. Nunca fixar estes valores no script."""
    import os
    m = dict(cfg["mfa_config"])
    env = {"MFA_IS_ENABLE": ("is_enable", lambda v: v.lower() == "true"), "MFA_TTL": ("ttl_s", int),
           "MFA_REMEMBER_TTL": ("remember_ttl_s", int), "MFA_RETRY_AFTER_BO": ("retry_after_bo", int)}
    for var, (chave, conv) in env.items():
        if os.environ.get(var):
            m[chave] = conv(os.environ[var])
    return m


def countdown_reenviar(page):
    """Segundos mostrados em «Reenviar código (Ns)» (None se o botão não mostrar contagem)."""
    import re
    b = page.get_by_role("button", name=re.compile("Reenviar", re.I))
    expect(b).to_have_text(re.compile(r"\(\d+\s*s\)"))
    return int(re.search(r"\((\d+)\s*s\)", b.inner_text()).group(1))
