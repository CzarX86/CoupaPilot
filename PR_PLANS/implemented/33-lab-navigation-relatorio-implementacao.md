# Relatório de Implementação: LAB de análises

## Resultado

Power BI e Timesheet foram removidos da navegação de primeiro nível e agrupados na tab final `LAB`.

## Sub-tabs entregues

- `PO Source & Selection`;
- `GRIR Reconciliation`;
- `FX Reconciliation`;
- `Timesheet Review`.

## Verificação

- JavaScript validado com `node --check`;
- Python compilado com `py_compile`;
- testes de provider, Power BI e cache: 22 aprovados;
- `git diff --check`: aprovado;
- estado de seleção de PO mantido em memória durante a troca de sub-tabs.
- Playwright UI: 2 testes de jornada aprovados;
- bundle macOS em `dist/ContractDownloader.app`: assinado e verificado.

A Timesheet Review continua deliberadamente sem vínculo com GRIR/FX até a definição da chave PWO→PO→invoice.

O app no caminho de projeto não foi substituído porque estava em execução durante o build; o artefato atualizado está em `dist/ContractDownloader.app`.
