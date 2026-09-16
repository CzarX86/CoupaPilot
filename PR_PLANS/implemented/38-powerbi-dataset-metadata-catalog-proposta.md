# Proposta de Mudança: Inventário dinâmico do datamodel de POs do Power BI

## Contexto

O catálogo anterior continha somente 21 campos confirmados manualmente pelo provider. Ele preservava uma origem textual, mas não garantia que todas as colunas disponíveis no datamodel fossem apresentadas ao usuário nem mantinha `table` e `column` como metadados separados no cache.

## Objetivo

Descobrir o inventário do dataset Power BI por metadata, organizar os campos por tabela de origem e permitir que as colunas descobertas sejam usadas na prévia de POs.

## Escopo

- consultar as tabelas e colunas do dataset pelo adaptador Fabric CLI já existente;
- preservar nome da tabela, nome da coluna, display name, tipo, grupo, origem e visibilidade;
- manter medidas/campos confirmados que não apareçam no endpoint de colunas;
- gerar chaves estáveis para campos descobertos;
- carregar o catálogo cacheado no provider para validar e montar o DAX da prévia;
- manter o catálogo confirmado como fallback quando metadata estiver indisponível.

## Fora do escopo

- alterar autenticação do Power BI;
- consultar dados para inferir colunas quando o metadata endpoint falhar;
- criar novos filtros além da seleção de campos já existente.

## Critérios de aceitação

1. O refresh lista as colunas retornadas pelo metadata do dataset.
2. Cada campo mantém `table`, `table_label`, `column` e `source`.
3. O cache SQLite preserva esses metadados completos.
4. Uma coluna descoberta pode ser selecionada e usada na consulta DAX.
5. A seleção de campos confirmados e as medidas existentes continuam funcionando.
6. Falha de metadata não apaga o catálogo funcional anterior.
