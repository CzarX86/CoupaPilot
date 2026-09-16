# Phase 11 Context: visão filtrada de validação no Excel

## Objetivo

A partir da tela de validação, permitir que o usuário abra uma cópia de trabalho do input no Excel já filtrada para as linhas com problemas. O arquivo original permanece intacto e todas as linhas continuam presentes na cópia.

## Decisões

- Nunca aplicar filtro ou salvar alterações no arquivo original.
- Gerar uma cópia `.xlsx`/`.xlsm` em diretório temporário/persistente do aplicativo.
- Preservar todas as colunas e linhas originais.
- Acrescentar colunas de validação compreensíveis (`Validation Status`, `Validation Issues` e `Source Row`) na cópia.
- Ativar AutoFilter e ocultar explicitamente as linhas limpas, pois o Excel não aplica automaticamente a definição de filtro criada pelo openpyxl ao abrir o arquivo.
- Manter o número real da linha de origem para facilitar a correção no arquivo original.
- Abrir a cópia usando o aplicativo associado ao Excel; não exigir que Excel esteja instalado para a validação local.
- Para CSV, criar uma cópia XLSX para oferecer o mesmo fluxo de filtro.
- Não sobrescrever nem modificar o original.
