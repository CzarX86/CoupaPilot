# Relatório de Implementação: invoices do Power BI no Relationship Explorer

## Entrega

- Relationship Explorer enriquecido com os datasets Power BI de PO e Invoice;
- commitment em EUR por PO e total indicativo de commitment no contrato/SOW;
- invoices exibidas como filhos da PO, com número, documento contábil, data e valores;
- número da SOW usado como chave principal do contrato;
- SHA-256 do anexo SOW usado como chave quando não há número identificável;
- nome de arquivo isolado deixou de ser usado como chave de contrato;
- fallback para a árvore local com aviso quando o Power BI não está disponível;
- preview local atualizado com invoices e commitments simulados.

## Arquivos principais

- `ContractDownloader/src/reports/lab_relationships.py`
- `ContractDownloader/src/powerbi_provider.py`
- `ContractDownloader/src/gui/api.py`
- `ContractDownloader/src/main.py`
- `ContractDownloader/src/gui/web/app.js`
- `ContractDownloader/src/gui/web/index.html`
- `tools/powerbi_ui_preview.py`

## Verificação

- `python3 -m py_compile src/reports/lab_relationships.py src/powerbi_provider.py src/gui/api.py src/main.py` — aprovado;
- `node --check src/gui/web/app.js` — aprovado;
- `git diff --check` — aprovado;
- testes direcionados de LAB, Power BI, hierarquia e API — `83 passed`;
- suíte sem E2E — `257 passed`;
- a suíte completa não ficou verde por falhas preexistentes nos E2E de hierarquia/jornada e no diagnóstico de Edge, dependentes do ambiente de navegador/cache; os testes da alteração permanecem aprovados.

## Limitação conhecida

O valor oficial do contrato ainda não é extraído do documento SOW. O total exibido no nível do contrato é a soma dos commitments das POs retornadas pelo Power BI e deve ser tratado como evidência operacional, não como valor contratual canônico.
