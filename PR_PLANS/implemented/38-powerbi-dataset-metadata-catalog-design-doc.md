# Documento de Design: Inventário dinâmico do datamodel de POs

## Decisão

Reutilizar o adaptador `fab api -A powerbi` existente. O provider consulta `datasets/{datasetId}/tables` e, quando necessário, `datasets/{datasetId}/tables/{table}/columns`. O catálogo é normalizado antes de ser persistido no snapshot SQLite já usado pela modal.

## Modelo do catálogo

Cada item contém, quando disponível, `key`, `label`, `group`, `semantic_group`, `source`, `table`, `table_label`, `column`, `measure`, `measure_table`, `type`, `data_type`, `default`, `required` e `hidden`.

Campos reais usam uma chave estável derivada de tabela, coluna e hash curto. Campos confirmados mantêm suas chaves canônicas para não invalidar seleções ou exportações existentes.

## Consulta

Colunas descobertas são adicionadas como dimensões no `SUMMARIZECOLUMNS`. Medidas descobertas ou confirmadas são adicionadas como expressões com a tabela de medida correta. A leitura da resposta prioriza a referência completa `Tabela[Campo]`, evitando colisões quando duas tabelas possuem colunas homônimas.

## Compatibilidade e falhas

Ao carregar o cache, o provider reconstitui detalhes privados ausentes em snapshots antigos usando o catálogo confirmado. Se a descoberta falhar, o provider mantém os campos confirmados e identifica internamente a origem como fallback; o snapshot anterior não é apagado por uma falha de metadata.

## Interface

O modal continua compartilhado entre LAB e New Run. A linha de cada campo exibe tabela de origem, referência completa, tipo de dado e marcação de campo oculto, sem remover a possibilidade de seleção.

## Decisão registrada

Ver [ADR 005](../../docs/adr/005-powerbi-dataset-metadata-catalog.md).
