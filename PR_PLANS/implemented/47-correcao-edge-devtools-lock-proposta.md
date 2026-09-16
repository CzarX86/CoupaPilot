# Proposta de Mudança: Corrigir falha de inicialização do Edge WebDriver

## Contexto

Em macOS, o Microsoft Edge pode manter processos auxiliares depois que a última janela é fechada. O detector anterior verificava apenas o processo principal e podia iniciar o WebDriver enquanto o diretório de dados ainda estava bloqueado, resultando em `DevToolsActivePort file doesn't exist`.

## Escopo

- Detectar também helpers e processos background do Edge.
- Detectar locks residuais do diretório de dados antes do lançamento.
- Substituir o stack trace bruto por uma orientação de recuperação.

## Critérios de Aceitação

- Um helper do Edge ativo impede a captura e orienta o usuário a encerrar o Edge completamente.
- Um lock residual impede o lançamento com mensagem clara.
- A exceção `DevToolsActivePort` não aparece como stack trace na interface.
- O fluxo existente de perfil `@unilever.com` e SSO permanece inalterado.

