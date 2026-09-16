# Proposta de Mudança: Análise GRIR na aba Power BI

## Objetivo

Adicionar uma análise de Goods Received versus Invoice Received na parte inferior da aba Power BI, usando as POs resultantes dos filtros atuais.

## Contexto

O semantic model `Committed Spend BG Dataset` possui os valores de Goods Received por PO. O semantic model `Invoiced Spend SelfService` possui os lançamentos de invoices. A comparação precisa considerar todas as invoices relacionadas às POs selecionadas, sem aplicar o filtro de ano na segunda consulta.

## Escopo

- consultar Goods Received e Invoice Received por `PO Number`;
- calcular a variação GRIR e classificar cada PO;
- exibir cards, gráficos resumidos e tabela de divergências;
- respeitar as POs excluídas pelo usuário na prévia;
- manter o pipeline Coupa e a geração do input CSV existentes.

## Critérios de aceitação

- uma PO pode ter várias invoices sem multiplicar o valor de Goods Received;
- invoices são consultadas sem filtro de data;
- valores são comparados em EUR;
- POs sem invoice aparecem separadamente;
- a análise continua isolada na aba Power BI.
