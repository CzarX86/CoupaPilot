# Relatório de Implementação: Correção do perfil Edge SSO

## Entrega

- `CorporateEdgeProfileDetector` agora retorna o diretório raiz de dados do Edge.
- `profile_name` continua separado e é aplicado por `--profile-directory`.
- Foram adicionados testes que cobrem a detecção da raiz e os argumentos do Edge existente.

## Verificação

- Testes focados: `26 passed`.
- Suíte unitária sem `tests/e2e`: `258 passed`.
- `py_compile` dos módulos e testes de autenticação: concluído.
- `git diff --check`: concluído.

## Limites

Os testes E2E que podem abrir navegador ou porta local não foram executados nesta validação.
