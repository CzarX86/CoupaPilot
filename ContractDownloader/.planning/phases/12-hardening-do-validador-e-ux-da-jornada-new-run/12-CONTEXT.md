# Phase 12 Context: hardening do validador e UX da jornada New Run

## Objetivo

Corrigir divergências entre o validador da GUI, o pipeline CLI e o importador, além de tornar as etapas 1–5 previsíveis para o usuário.

## Escopo

- Normalização única de PO/Supplier para comparação e deduplicação.
- Conflito de uma PO com múltiplos fornecedores como erro não reparável automaticamente.
- Bloqueio de mapeamento PO/Supplier para a mesma coluna.
- Detecção de placeholders, coerção numérica do Excel, headers ambíguos e linhas CSV vazias.
- Leitura consistente da primeira planilha; reparo XLSM preservando VBA.
- Reparos e importação coerentes com o resultado da validação.
- Hierarquia selecionada pelo usuário não pode ser reativada por uma revalidação.
- Estado da seleção de arquivo e feedback da validação não podem vazar para o próximo input.
- Validação do destino antes da etapa 5 e proteção contra ações concorrentes.
- Mensagens de erro sem duplicação e cobertura E2E dos estados New Run.

## Segurança

- Não remover dados automaticamente quando houver conflito semântico.
- Manter backup antes de qualquer reparo in-place.
- Nunca alterar o input original ao gerar visualizações.
