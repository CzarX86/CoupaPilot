# Documento de Design: Seleção de colunas da prévia Power BI

## Decisão

O provider Python será a autoridade do inventário de campos. O frontend não terá uma lista paralela de colunas: ele chama `get_powerbi_po_columns()` e usa o retorno para montar a modal e as tabelas.

## Contrato do provider

`POWERBI_PO_COLUMNS` contém, para cada campo, `key`, `label`, `group`, `source`, `type`, `default` e, quando aplicável, `required`. Os detalhes DAX (`table`, `column`, `measure` e agregação) ficam privados no provider.

`preview_pos(..., columns=None)` mantém o comportamento atual quando `columns` não é informado. Quando recebe uma seleção, valida todas as chaves, insere `po_number` se necessário e monta `SUMMARIZECOLUMNS` somente com os campos permitidos.

Campos categóricos são dimensões do DAX; valores monetários são medidas existentes ou somas de colunas monetárias já usadas pelo fluxo GRIR/FX. O resultado continua sendo uma lista serializável de registros, com as chaves canônicas escolhidas.

## Contrato da ponte

- `get_powerbi_po_columns() -> {success, columns}`;
- `preview_powerbi_pos(year, uu_codes, management_paths, columns)`.

Campos desconhecidos retornam erro seguro e não chegam à consulta Power BI.

## Frontend

O estado `powerbiSelectedColumns` é compartilhado pelo documento. A modal `powerbi-columns-modal` edita um rascunho, preserva `PO number` e, ao aplicar, refaz a prévia se já existir uma consulta carregada.

`renderPowerBIPreviewTable()` recebe apenas o destino da tabela. Ele constrói cabeçalho, células agrupadas por PO e checkboxes de inclusão. É chamado para:

- `#powerbi-po-preview`, na subaba `PO Source & Selection`;
- `#new-run-powerbi-po-preview`, na etapa 1 de `New run`.

A etapa 1 funciona como visão compartilhada da prévia configurada no LAB e oferece acesso à mesma modal; a configuração completa da fonte continua centralizada na subaba do LAB.

## Segurança e limites

Nenhum texto recebido do usuário é interpolado diretamente como referência DAX. A seleção é validada contra o catálogo interno. Os rótulos e valores exibidos usam escaping HTML existente.

## Verificação

- testes unitários cobrem o inventário, DAX seletivo, inclusão obrigatória de PO e rejeição de chave desconhecida;
- `node --check` valida a sintaxe do JavaScript;
- testes estáticos confirmam a presença da modal e dos dois destinos compartilhados.
