# Relatório de Implementação: Seleção do perfil Edge Unilever

## Entrega

- `ProfileCandidate` agora mantém uma pontuação interna de seleção.
- O detector considera nome e metadados do perfil, além das evidências existentes em `Local State` e `Preferences`.
- O perfil corporativo mais forte é selecionado automaticamente quando a preferência é inequívoca.
- Empates permanecem protegidos por ação requerida para evitar o uso silencioso da conta errada.
- Foi adicionada regressão para o caso de um perfil `Unilever Work` entre múltiplos perfis corporativos.

## Verificação

- Testes focados de autenticação: `10 passed`.
- Suíte sem E2E: `263 passed`.
- Compilação dos módulos de autenticação: concluída.

## Limites

Os testes E2E que abrem navegador real não foram executados nesta validação. O sandbox também não permitiu inspecionar a lista de processos do macOS; nenhum processo do Edge foi encerrado automaticamente.

