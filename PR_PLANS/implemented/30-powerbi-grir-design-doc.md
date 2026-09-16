# Documento de Design: Análise GRIR na aba Power BI

## Fontes e granularidade

- POs: dataset `45f78e7b-bb55-42f4-a5e3-8b790e6dfbb3`, tabela `Purchase Order`, soma de `GoodsReceiptReportingCurrencyEuroAmount` por `PO Number`.
- Invoices: dataset `2cbe0c63-e1da-416e-b765-a87fd33d5ebe`, tabela `Invoice`, soma de `ReportingCurrencyEuroAmount` por `PO Number`.
- O vínculo primário é `PO Number`. `PO Line Item Number` e `PO Line Number` são referências secundárias; as chaves técnicas dos modelos não são compartilhadas.

## Consulta

O aplicativo consulta primeiro as POs com ano, supplier e Management Unit. Depois envia os números de PO selecionados à análise GRIR. As consultas GRIR usam apenas `TREATAS` por PO e não incluem `Time[Year]` nem datas. Listas grandes são divididas em blocos de 250 POs.

## Métricas

- Goods Received EUR;
- Invoice Received EUR;
- GRIR variance EUR = Goods Received EUR - Invoice Received EUR;
- quantidade de POs, invoices e linhas contábeis;
- status `No invoice`, `GR > Invoice`, `Invoice > GR` ou `Balanced`, com tolerância de EUR 0,01.

## Interface

A seção GRIR aparece abaixo da prévia de POs e contém cards, barras comparativas de valores, distribuição por status e tabela ordenada pela divergência absoluta. Desmarcar uma PO atualiza os resultados locais sem nova consulta.
