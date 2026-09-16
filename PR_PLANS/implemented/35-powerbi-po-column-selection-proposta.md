# Proposta de Mudança: Seleção de colunas da prévia de POs do Power BI

## Contexto

A prévia de POs do Power BI exibia um conjunto fixo de campos. Isso limita a análise e deixa o usuário sem visibilidade sobre quais campos o semantic model de POs permite consultar.

## Objetivo

Exibir uma ação de seleção de colunas que abre uma modal com o inventário canônico do dataset de POs. A mesma seleção deve controlar a tabela da subaba `PO Source & Selection` e a tabela de apoio da etapa 1 de `New run`.

## Escopo

- catalogar no provider os campos confirmados do dataset de POs, incluindo origem, grupo, tipo e obrigatoriedade;
- expor o catálogo pela ponte Python/JavaScript;
- aceitar no provider somente chaves presentes no catálogo e manter `PO number` obrigatório;
- gerar a consulta DAX com os campos escolhidos;
- renderizar as colunas escolhidas nas duas tabelas de prévia;
- manter a seleção de POs e as análises GRIR/FX existentes.

## Fora do escopo

- descoberta automática de metadados fora dos campos já confirmados nas consultas do semantic model;
- alteração do pipeline Coupa ou do formato principal de input;
- novas fontes de dados além do dataset de POs.

## Critérios de aceitação

1. A modal lista os campos do catálogo com o nome amigável e a origem no Power BI.
2. O usuário pode selecionar todos, limpar os opcionais ou escolher um subconjunto.
3. `PO number` permanece sempre selecionado.
4. Aplicar a seleção atualiza a consulta e as tabelas no LAB e no New Run.
5. Uma chave que não pertence ao catálogo é rejeitada no backend.
6. A seleção/exclusão de POs continua alimentando GRIR e FX.
