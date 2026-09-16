# Documento de Design: Seleção ranqueada do perfil Edge SSO

## Solução

`CorporateEdgeProfileDetector` continua lendo somente `Local State` e `Preferences` para localizar evidências de `@unilever.com`. Cada candidato recebe uma pontuação interna baseada em:

- nome do perfil;
- metadados textuais do perfil;
- presença do domínio corporativo;
- indicadores de trabalho/corporativo;
- marca de conta corporativa principal consentida;
- caminhos de evidência relacionados a conta ou e-mail.

Os candidatos são ordenados pela pontuação. Se o primeiro tiver pontuação estritamente maior que o segundo, apenas ele é retornado como `profile_detected`; em caso de empate, o detector retorna `action_required` com os candidatos ordenados.

## Segurança e compatibilidade

A pontuação não é exibida ao usuário e nenhum valor de conta é incluído nas mensagens de diagnóstico. O contrato de `ProfileCandidate` permanece compatível com os três argumentos existentes, pois a pontuação tem valor padrão. O launcher continua recebendo a raiz de dados do Edge e o nome lógico do perfil separadamente.

## Testes

- empate entre dois perfis corporativos;
- seleção de um perfil nomeado como Unilever Work;
- detecção de um único perfil;
- bloqueio quando o Edge está aberto;
- captura pelo `AuthService` com o perfil detectado.

