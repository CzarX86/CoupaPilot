# Proposta de Mudança: corrigir ordem e nomes da hierarquia de pastas

## Contexto

O usuário consegue reordenar os níveis de pasta na etapa final da interface, mas o caminho efetivamente persistido pelo worker ainda tratava `Supplier` como o primeiro nível. Além disso, valores que já continham barras invertidas ou sequências de underscores podiam resultar em nomes como `Integrated_Advertising___Creative_-_Agency_Fees`.

## Objetivo

Fazer com que a ordem explícita aprovada na interface seja a mesma ordem usada na criação das pastas e normalizar sequências consecutivas de `_` para um único separador.

## Escopo

- preservar `Supplier` na posição escolhida pelo usuário quando uma ordem explícita for enviada;
- remover a reposição automática de `Supplier` no topo durante a validação da interface;
- aplicar a ordem no worker, no mapa de retry e no caminho de importação;
- converter barras e barras invertidas em `_` e colapsar sequências consecutivas de `_`;
- adicionar regressões para a ordem intermediária e para os nomes informados.

## Critérios de aceitação

1. Com a ordem `Year / Supplier / CRG`, o subdiretório persistido é `Year/Supplier/CRG`.
2. Uma nova validação não move `Supplier` de volta para o topo.
3. `Integrated\\_Advertising\\_\\_\\_Creative\\_-\\_Agency\\_Fees` é normalizado sem barras invertidas e sem underscores consecutivos.
4. `TV___Cinema_including_Buyouts_excluding_celebrity_costs` é normalizado para um único underscore entre os termos.
5. A suíte não-E2E permanece verde.
