# Relatório de Implementação: confirmação inline da árvore de pastas

## Resultado

A jornada de `New run` agora termina na etapa 3. A localização é definida primeiro; em seguida, a hierarquia e a árvore final são exibidas na mesma tela. O usuário precisa marcar a aprovação da estrutura para habilitar `Start download`.

## Entregas

- Removida a etapa 4 e o painel de revisão separado; a jornada agora termina na etapa 3.
- Removido o `confirm()` específico da árvore de pastas.
- Movida a escolha do destino para o início da etapa 3.
- Adicionado checkbox de aprovação junto à árvore final na etapa 3.
- O CTA único da barra flutuante da etapa 3 agora chama diretamente o fluxo de `Start download` e só é habilitado com destino, hierarquia e aprovação válidos.
- O checkbox é invalidado quando o destino ou a hierarquia muda.
- Ajustados textos em inglês e português, estilos e teste E2E.
- Consolidado o CTA principal na barra flutuante: ele executa a ação da etapa ativa e muda entre continuar a validação, continuar para pastas e iniciar o download.
- Removidos os CTAs duplicados dos rodapés dos cards; os rodapés mantêm apenas navegação secundária e a ação de reinício.
- Reintroduzido `Start over` na barra flutuante como ação secundária persistente durante a preparação; ele limpa o estado do draft, filtros, hierarquia, destino e aprovação, preservando histórico e arquivos baixados.
- O reset fica indisponível durante uma execução ativa; após a execução terminar ou ser parada, o usuário pode voltar à Nova execução e reabrir a etapa 1 com a seleção de Excel pronta para um novo input.
- Corrigido o reset do Power BI para reconstruir o dropdown a partir do cache persistente, sem apagar temporariamente os valores disponíveis.

## Arquivos principais

- `ContractDownloader/src/gui/web/index.html`
- `ContractDownloader/src/gui/web/app.js`
- `ContractDownloader/src/gui/web/style.css`
- `ContractDownloader/tests/e2e/test_gui_hierarchy_workflow.py`

## Verificação

- `node --check ContractDownloader/src/gui/web/app.js` — passou.
- `./.venv/bin/pytest tests/test_powerbi_hierarchy.py tests/test_gui_api.py::test_reset_new_run_deletes_only_app_generated_template -q` — 6 passaram.
- O teste de regressão confirma que `Start over` chama `showPowerBICacheResults()` e não zera `powerbiSearchResults`.
- `./.venv/bin/pytest tests/e2e/test_gui_hierarchy_workflow.py -k 'final_folder_approval or hierarchy_disable_survives_revalidation' -q` — 2 passaram.
- O teste E2E de reordenação continua com falha preexistente por duplicação de níveis `SUPPLIER` no fixture; não é causado pela consolidação da jornada.
- `./.venv/bin/pytest tests/test_cli_supervisor.py -q` — 12 passaram.
- `./.venv/bin/pytest tests/test_cli_supervisor.py tests/test_powerbi_hierarchy.py -q` — 16 passaram.
- Teste E2E específico da aprovação inline — passou.
- Testes E2E de navegação com CTA superior e aprovação — 2 passaram.
- O probe amplo alcançou `Start over`, reselecionou o input e iniciou novamente; falhou depois no clique do botão de pausa por interceptação visual no Active run.
- A suíte E2E completa executou 3 testes, pulou 1 e manteve 2 falhas preexistentes relacionadas à contagem/duplicação de níveis da hierarquia, fora deste fluxo.
- A inspeção visual pelo navegador embutido foi bloqueada pela política para URLs `file://`; a ordem também foi coberta pelo DOM do teste E2E.
