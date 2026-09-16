# Documento de Design: Cache do catálogo de colunas de POs

> A implementação de descoberta dinâmica está detalhada em `PR_PLANS/Implemented/38-powerbi-dataset-metadata-catalog-design-doc.md`.

## Decisão

Usar o SQLite já adotado para o estado local da aplicação. O catálogo é pequeno, versionável como JSON e tem ciclo de vida independente dos caches de fornecedores e Management Unit.

## Persistência

A tabela `powerbi_po_columns_cache` terá uma única linha (`id = 1`) com `columns_json` e `updated_at`. O padrão de upsert é o mesmo usado pelos demais snapshots locais. A leitura de JSON inválido retorna catálogo vazio, permitindo que a camada de serviço se recupere na próxima leitura.

## Validade

O backend considera o cache vencido quando não há data, quando o catálogo está vazio ou quando `updated_at` tem mais de 30 dias. Nesse caso, `get_powerbi_po_columns()` salva novamente a lista canônica fornecida por `PowerBIProvider.po_columns()`.

`refresh_powerbi_po_columns()` sempre executa essa gravação, independentemente da idade do cache. A operação não é executada automaticamente a cada abertura da modal quando o frontend já carregou o catálogo na sessão.

## Interface

O modal mostra `Last updated` e oferece `Refresh catalog`. A atualização preserva as chaves selecionadas que ainda estiverem no inventário; quando não houver seleção anterior, usa os defaults do provider. As tabelas do LAB e do New Run continuam compartilhando o mesmo estado de seleção.

## Limites

O provider continua sendo a autoridade do inventário normalizado. O refresh consulta metadata quando disponível e mantém o catálogo confirmado como fallback. O cache controla a frequência de leitura e persistência da lista.

## Verificação

- teste de round-trip do cache no SQLite;
- teste de cache mensal, vencimento e refresh explícito na ponte;
- teste estático do botão e do endpoint usados pela interface;
- `py_compile`, `node --check` e `git diff --check`.
