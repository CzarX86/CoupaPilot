# Proposta de Mudança: storytelling da LAB

## Objetivo

Transformar a tab `LAB` em uma experiência guiada, com uma subtab inicial `Overview` dedicada ao contexto e contexto curto próximo dos controles e resultados. A interface deve explicar a sequência de trabalho, as fontes de dados e a forma correta de interpretar GRIR, FX e Timesheets sem alterar o comportamento analítico.

## Escopo

- subtab inicial `Overview` com a introdução visual e o fluxo `Scope → PO set → GRIR → FX`;
- contexto específico para cada sub-tab;
- indicação visível das fontes utilizadas em cada análise;
- notas curtas de método e interpretação próximas dos painéis;
- explicação recolhida por card com cálculo, variáveis e fontes, aberta sob demanda;
- ordenação das tabelas por clique no header, com suporte a colunas numéricas, textuais e grupos PO→invoice;
- sinalização de que Timesheet Review continua sendo um workstream separado até a confirmação do vínculo PWO→PO→invoice.

## Fora do escopo

- alteração de consultas Power BI ou Invoice;
- alteração de cálculos, filtros, estado de seleção ou exportação;
- integração automática dos Timesheets às POs e invoices.

## Critérios de aceitação

- a primeira subtab da LAB explica a sequência de uso antes dos controles;
- cada sub-tab informa propósito, fonte e orientação de leitura;
- o conteúdo é curto, escaneável e responsivo;
- a navegação e os cálculos existentes continuam funcionando.
