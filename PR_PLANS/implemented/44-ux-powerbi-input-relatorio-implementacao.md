# Relatório de Implementação — UX do fluxo Power BI e isolamento do input

## Entrega

- Adicionada busca de suppliers no picker Power BI, com agrupamento entre suppliers salvos e demais resultados do dataset.
- Melhorado o algoritmo de busca por tokens e ranking textual no provider Power BI.
- Adicionada persistência SQLite da seleção de colunas e exposição dos métodos na API desktop.
- Adicionados alertas de pendência, limpeza de estado ao alternar a origem e navegação antecipada para Active run.
- Mantida a descoberta completa de colunas retornada pelos metadados do dataset.

## Validação

- `node --check src/gui/web/app.js` — aprovado.
- Testes focados Power BI/GUI/DB — 105 aprovados.
- Suíte geral — 279 aprovados; 20 testes E2E não executaram no sandbox por restrição de abertura de portas, além de uma checagem dependente do perfil Edge real.
