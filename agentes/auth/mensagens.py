"""Leitura das mensagens visíveis (toasts/alertas/erros de formulário) na app Zap Agentes."""
import re

SELETOR_MSG = "[role=alert], .toast, .alert, .invalid-feedback, .text-danger, .swal2-popup"
ARTEFACTOS = re.compile(r'[{}\[\]]"|"\s*:|</?\w+[^>]*>|\\u[0-9a-f]{4}|&(quot|amp|lt|gt|#\d+);|\\n', re.I)


def mensagens_visiveis(pg) -> list[str]:
    loc = pg.locator(SELETOR_MSG)
    return [t.strip() for i in range(loc.count()) if loc.nth(i).is_visible() and (t := loc.nth(i).inner_text()).strip()]


def artefactos(texto: str) -> list[str]:
    """Fragmentos de JSON/HTML/escapes num texto que devia ser só prosa."""
    return [m.group(0) for m in ARTEFACTOS.finditer(texto)]
