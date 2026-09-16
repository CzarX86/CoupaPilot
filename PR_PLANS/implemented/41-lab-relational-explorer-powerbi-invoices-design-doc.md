# Documento de Design: invoices do Power BI no Relationship Explorer

## Fluxo de dados

1. `AppAPI.get_lab_relationships` lê a execução selecionada e os anexos do SQLite.
2. `TurboAPI` fornece um hook de enriquecimento que consulta `PowerBIProvider` para as POs da execução.
3. `PowerBIProvider.relationship_data` reutiliza `analyze_grir_fx`, que já consulta os datasets de PO e invoice, e expõe apenas os dados necessários à árvore.
4. `build_lab_relationships` mantém o agrupamento de contratos local e incorpora commitment/invoices do Power BI.

## Chaves do contrato

- `SOW:<número>` quando o nome do anexo contém uma referência explícita;
- `SOW-HASH:<sha256>` quando o anexo é identificado como SOW e não há número;
- `SOW:__unlinked__` quando não existe evidência suficiente.

O nome normalizado do arquivo não será usado como chave de contrato, porque pode gerar falsos agrupamentos.

## Dados da PO e invoice

Cada PO recebe `commitment_value_eur` do measure `Measure[Commitment Value EUR]`. Cada invoice recebe número, documento contábil, data, valor na moeda do documento, valor de reporting em EUR e quantidade de linhas do dataset Invoice. A UI mostra esses registros como filhos da PO.

Quando o Power BI está indisponível, o relatório local não é descartado; a API acrescenta um achado de aviso para deixar explícita a ausência do enriquecimento.

## Validações

Continuam válidas as regras existentes para POs sem SOW, múltiplas SOWs e POs sem invoice. A regra de invoice duplicada usa a chave retornada pelo dataset Invoice, preservando a indicação de invoices presentes sob mais de uma PO.
