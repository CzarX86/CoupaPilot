# Documento de Design: storytelling da LAB

## Composição visual

A experiência usa cartões editoriais compactos, sem criar uma nova camada de dados. A navegação da LAB começa em uma subtab `Overview`, evitando repetir a introdução em cada análise:

1. `lab-story-intro` dentro de `lab-panel-overview` apresenta o objetivo e o fluxo da LAB;
2. cada `lab-panel` recebe um `lab-panel-intro` com índice, pergunta analítica, descrição e badge de fonte;
3. GRIR e FX recebem um `lab-method-grid` para mostrar a decomposição da análise;
4. `lab-reading-note` registra como interpretar o resultado e limitações conhecidas.
5. `lab-card-method` usa o elemento nativo `<details>` para divulgação progressiva de cálculo, variáveis e fontes.

Os blocos são declarados nos painéis da LAB antes do conteúdo legado de Power BI e Timesheet ser movido pelo JavaScript. Assim, o markup e os listeners existentes continuam sendo reutilizados. A subtab `Overview` não dispara consulta; a consulta Power BI só é carregada ao entrar em `PO Source & Selection`.

## Diretrizes de conteúdo

- usar perguntas analíticas curtas em vez de textos longos;
- manter os filtros junto do espaço de evidência;
- nomear as fontes como `PO semantic model`, `Invoice dataset` e `Local workbook`;
- declarar a limitação de Timesheet sem simular reconciliação inexistente;
- manter explicações detalhadas recolhidas por padrão, para preservar a leitura do dashboard;
- manter a interface em inglês, conforme a convenção do aplicativo.

## Responsividade

Em telas estreitas, o cabeçalho editorial vira uma coluna, o fluxo passa a ser vertical, os métodos empilham e os badges permanecem abaixo do texto principal.

## Decisões preservadas

Não foram adicionados endpoints, dependências ou estados novos. A mudança é somente de apresentação e orientação do usuário.

## Ordenação das tabelas

Os headers com conteúdo recebem `role="button"`, `tabindex` e `aria-sort`. O comparador infere números, datas e texto, alterna ascendente/descendente e usa setas visuais. Colunas de ação não são ordenáveis. Na tabela FX, o `<tbody>` é tratado como grupos: cada PO permanece junto das suas invoices durante a ordenação.
