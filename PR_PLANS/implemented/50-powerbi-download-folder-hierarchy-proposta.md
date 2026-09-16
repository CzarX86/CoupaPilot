# Proposta de Mudança: Hierarquia de pastas do download Power BI

## Contexto

O fluxo de `New run` alimentado pelo Power BI já organiza os downloads por fornecedor, mas os campos CRG e Ano não estavam disponíveis como níveis opcionais da hierarquia. Além disso, códigos derivados do fornecedor podiam ser tratados como níveis adicionais, criando pastas repetidas como `EY/EY/EY`.

## Objetivo

Permitir que o usuário inclua opcionalmente CRG e Ano na hierarquia de pastas do download Coupa, mantendo o fornecedor como primeiro nível único.

## Escopo

- consultar CRG e Ano no snapshot usado pelo download;
- exibir ambos como níveis opcionais na etapa de confirmação das pastas;
- respeitar a ordem e a seleção feitas pelo usuário;
- impedir que Supplier GU/S code criem níveis de pasta do fluxo Power BI;
- remover níveis duplicados quando valores de pasta forem iguais ao fornecedor ou a outro nível.

## Fora do escopo

- alterar o modelo semântico do Power BI;
- mudar o nome das pastas já geradas;
- alterar a hierarquia de arquivos de entradas Excel genéricas.

## Critérios de aceitação

1. CRG e Ano aparecem no catálogo e são consultados no preview/snapshot Power BI.
2. CRG e Ano começam desativados e podem ser ativados individualmente na hierarquia.
3. Com ambos ativados, a estrutura fica `Fornecedor/CRG/Ano/PO`.
4. Supplier GU/S code não gera subpastas adicionais no fluxo Power BI.
5. Valores repetidos não criam pastas duplicadas, como `EY/EY/EY`.
