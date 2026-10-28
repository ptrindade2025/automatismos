"""Autenticação no ZW (Zapweb).

Origem: _comum/scripts/login_zw.py, _comum/scripts/zw_session.py e
_comum/scripts/smoke_login_logout_zw.py.

## login(pg, base_url, utilizador_env, password_env)
- **Objetivo:** autenticar um utilizador no ZW.
- **Pré-condições:** utilizador ativo com perfil e loja; variáveis ZW_USER e ZW_PASS definidas
  (ou as indicadas nos parâmetros).
- **Parâmetros:** pg (página Playwright); base_url (por omissão ZW PP); nomes das variáveis de ambiente.
- **Passos:** abrir base_url; preencher input[name=login] e input[name=pass]; submeter.
- **Seletores:** atributos name do formulário (sem label/data-testid confirmados; «a confirmar»).
- **Resultado esperado:** o formulário de login desaparece; devolve True. Levanta erro se falhar.
- **Casos que o usam:** smoke de login/logout ZW; P0704-45/46 (pré-condição).

## abrir_sessao(p, utilizador, base_url)
- **Objetivo:** reutilizar o storage_state guardado ou, se inválido, autenticar e guardá-lo.
- **Resultado esperado:** devolve (browser, contexto, página) autenticados em ?p=start.

## logout(pg)
- **Objetivo:** terminar a sessão pelo link «Logout|Sair».
- **Resultado esperado:** o link deixa de estar visível.
"""
import re
from playwright.sync_api import expect
from automacao._comum.config import ZW_URL_PP, env, novo_browser, guardar_estado, STATE_DIR

SUBMETER = "input[type=submit][value=Entrar], input[type=submit][name=submit]"


def login(pg, base_url: str = ZW_URL_PP, utilizador_env: str = "ZW_USER",
          password_env: str = "ZW_PASS") -> bool:
    pg.goto(base_url)
    campo_login, campo_pass = pg.locator("input[name=login]"), pg.locator("input[name=pass]")
    # Esperado: formulário de login com utilizador e palavra-passe visíveis
    expect(campo_login).to_be_visible()
    expect(campo_pass).to_be_visible()
    campo_login.fill(env(utilizador_env))
    campo_pass.fill(env(password_env))
    pg.locator(SUBMETER).first.click()
    pg.wait_for_load_state("networkidle")
    # Esperado: o formulário de login desaparece (sessão aberta)
    expect(campo_pass, "login ZW falhou: o formulário de login continua visível").to_have_count(0)
    return True


def abrir_sessao(p, utilizador: str, base_url: str = ZW_URL_PP, headless: bool = True,
                 dialog_handler=None):
    st = STATE_DIR / f"state_{utilizador}.json"
    b = novo_browser(p, headless=headless)
    ctx = b.new_context(viewport={"width": 1400, "height": 900},
                        storage_state=str(st) if st.exists() else None)
    pg = ctx.new_page()
    pg.on("dialog", dialog_handler or (lambda d: (print(f"DIALOG[{d.type}]:", d.message), d.dismiss())))
    pg.goto(base_url + "?p=start", wait_until="networkidle")
    if pg.locator("input[name=login]").count():  # decisão de fluxo (estado guardado inválido), não asserção
        login(pg, base_url)
        guardar_estado(ctx, utilizador)
    return b, ctx, pg


def logout(pg) -> None:
    link = pg.get_by_role("link", name=re.compile(r"Logout|Sair", re.I)).first
    link.click()
    # Esperado: volta ao formulário de login e o link deixa de existir
    expect(pg.locator("input[name=pass]")).to_be_visible()
    expect(link).to_have_count(0)
