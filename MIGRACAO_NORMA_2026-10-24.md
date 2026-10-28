# Migração para a norma de asserções (24/10/2026)

**Âmbito:** biblioteca `automacao/`, scripts P0733 (suite SZA 263) e os 4 scripts do `qa-runner` com PIN.
**Validação:** só `python -m py_compile`, importação dos módulos e `pytest --collect-only` (15 testes recolhidos; filtro `--caso` verificado). **Nada foi executado contra aplicações Zap.**
**Backups:** cada ficheiro alterado tem cópia `<ficheiro>.bak-20261024-104102`. Nada foi apagado.

## Resumo
- 4 módulos da biblioteca migrados; 1 com ajuste menor (`codigo_mfa.py`).
- 4 scripts do `qa-runner`: PIN/credenciais passaram para variáveis de ambiente.
- Nova suite pytest P0733 em `projetos/P0733-seguranca-zap-agentes/testes/` (4 ficheiros novos) que substitui, para execuções futuras, os 7 scripts de execução SZA.
- Documentação atualizada: `CATALOGO.md`, `projetos/P0733-seguranca-zap-agentes/scripts/LEIA-ME.md`.

## Biblioteca
| Ficheiro | O que mudou | A confirmar |
|---|---|---|
| `agentes/auth/login.py` | Reescrito. Sem `wait_for_timeout` (3); `expect` para ecrã /login, URL de destino e «Introduza o código». Novos `escolher_email`, `pedir_codigo`, `validar_codigo`. `login_credenciais` ganhou `url_esperado` e `utilizador` (compatível com as chamadas antigas). `preencher_codigo` deixou o fallback silencioso para `input:visible`. Canal E-mail por `get_by_label`. | Os campos de login continuam por id (`#input-login-*`): não há label nem `data-testid` confirmados. `get_by_label("E-mail")` assume que o rótulo envolve o rádio. |
| `agentes/auth/codigo_mfa.py` | `time.monotonic` e comentários. | Mantém `time.sleep(1)` na **sondagem da BD** (não é espera de UI). Exceção à norma a aprovar pelo Pit. |
| `zw/auth/login.py` | `expect` para formulário visível e desaparecimento do formulário (substitui verificação manual); `logout` verifica regresso ao login. Assinaturas iguais. | Seletores por `name` (sem label/`data-testid`). |
| `zw/vendas/criar_aquisicao.py` | 3 esperas fixas retiradas; `expect` de «Conta: <conta>» e do valor da loja; login de `abrir()` com `input[name=login/pass]` e `expect`. Dict devolvido inalterado (é observação; o caso 121 aceita os dois resultados). | Perdeu o estado «validado»: precisa de nova execução autorizada. `is_visible` mantém-se apenas como dado registado, não como asserção. |
| `zw/vendas/pagar_aquisicao.py` | 11 esperas fixas retiradas (load_state + `expect`); botões por `get_by_role`; `expect` do item marcado, do modo de pagamento e da loja. `abrir_aq` falha se o número da aquisição não aparecer. Valores devolvidos iguais (usados por `venda_loja.py`). | Seletores por confirmar na 1.ª execução (já era «não validado»). O `#estado` e o `accao_remover` podem abrir janelas assíncronas: confirmar que `networkidle` chega. |
| `_comum/config.py` | Sem alterações (só backup). | — |

## qa-runner (PIN)
| Ficheiro | O que mudou |
|---|---|
| `explora.py`, `renomear.py` | PIN escrito no código → `AW_PIN` (utilizador por `AW_USER`, por omissão 27243562). `renomear.py`: `try/except: pass` → `wait_for_event("close", timeout=0)`. |
| `login.py`, `visivel.py` | PIN/palavra-passe na linha de comandos (`sys.argv`) → `AW_USER`/`AW_PIN`. `visivel.py`: `except` silencioso retirado. |

**Atenção:** o PIN antigo continua nos backups (`*.bak-20261024-104102`) destes 2 ficheiros e no histórico. Apagar ou limpar exige autorização do Pit.
Estes scripts são exploratórios: as esperas fixas e seletores CSS restantes não foram migrados.

## P0733 · suite SZA 263 (novos)
| Ficheiro | Conteúdo |
|---|---|
| `testes/pytest.ini` | Marcadores `caso`, `escreve`, `a_confirmar`, `ci`, `qa_only`. |
| `testes/conftest.py` | Fixtures `browser`, `contexto`, `page`, `cfg`; opções `--config`, `--base-url-aw`, `--caso`, `--permitir-escrita`, `--headed`. Segredos só em `AW_SECRET`/`AW_PIN`. |
| `testes/config/sza263.yaml` | Contas, emails, URLs e mensagens da revisão SZA-263 (sem segredos). Textos corretos: «Credenciais inválidas» (NC-02) e «Dados atualizados com êxito» (NC-17). |
| `testes/test_sza263.py` | 15 testes (701–715) com `expect` por passo, comentado com P1…P4. 707 e 712 marcados `escreve` (só correm com `--permitir-escrita`). |

Scripts antigos (`sza_run2.py`, `sza_run2b.py`, `mfa_suite.py`, `mfa_707_712.py`, `mfa_assoc.py`, `mfa_709.py`, `sza704_r2.py`, `explore_*.py`) **não foram alterados**: são o histórico das runs 1 e 2 e continuam fora da norma. Os `qase_*.py` não usam Playwright.

### A confirmar na suite
- **703:** validade do código (LAC-01). A espera de 35 s é `time.sleep` de regra de negócio (TTL no servidor): exceção à norma a aprovar.
- **705:** o esperado é /login/mfa; hoje a app vai para /login («A sessão terminou»), por isso o teste deve falhar.
- **706:** o teste falha enquanto existir a NC-14.
- **707/709:** texto do caso mistura SMS e email; asserções feitas no equivalente email.
- **711:** mensagens de formato (NC-18/19) e P7 (LAC-03). Só se verifica que não avança.
- **712:** esperado de segurança (1184); nome do botão (Confirmar/Guardar/Gravar) e se pede palavra-passe.
- **713:** o login usa `AW_PIN`. Confirmar se GET /login/mfa devolve mesmo 404.
- **715:** tempo de bloqueio; dígitos e «Reenviar código» desativados (asserções por acrescentar).
- **Campo email:** `input[type=email]` por falta de label/`data-testid`.
- Countdown do «Reenviar» (`expect` com 60 s).
- Os casos 1181–1186 ainda não têm teste.

## Pendente
1. Primeira execução autorizada da suite e de `criar_aquisicao`/`pagar_aquisicao`, para confirmar seletores.
2. Aprovar as 2 exceções de `sleep` (sondagem da BD; expiração no 703).
3. Limpar o PIN dos backups (exige autorização).
4. `data-testid` nas aplicações (fica para quando a DEV entrar).
