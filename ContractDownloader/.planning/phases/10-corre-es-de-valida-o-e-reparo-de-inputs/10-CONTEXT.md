# Phase 10 Context: validação e reparo de inputs

## Problema

A etapa 2 agrupa problemas, mas o usuário não consegue identificar facilmente todos os POs/linhas afetados. Os botões `Fix` também precisam apresentar falhas de reparo de forma visível e revalidar o mesmo arquivo imediatamente.

## Objetivo

Tornar a correção de inputs acionável e auditável: mostrar os valores afetados, executar os reparos seguros no arquivo selecionado e informar o resultado sem exigir que o usuário depure o log.

## Regras

- Reparos automáticos continuam limitados a linhas totalmente vazias, POs duplicadas e caracteres inválidos.
- Antes de editar, criar backup do input.
- Inputs abertos no Excel continuam bloqueados.
- Mapeamentos persistidos de colunas também devem ser respeitados pelos reparos.
- O input original fora de uma execução não deve ser apagado.
- Após cada reparo, revalidar o arquivo e manter a lista de problemas atualizada.
