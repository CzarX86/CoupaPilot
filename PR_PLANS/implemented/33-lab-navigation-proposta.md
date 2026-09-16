# Proposta de Mudança: LAB de análises

## Objetivo

Agrupar as análises experimentais em uma única tab `LAB`, mantendo as tabs originais do aplicativo visíveis e deslocando Power BI e Timesheet para sub-tabs internas.

## Nova navegação

- tabs originais: `New run`, `Active run`, `Run history`, `Learn` e `Settings`;
- tab adicional ao final: `LAB`;
- sub-tabs da LAB:
  - `PO Source & Selection`;
  - `GRIR Reconciliation`;
  - `FX Reconciliation`;
  - `Timesheet Review`.

## Comportamento

As POs selecionadas na sub-tab `PO Source & Selection` continuam alimentando as análises GRIR e FX. A Timesheet Review permanece visualmente disponível, mas sem vínculo automático com as POs até que a chave PWO→PO→invoice seja confirmada.

## Critérios de aceitação

- Power BI e Timesheet não aparecem mais como tabs de primeiro nível;
- LAB aparece como a última opção de navegação;
- as quatro sub-tabs alternam sem recarregar ou perder a seleção de POs;
- GRIR e FX preservam seus resultados e ações existentes;
- Timesheet permanece isolada e sinaliza sua limitação de integração.
