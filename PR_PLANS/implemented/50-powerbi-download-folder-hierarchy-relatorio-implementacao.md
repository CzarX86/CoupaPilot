# Relatório de Implementação: Hierarquia de pastas do download Power BI

## Resultado

O download iniciado a partir do Power BI agora suporta CRG e Ano como níveis opcionais da hierarquia de pastas. O fornecedor continua sendo um único nível inicial, e os códigos Supplier GU/S não criam subpastas.

## Entregas

- campos `CRG` e `Year` adicionados ao catálogo Power BI com as referências semânticas confirmadas;
- CRG e Ano incluídos no preview/snapshot mesmo quando não fazem parte da seleção analítica persistida;
- códigos Supplier GU/S preservados como metadados antes de `<|>`;
- seleção explícita da UI respeitada pelo worker, sem fallback para todos os campos;
- deduplicação de níveis e valores de pasta, corrigindo estruturas repetidas como `EY/EY/EY`;
- tentativa de início não revalida novamente um input já validado, preservando CRG/Ano quando a checagem de caminho reprova a execução;
- recuperação de retry alinhada à ordem de hierarquia selecionada;
- regressões automatizadas para CRG/Ano e duplicação do fornecedor.

## Arquivos principais

- `ContractDownloader/src/powerbi_provider.py`
- `ContractDownloader/src/main.py`
- `ContractDownloader/process_all_pos.py`
- `ContractDownloader/src/gui/api.py`
- `ContractDownloader/src/gui/web/app.js`
- `ContractDownloader/tests/test_powerbi_provider.py`
- `ContractDownloader/tests/test_powerbi_hierarchy.py`
- `ContractDownloader/tests/test_gui_api.py`

## Verificações

- `uv run pytest tests/test_powerbi_provider.py tests/test_powerbi_hierarchy.py tests/test_gui_api.py -q`: `84 passed`;
- `uv run pytest -q --ignore=tests/e2e`: `308 passed`;
- `uv run python -m compileall -q ...`: aprovado;
- `node --check src/gui/web/app.js`: aprovado;
- `uv run --group build python -m PyInstaller --noconfirm ContractDownloader.spec`: bundle macOS recompilado e sincronizado com `ContractDownloader.app`.

A suíte completa foi tentada; 14 testes E2E falharam porque o executável Chromium do Playwright não está instalado neste ambiente. Essa limitação é externa ao código alterado; os testes não-E2E passaram integralmente.
