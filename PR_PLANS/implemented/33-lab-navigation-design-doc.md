# Documento de Design: LAB de análises

## Implementação

O conteúdo já existente de Power BI e Timesheet continua no HTML com seus IDs e contratos atuais. Durante a inicialização da interface, os blocos são movidos para quatro painéis da LAB:

- seleção Power BI e preview de PO → `source`;
- card GRIR → `grir`;
- card FX → `fx`;
- conteúdo Timesheet → `timesheet`.

Essa composição evita duplicar markup e mantém os listeners, estado de seleção, exclusões e resultados em memória.

## Estado compartilhado

`powerbiPreviewRows`, `powerbiExcludedPOs`, `powerbiGrirRows` e `powerbiGrirFxRows` permanecem no escopo da aplicação. Trocar de sub-tab apenas alterna visibilidade; não dispara nova consulta nem limpa os dados.

Ao entrar na LAB, a sub-tab anteriormente aberta é preservada. A conexão Power BI é carregada quando a sub-tab de fonte é acessada; o cache Timesheet é carregado ao acessar sua sub-tab.

## Decisão de nomenclatura

Foi adotada linguagem orientada ao trabalho do usuário, mantendo o termo Power BI apenas como detalhe técnico interno. `Reconciliation` descreve melhor a finalidade das análises GRIR/FX do que `Variances` isoladamente.
