# ADR 002: Vínculo GRIR entre os semantic models de PO e invoice

## Status

Aceito para a análise GRIR inicial.

## Decisão

Relacionar os modelos por `PO Number`. Usar `PO Line Item Number` e `PO Line Number` apenas como refinamento futuro. Não usar `CoupaPurchaseOrderPKSK`, `CoupaPurchaseOrderIPAllocatedPKSK` ou `PurchaseOrderNumberSK` como chave entre modelos, pois os valores observados não são compatíveis.

## Consequências

- o valor de Goods Received vem da tabela não alocada de Purchase Order, evitando duplicação por alocações;
- o valor de Invoice Received vem da soma de `ReportingCurrencyEuroAmount` no nível de invoice ledger;
- a relação é um-para-muitos: uma PO pode ter várias invoices;
- POs sem invoice permanecem visíveis como uma categoria própria.
