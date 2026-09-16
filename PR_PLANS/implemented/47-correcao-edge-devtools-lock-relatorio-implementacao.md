# Relatório de Implementação: Correção do lock do Edge WebDriver

## Entrega

- Detecção macOS ampliada para processos principais e auxiliares do Edge.
- Verificação de locks residuais antes de iniciar o WebDriver.
- Mensagem amigável para falhas `DevToolsActivePort`.
- Regressões adicionadas para helpers, lock residual e erro do launcher.

## Verificação

- Testes focados de autenticação: `30 passed`.
- Suíte sem E2E: `268 passed`.
- Nenhum processo do Edge foi encerrado automaticamente.

