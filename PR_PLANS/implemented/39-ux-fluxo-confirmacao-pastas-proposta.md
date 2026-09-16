# Proposta de Mudança: consolidar confirmação da árvore de pastas

## Contexto

A jornada de `New run` exibia a árvore/previsão antes da escolha do destino, abria um `confirm()` para validar a estrutura e levava o usuário a uma etapa 4 separada. A tela 3 já contém as informações necessárias para a decisão.

## Objetivo

Simplificar o fluxo para três etapas: input, validação e configuração final. Na etapa 3, o usuário escolhe primeiro a localização, visualiza a árvore final e aprova essa estrutura por checkbox antes de iniciar o download.

## Critérios de aceitação

- A etapa 4 não aparece na navegação nem no conteúdo da jornada.
- A localização de salvamento aparece antes da árvore final.
- A árvore final permanece visível na tela e possui checkbox de aprovação.
- O download só pode ser iniciado com o checkbox marcado e um destino preenchido.
- Alterar o destino ou a hierarquia remove a aprovação anterior.
- Não há `confirm()` para a árvore de pastas.

## Escopo

HTML, JavaScript, CSS e teste E2E da jornada de `ContractDownloader`.

O design doc foi omitido por se tratar de uma alteração localizada de fluxo e apresentação, sem decisão arquitetural nova.
