# Relatório de Implementação: correção de ordem e nomes da hierarquia

## Resultado

A ordem aprovada na interface agora chega ao worker sem reposicionar `Supplier`. Os nomes de pasta com barras invertidas ou múltiplos underscores são normalizados para um único `_`.

## Entregas

- `Supplier` pode permanecer no meio da hierarquia, por exemplo `Year/Supplier/CRG`;
- a validação do frontend preserva a ordem já escolhida;
- o worker e a API usam a mesma regra de níveis e de nomes;
- retries que reconstruam o mapa de subpastas recebem a ordem explícita;
- regressões adicionadas para a posição do fornecedor e para os exemplos de nomes.

## Verificações

- `uv run pytest tests/test_powerbi_hierarchy.py tests/test_gui_api.py tests/e2e/test_cross_platform.py -q`: aprovado;
- `uv run pytest -q --ignore=tests/e2e`: aprovado;
- `uv run python -m compileall -q process_all_pos.py src/gui/api.py`: aprovado;
- `node --check src/gui/web/app.js`: aprovado.
