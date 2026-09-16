# Documento de Design: Análise de FX integrada ao GRIR

## Fontes e granularidade

### Invoice semantic model

Dataset `2cbe0c63-e1da-416e-b765-a87fd33d5ebe`, tabela `Invoice`:

- `PO Number`;
- `PO Line Number`;
- `Purchase Invoice Number`;
- `Accounting Document Number`;
- `Document Date`;
- `DocumentCurrencyAmount`;
- `LocalCurrencyAmount`;
- `ReportingCurrencyEuroAmount`;
- `DocumentCurrencySK` e `LocalCurrencySK`.

### PO semantic model

Dataset `45f78e7b-bb55-42f4-a5e3-8b790e6dfbb3`, tabela `Purchase Order`:

- `PO Number`;
- `PO Line Item Number`;
- `DocumentCurrencyAmount`;
- `ReportingCurrencyEuroAmount`;
- `GoodsReceiptDocumentCurrencyAmount`;
- `GoodsReceiptReportingCurrencyEuroAmount`;
- `DocumentCurrencySK` e `LocalCurrencySK`.

O vínculo preferencial é `(PO Number, linha)`. Quando a linha não estiver disponível ou não for única, a implementação pode usar PO Number somente se a taxa-base for única; caso contrário, o resultado deve ser marcado como não resolvido.

As chaves técnicas dos dois semantic models não devem ser cruzadas. A junção é feita pelos campos de negócio PO e linha.

## Taxas efetivas

```text
invoice_fx_rate = invoice_reporting_eur / invoice_document_amount
po_fx_rate = po_reporting_eur / po_document_amount
goods_received_fx_rate = goods_received_reporting_eur / goods_received_document_amount
```

Taxas só são calculadas quando o denominador é diferente de zero. Os valores convertidos devem ser somados antes de derivar uma taxa agregada, evitando média simples de taxas.

Para separar o efeito cambial da diferença GRIR:

```text
invoice_value_at_po_rate = invoice_document_amount * po_fx_rate
fx_impact_eur = invoice_received_eur - invoice_value_at_po_rate
grir_ex_fx_eur = goods_received_eur - invoice_value_at_po_rate
grir_total_eur = goods_received_eur - invoice_received_eur
```

Quando o PO FX não puder ser resolvido, `fx_impact_eur` deve ficar nulo e a linha deve indicar `FX unavailable`, sem substituir por zero.

## Contrato do provider

Adicionar um método no `PowerBIProvider` para consultar e consolidar os detalhes FX das POs já selecionadas. O contrato deve retornar dados serializáveis, agrupados por PO, com resumo e invoices:

```text
{
  po_number,
  goods_received_eur,
  invoice_received_eur,
  grir_total_eur,
  fx_impact_eur,
  grir_ex_fx_eur,
  po_fx_rate,
  goods_received_fx_rate,
  invoices: [
    {
      invoice_number,
      accounting_document_number,
      document_date,
      document_currency,
      document_amount,
      reporting_eur,
      invoice_fx_rate,
      fx_delta_vs_po,
      fx_impact_eur,
      status
    }
  ]
}
```

O método pode reutilizar os valores GRIR já consultados, mas não deve aplicar o filtro de ano/data às invoices relacionadas.

## Interface

- cards: POs analisadas, invoices, GRIR total, impacto FX, GRIR sem FX e invoices sem taxa;
- gráficos: decomposição GRIR versus FX e impacto FX por PO/status;
- tabela hierárquica PO → invoices, com todas as POs recolhidas inicialmente;
- botões `Expand all` e `Collapse all`;
- indicação clara de `SOW FX unavailable` enquanto a extração do Coupa não estiver integrada.

## SOW como enriquecimento futuro

O extrator de documentos do Coupa fornecerá posteriormente `sow_fx_rate`, moeda, origem do documento e confiança da extração. Esse enriquecimento será associado à PO/contrato e consumido pela mesma camada de apresentação. A análise PO versus invoice não dependerá dessa informação.

## Desempenho e segurança

- manter o chunking das consultas por PO;
- não persistir tokens ou conteúdo de documentos no cache Power BI;
- manter mensagens e logs sem dados sensíveis;
- preservar a separação entre a aba Power BI e o pipeline Coupa.
