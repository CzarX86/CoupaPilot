# Documento de Design: Autenticação Edge por DevTools com fallback dedicado

## Decisão

`EdgeDevToolsConnector` consulta apenas endpoints de loopback (`127.0.0.1`, `localhost` ou `::1`) e valida `/json/version` para confirmar que o processo é Microsoft Edge. Também aceita um endereço explícito por `COUPA_EDGE_DEBUGGER_ADDRESS` e o arquivo `DevToolsActivePort` do diretório padrão.

Quando o endpoint existe, `EdgeOptions.debugger_address` é usado e o Selenium não recebe `--user-data-dir` nem `--profile-directory`. Quando ele não existe, `AuthService` usa `BrowserProfileManager` e o perfil dedicado do aplicativo, que é isolado do perfil pessoal e mantém o fluxo de onboarding SSO.

O launcher resolve o EdgeDriver a partir da versão embutida no Edge instalado: primeiro procura uma cópia exata no cache local, depois uma cópia compatível e, por último, delega ao Selenium Manager. A criação da sessão aplica um timeout de socket de 20 segundos apenas durante o handshake e restaura o valor anterior ao terminar. Assim, um driver local travado produz um erro acionável em vez de aguardar o timeout padrão de dois minutos.

Sem um endpoint DevTools, o fluxo consulta o detector corporativo antes do fallback. Um perfil com evidência `@unilever` é aberto com seu diretório de dados original e seu nome de perfil real. Se esse Edge estiver em execução, a autenticação termina com `EDGE_PROFILE_IN_USE` e uma ação explícita; abrir outro perfil seria silenciosamente incorreto para SSO.

## Ciclo de vida

Uma sessão anexada usa o WebDriver apenas como cliente de controle. O encerramento chama o serviço do driver sem executar `driver.quit()` sobre o navegador do usuário. Sessões iniciadas pelo aplicativo continuam sendo encerradas normalmente.

## Segurança

Nenhum valor de cookie é lido por diagnóstico ou persistido pelo detector. O endpoint DevTools é limitado a loopback para impedir conexão acidental a um host remoto. O diretório pessoal do Edge permanece somente como fonte opcional de um endpoint já habilitado.
