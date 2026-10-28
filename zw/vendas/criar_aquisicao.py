"""Criar uma aquisição no ZW pela UI (Aquisição > Criar), escolhendo a conta e a loja.

Origem: c0809.py / c121.py do run 5 da P0704-46 (23/10/2026). Validado em ZW QA (zwptrindade2), userqase01.
- **Objetivo:** abrir «Criar Aquisição» para uma conta, escolher a loja, ver se o Nº Contrato CRM é
  obrigatório e gravar (com ou sem contrato). Devolve o que a UI mostrou.
- **Pré-condições:** sessão ZW autenticada com acesso à loja. ESCREVE NA APLICAÇÃO se a gravação for aceite.
- **Resultado:** dict com conta mostrada, campo visível/obrigatório, alertas, nº da aquisição criada (ou None)
  e os caminhos das capturas de ecrã.
- **Casos que o usam:** P0704-46 caso 121 (TC-REQ-006-08).
- **Norma 2026-10-24:** esperas fixas substituídas por load_state/expect; o dict devolvido é observação
  (o caso 121 aceita ambos os resultados), por isso o veredicto continua no script do caso.
  Seletores por id/name do ZW (sem label/data-testid; «a confirmar»).
"""
import os
import re
from pathlib import Path
from playwright.sync_api import expect

U_QA = "http://10.151.58.27/zwptrindade2/"


def password_zw() -> str:
    """Password do ZW: variável ZWP ou ~/.config/p0704/zwp (chmod 600). Nunca é escrita nem mostrada."""
    k = os.environ.get("ZWP", "").strip()
    f = Path(os.path.expanduser("~/.config/p0704/zwp"))
    if not k and f.exists():
        if f.stat().st_mode & 0o077:
            raise SystemExit(f"{f} tem de ter permissões 600.")
        k = f.read_text().strip()
    if not k:
        raise SystemExit("Password do ZW em falta (ZWP ou ~/.config/p0704/zwp).")
    return k


def abrir(p, utilizador: str, base: str = U_QA, video_dir: str | None = None):
    """Login no ZW; com video_dir grava vídeo da sessão (evidência de erros)."""
    b = p.chromium.launch(channel="chrome", headless=True)
    kw = {"viewport": {"width": 1366, "height": 900}}
    if video_dir:
        kw.update(record_video_dir=video_dir, record_video_size={"width": 1366, "height": 900})
    c = b.new_context(**kw)
    pg = c.new_page()
    pg.goto(base, timeout=30000)
    campo_login, campo_pass = pg.locator("input[name=login]"), pg.locator("input[name=pass]")
    # Esperado: formulário de login visível
    expect(campo_login).to_be_visible()
    campo_login.fill(utilizador)
    campo_pass.fill(password_zw())
    campo_pass.press("Enter")
    pg.wait_for_load_state("networkidle")
    # Esperado: sessão aberta (o formulário de login desaparece)
    expect(campo_pass, "Login no ZW falhou.").to_have_count(0)
    return b, c, pg


def criar_aquisicao(pg, conta: str, idloja: str, pasta, prefixo: str, contrato: str | None = None,
                    base: str = U_QA) -> dict:
    alertas: list[str] = []
    pg.on("dialog", lambda d: (alertas.append(d.message), d.accept()))
    pasta = Path(pasta); pasta.mkdir(parents=True, exist_ok=True)
    pg.goto(base + "?p=aquisicao&opcao=criar"); pg.wait_for_load_state("networkidle")
    pg.select_option("#fastcampo", "codigoconta"); pg.fill("#fastvalor", conta); pg.press("#fastvalor", "Enter")
    pg.wait_for_load_state("networkidle")
    pg.goto(base + "?p=aquisicao&opcao=criar"); pg.wait_for_load_state("networkidle")
    # Esperado: o formulário mostra «Conta: <conta>» (FAST aplicou a conta)
    expect(pg.get_by_text(re.compile(rf"Conta:\s*{re.escape(conta)}")).first).to_be_visible()
    t = pg.inner_text("body")
    m = re.search(r"Conta:\s*(\d{10})", t); cli = re.search(r"Cliente:\s*(.+)", t)
    pg.select_option("#selectLoja", idloja); pg.evaluate("$('#selectLoja').trigger('change')")
    # Esperado: loja escolhida aplicada no seletor
    expect(pg.locator("#selectLoja")).to_have_value(str(idloja))
    pg.wait_for_load_state("networkidle")
    campo = pg.locator("#inputContratoCrm")
    if contrato:
        campo.fill(contrato)
    r = {"conta_mostrada": m and m.group(1), "cliente_mostrado": cli and cli.group(1).strip(),
         "loja": pg.locator("#selectLoja option:checked").inner_text().strip(),
         "campo_contrato_visivel": campo.is_visible(),  # observação registada (o caso decide), não asserção
         "data_obrigatorio": campo.get_attribute("data-obrigatorio"),
         "contrato_preenchido": contrato or ""}
    r["captura_antes"] = str(pasta / f"{prefixo}_1_formulario_preenchido.png")
    pg.screenshot(path=r["captura_antes"], full_page=True)
    pg.click("input[name=submeter]"); pg.wait_for_load_state("networkidle")
    r["captura_depois"] = str(pasta / f"{prefixo}_2_depois_de_gravar.png")
    pg.screenshot(path=r["captura_depois"], full_page=True)
    t = pg.inner_text("body"); c = re.search(r"Aquisição (\d+) criada com sucesso", t)
    r.update(alertas=list(alertas), aquisicao_criada=c and c.group(1),
             ficou_no_formulario=bool(pg.locator("input[name=submeter]").count()))
    return r
