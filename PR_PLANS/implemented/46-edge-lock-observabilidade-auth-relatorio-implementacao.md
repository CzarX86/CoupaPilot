# Relatório de Implementação: Robustez do login Edge e diagnóstico

## Entrega

- Detecção do processo principal separada da contagem informativa de helpers.
- Validação do PID proprietário do `SingletonLock` e do processo correspondente.
- Locks órfãos são ignorados sem serem removidos.
- Erros comuns do WebDriver possuem códigos `EDGE_PROFILE_IN_USE`, `EDGE_DRIVER_VERSION_MISMATCH` e `BROWSER_START_FAILED`.
- Eventos de autenticação são gravados em JSONL com estado anterior, estado atual e duração.
- Health check do Keychain/Credential Manager diferencia sessão ausente de backend inacessível.
- Diagnóstico do host mostra perfil dinâmico, processos/lock, armazenamento seguro e último evento.

## Verificação

- Testes focados: `83 passed`.
- Suíte sem E2E: `273 passed`.
- Compilação dos módulos alterados: concluída.
- `git diff --check`: concluído.
- Build macOS ARM64: `1.0.5`.
- Versão do bundle e `.version` empacotado: `1.0.5`.
- Verificação de assinatura ad-hoc com `codesign --verify --deep --strict`: concluída.

## Limites

Os testes E2E que abrem um Edge real não foram executados no sandbox. A enumeração de processos também foi bloqueada no ambiente de desenvolvimento, mas a indisponibilidade agora aparece explicitamente no diagnóstico em vez de ser tratada como sucesso silencioso.
