# Proposta de Mudança: Priorizar o perfil corporativo do Edge

## Contexto

O fluxo de autenticação do Coupa usa o perfil existente do Microsoft Edge para reaproveitar a sessão SSO homologada. O detector já procura contas com `@unilever.com`, mas, quando encontra mais de um perfil corporativo, interrompe o fluxo sem considerar os metadados que identificam o perfil de trabalho.

## Escopo

- Ranqueiar os perfis que contenham uma conta `@unilever.com`.
- Priorizar sinais de perfil corporativo, como nome/metadados com Unilever ou Work e conta corporativa principal consentida.
- Usar automaticamente o melhor candidato quando houver diferença clara de prioridade.
- Manter ação requerida quando houver empate, evitando capturar a sessão de uma conta corporativa incorreta.
- Preservar a abertura com o diretório raiz do Edge e `--profile-directory` separado.

## Critérios de Aceitação

- Um perfil claramente identificado como corporativo da Unilever é selecionado sem intervenção adicional.
- Dois perfis corporativos equivalentes continuam exigindo escolha explícita.
- O detector não expõe e não persiste credenciais, cookies ou tokens.
- Os testes de autenticação existentes permanecem passando.

