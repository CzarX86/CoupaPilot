# Proposta de Mudança: Análise de FX integrada ao GRIR

## Objetivo

Estender a seção GRIR da aba Power BI para mostrar a variação cambial entre invoices, PO e, quando estiver disponível, a taxa extraída da SOW.

## Contexto

O dataset de invoices não expõe uma coluna explícita de FX rate, mas possui os valores na moeda documental e em EUR. O dataset de POs possui os mesmos valores-base e também os valores de Goods Received. A taxa efetiva pode ser calculada por linha, desde que o valor documental seja diferente de zero.

A comparação deve ser apresentada primeiro por PO, com a PO recolhida por padrão. O usuário poderá expandir uma PO para visualizar as invoices relacionadas.

## Escopo

- consultar invoices relacionadas às POs já selecionadas na análise GRIR;
- calcular a taxa efetiva da invoice a partir dos valores documentais e EUR;
- calcular a taxa efetiva da PO e, quando disponível, do Goods Received;
- calcular a diferença cambial e separar o impacto de FX da diferença GRIR;
- exibir cards e gráficos agregados;
- exibir uma lista hierárquica PO → invoices, recolhida inicialmente;
- manter o campo de FX da SOW como enriquecimento opcional para uma etapa futura de extração dos documentos baixados do Coupa;
- não alterar o fluxo de download ou processamento Coupa existente.

## Fora de escopo nesta etapa

- extração do FX diretamente de documentos SOW;
- inferência de uma taxa contratual quando a SOW não estiver disponível;
- substituição do valor de Invoice Received utilizado pelo GRIR atual;
- exportação detalhada de invoices.

## Critérios de aceitação

- a visão inicial exibe uma linha agregada por PO e permanece recolhida;
- expandir uma PO exibe suas invoices sem misturar valores entre POs;
- invoices com valor documental zero não geram taxa artificial;
- o impacto de FX é distinguido da variação GRIR total;
- POs sem invoices e invoices sem taxa calculável aparecem com status explícito;
- a ausência do FX da SOW não bloqueia a análise PO versus invoice;
- as seleções/exclusões de POs existentes continuam respeitadas.
