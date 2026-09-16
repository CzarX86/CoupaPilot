# ADR 003: Taxa efetiva para análise FX do GRIR

## Status

Aceito para implementação inicial.

## Contexto

Os semantic models de invoice e PO não expõem uma coluna explícita de FX rate. Ambos expõem valores na moeda documental e valores convertidos para EUR. O valor da SOW ainda será extraído futuramente de documentos baixados do Coupa.

## Decisão

Usar uma taxa efetiva derivada por linha:

```text
ReportingCurrencyEuroAmount / DocumentCurrencyAmount
```

A comparação inicial será PO versus invoice. O FX da SOW será um enriquecimento opcional posterior, sem impedir a análise quando estiver ausente. A interface será hierárquica, com PO recolhida e invoices no nível expandido.

## Consequências

- a taxa pode refletir arredondamentos ou ajustes contábeis e deve ser rotulada como efetiva;
- denominadores zero ou vínculos ambíguos serão exibidos como indisponíveis;
- a futura extração da SOW poderá ser adicionada sem alterar o contrato principal da tela;
- a separação entre GRIR total, impacto FX e GRIR sem FX ficará auditável por PO.
