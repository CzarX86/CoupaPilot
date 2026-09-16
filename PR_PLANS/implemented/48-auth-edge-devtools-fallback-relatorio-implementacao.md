# Relatório de Implementação: Autenticação Edge por DevTools e fallback dedicado

## Entrega

- Adicionado `EdgeDevToolsConnector` com validação local de `/json/version`.
- Adicionado suporte a `debugger_address` nas opções e no launcher Selenium.
- O fluxo autenticado usa DevTools quando disponível e retorna ao perfil dedicado quando não está.
- O attach não encerra a janela Edge do usuário.
- Diagnóstico da aplicação informa a estratégia selecionada.
- A mensagem e o rastreamento distinguem attach DevTools de fallback dedicado.
- O fallback dedicado resolve primeiro o EdgeDriver exato da versão instalada e só usa o Selenium Manager como fallback.
- O handshake inicial do driver é limitado a 20 segundos; falhas de `HTTPConnectionPool` não ficam presas no timeout padrão de 120 segundos.
- O diagnóstico do host usa o mesmo resolvedor de driver do launcher.
- O fluxo principal voltou a usar o detector do perfil corporativo: quando encontra `@unilever`, passa o `user-data-dir` real e o `profile-directory` selecionado ao Edge.
- Se o Edge real estiver aberto sem DevTools, o app não abre o fallback errado; retorna `EDGE_PROFILE_IN_USE` com a ação necessária.
- Falhas durante a criação da sessão encerram o `msedgedriver` recém-iniciado para não deixar processos órfãos bloqueando a próxima tentativa.

## Evidência

- Cookies do perfil real e do perfil dedicado foram inspecionados somente por metadados; valores não foram exibidos.
- O perfil real selecionado não possuía `_coupa_session`; o perfil dedicado ainda possuía o registro Coupa, embora a sessão tenha sido rejeitada pelo servidor no smoke test.
- Suíte sem E2E: 281 testes passaram.
- Smoke test real do launcher: Edge `151.0.4129.93` + EdgeDriver `151.0.4129.93`, perfil temporário, inicialização em menos de 1 segundo e encerramento limpo.
- Teste de integração unitária do fluxo: perfil corporativo detectado é usado e o fallback é bloqueado quando o Edge está aberto.

## Limite conhecido

Uma sessão Coupa vencida exige novo SSO no perfil dedicado ou um Edge real já iniciado com remote debugging. O aplicativo não copia nem descriptografa bancos de cookies do perfil pessoal.
