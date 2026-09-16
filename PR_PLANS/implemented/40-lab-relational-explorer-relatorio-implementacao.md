# Relatório de Implementação: explorador relacional da LAB

## Entrega

- subaba `Relationship Explorer` em `LAB`;
- API `get_lab_relationships` para consultar uma execução local;
- árvore SOW → PO → documentos com expansão individual e global;
- grade em estilo worksheet/Excel, com cabeçalho, número de linha, gridlines e indentação por nível;
- indicadores de SOW candidates, POs, invoices e warnings;
- validação de múltiplos SOWs por PO, invoices em múltiplas POs e relações ausentes;
- preview de navegador com dados simulados;
- documentação da limitação atual do schema.

## Verificação

- `node --check src/gui/web/app.js`: aprovado;
- `python3 -m py_compile src/reports/lab_relationships.py src/gui/api.py`: aprovado;
- `UV_CACHE_DIR=/tmp/coupa-lab-uv-cache uv run pytest tests/test_lab_relationships.py tests/test_session_db.py tests/test_gui_api.py -q`: 62 aprovados;
- `git diff --check`: aprovado.

## Limitação conhecida

O banco ainda não possui tabelas canônicas de SOW e invoice. Os números exibidos nesta feature são candidatos derivados dos nomes/hashes dos anexos e devem ser confirmados antes de serem usados como fonte oficial.
