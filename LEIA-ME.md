# Biblioteca de procedimentos automatizados de QA

Esta pasta reúne os passos de automação reutilizáveis (login, MFA, leitura de códigos, pagamentos), organizados por aplicação e por módulo. Os scripts dos projetos importam daqui e limitam-se a combinar procedimentos com os dados de cada caso.

## Estrutura

```
automacao/
├── CATALOGO.md          lista de procedimentos, origem e estado
├── _comum/              configuração, variáveis de ambiente, leitura da BD
├── zw/auth/             login, sessão e logout no ZW
├── zw/vendas/           aquisições e pagamentos
└── agentes/auth/        login e MFA no Zap Agentes
```

## Utilização num script de projeto

Os scripts ficam em `projetos/<P>/scripts/` e importam a biblioteca a partir de `~/GrokBot/QA`:

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/GrokBot/QA"))
from playwright.sync_api import sync_playwright
from automacao.zw.auth.login import abrir_sessao

with sync_playwright() as p:
    b, ctx, pg = abrir_sessao(p, "userqase")
    # ... passos do caso ...
    b.close()
```

Executar sempre com o Python do qa-runner: `~/GrokBot/qa-runner/.venv/bin/python`.

## Regras

1. Credenciais só em variáveis de ambiente (`ZW_USER`, `ZW_PASS`, `AW_USER`, `AW_PASS`, ou outras indicadas como parâmetro). Nunca escrever palavras-passe, PIN ou tokens em ficheiros, nem passá-los como argumentos da linha de comandos.
2. A BD é lida apenas através de `_comum/bd.py`, que usa o `dbq.py` (só SELECT, sessão READ ONLY) e exige LIMIT.
3. Procedimentos que escrevem nas aplicações Zap estão assinalados na ficha e só se executam com autorização explícita do Pit.
4. Cada procedimento novo leva uma ficha (docstring) com objetivo, pré-condições, parâmetros, passos, resultado esperado e casos que o usam, e uma linha no `CATALOGO.md`.
5. Um procedimento só passa a «validado» depois de correr com sucesso a partir da biblioteca; até lá, marcar «não validado».
6. Não alterar os scripts originais dos projetos; extrair para aqui e refatorar.
7. Repositório local: não fazer push.

## Manutenção

A manutenção cabe ao agente QA; o Aldrabao revê o código.

## Norma de asserções (obrigatória desde 2026-10-24)

**Desenho dos casos de teste:** cada passo tem um resultado esperado verificável:
- o texto visível exacto, ou a parte que importa;
- o ecrã ou URL de destino;
- o estado dos campos e botões, quando relevante;
- dados concretos.

O que ainda não se sabe fica marcado como «a confirmar». Nunca «é apresentada mensagem de erro» nem «sucesso».

**Scripts Playwright (Python):**
- Cada resultado esperado tem uma asserção web-first: `expect(locator).to_have_text / to_contain_text / to_have_value / to_be_enabled / to_be_disabled / to_be_visible` e `expect(page).to_have_url(...)`.
- Os seletores usam `get_by_role`, `get_by_label`, `get_by_text` ou `[data-testid]`. Sem XPath absoluto nem CSS frágil.
- Sem `wait_for_timeout` nem `time.sleep`; o auto-wait do `expect` trata das esperas.
- Sem `try/except` que silencie erros. O teste falha logo, com uma mensagem clara.
- Um comentário em cada asserção diz a que resultado esperado corresponde.
- As gralhas da aplicação são verificadas contra o texto correcto, para que o teste falhe até serem corrigidas.
