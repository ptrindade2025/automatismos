"""Auxiliares MFA do Zap Agentes para casos de limite e sessão (SZA 1181–1186).

post_form: submete um POST real do browser (form criado na página com o _token CSRF actual),
para repetir pedidos ao canal/reenvio/validação sem depender do ecrã em que se está.
"""
from playwright.sync_api import Page


def post_form(pg: Page, url: str, campos: dict) -> None:
    with pg.expect_navigation():
        pg.evaluate("""([url, campos]) => {
            const t = document.querySelector('input[name=_token]')?.value
                   || document.querySelector('meta[name=csrf-token]')?.content;
            const f = document.createElement('form'); f.method = 'POST'; f.action = url;
            for (const [k, v] of Object.entries({_token: t, ...campos})) {
                const i = document.createElement('input'); i.type = 'hidden'; i.name = k; i.value = v; f.appendChild(i); }
            document.body.appendChild(f); f.submit(); }""", [url, campos])


def estados_sessao(pg: Page, caminhos: list) -> dict:
    """GET XHR/JSON a cada caminho: {caminho: [estado|'redirect', corpo(200 car.)]}"""
    return pg.evaluate("""async (ps) => { const o = {}; for (const p of ps) {
        const r = await fetch(p, {redirect: 'manual', headers: {'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'}});
        o[p] = r.type === 'opaqueredirect' ? ['redirect', ''] : [r.status, (await r.text()).slice(0, 200)]; }
        return o; }""", caminhos)
