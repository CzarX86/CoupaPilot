# Documento de Design: Correção da autenticação SSO do Edge

## 1. Comparação — CLI legado × arquitetura atual

### 1.1 CLI legado (commit `3bcb938`, `src/engine/authenticator.py`)

- Uma única função assíncrona `get_coupa_cookies()`.
- `webdriver.Edge(options=options)` direto, **sem perfil**, **sem resolver
  EdgeDriver** (dependia do Selenium Manager).
- Navegava ao Coupa e aguardava login manual com thread de ENTER.
- `driver.get_cookies()` → dicionário → `cookies.json` + `auth_cache.db`.
- Validação via `httpx` checando URL final.
- Heurística legada de seleção de perfil (`_edge_profile_directory`) já
  priorizava sinais corporativos: `hosted_domain`, `is_consented_primary_account`,
  `profile.is_relative_to_aad`, `edge_account_tenant_id`, `edge_account_type` e
  tokens de nome (`work`, `business`, `corporate`...).

**Pontos fortes do legado**: a heurística de perfil era mais próxima do requisito
corporativo (sinais AAD/tenant), não fazia busca recursiva por `@unilever`.

**Pontos fracos do legado**: cache em texto puro, sem detecção de perfil
estruturada, sem distinção DevTools/lock, sem timeout limitado, sem limpeza de
`msedgedriver`.

### 1.2 Arquitetura atual (antes desta correção)

- `AuthService` (política única GUI+CLI) → `BrowserLogin` (captura visível) →
  `SeleniumBrowserLauncher` (WebDriver) + `EdgeDriverResolver` (driver exato).
- `SecureSessionStore` (Keychain/Credential Manager) + `SessionValidator`.
- `CorporateEdgeProfileDetector` com busca recursiva de `@unilever`.
- `EdgeDevToolsConnector` (loopback) e `BrowserProfileManager` (perfil dedicado).
- Fluxo: cache → DevTools → detectar perfil → abrir perfil real/fechado → capturar.

**Deficiências atuais**:
1. Detecção por substring recursiva (falso-positivos).
2. Sem distinção entre nome técnico (`Default`) e nome visual (`Perfil 1`).
3. Mapeamento de erro incorreto (`DevToolsActivePort` → "profile in use").
4. Sem limite real na criação de sessão (msedgedriver espera 60s).
5. `msedgedriver` órfão em falhas.

## 2. Decisões desta correção

### 2.1 Seleção determinística por campos de identidade

`CorporateEdgeProfileDetector` passa a extrair **somente** campos de identidade:

- `Preferences.account_info[].email` (prova primária, +100);
- `Local State.profile.info_cache[<perfil>].user_name` / `gaia_name` (+50);
- `Local State.profile.info_cache[<perfil>].hosted_domain` (+20);
- sinais de ranqueamento (nunca prova sozinhos): `edge_account_tenant_id` (+40),
  `edge_account_type` (+30), `profile.is_relative_to_aad` (+25),
  `is_consented_primary_account` (+10), nome visual com termo corporativo (+5).

`custom_links`, URLs, títulos, favoritos e workspaces são **ignorados**. O
candidato retorna `user_data_dir`, `profile_directory`, `display_name`
(nome visual), evidências seguras (apenas caminhos de campos), `score` e
`reason`. Nunca registra o e-mail completo.

### 2.2 Limite de 20s e erro preciso no launcher

`SeleniumBrowserLauncher` executa `webdriver.Edge` em thread daemon e aguarda
`DRIVER_STARTUP_TIMEOUT=20s`. Em estouro:

- mata a árvore do serviço (filhos do `msedgedriver` e o próprio driver), nunca o
  Edge do usuário;
- se o alvo é o diretório de dados padrão do Edge, emite
  `EDGE_REMOTE_DEBUGGING_REFUSED` com instrução clara (Edge 151 bloqueia remote
  debugging no diretório padrão);
- caso contrário emite `EDGE_DRIVER_START_TIMEOUT`.

O mapeamento distingue agora `devtoolsactiveport`, `user data directory is
already in use`, `chrome not reachable`, `read timed out` e
`only supports microsoft edge version`.

### 2.3 Limpeza de `msedgedriver` órfão

Nova função `reap_orphaned_msedgedrivers()` finaliza **apenas** drivers
reparentados (`ppid=1`), usando `pgrep -x msedgedriver` + `ps -o ppid=`. É
invocada no início de `AuthService.authenticate` e registra os PIDs no
diagnóstico. Nunca toca no Edge do usuário nem em drivers de outros processos.

### 2.4 Cancelamento e fluxo de status

`BrowserLogin` ganha `cancel()` (evento checado no loop de espera SSO) e o
timeout padrão de espera cai de 900s para 300s (configurável). `AuthService`
emite as etapas: `Preparing`, `Detecting corporate Edge profile`, `Checking Edge
process and profile lock`, `Connecting through DevTools` / `Opening detected
corporate profile`, `Waiting for SSO`, `Validating Coupa session`, `Saving
secure session`.

### 2.5 Diagnóstico

`auth_diagnostics.jsonl` continua só com metadados. Erros de driver passam a
registrar `edge_driver_diagnostics` (versão do Edge, versão do driver, caminho
do driver, porta, tempo) e `edge_driver_reaped` (PIDs). Nenhum cookie, token,
senha, e-mail completo, URL com query sensível ou conteúdo do Keychain é
gravado.

## 3. Segurança

- Não copia o perfil, não descriptografa `Cookies`, não lê valor do Keychain.
- Remote debugging só em loopback (`127.0.0.1`, `localhost`, `::1`).
- `driver.quit()` nunca é chamado sobre um Edge anexado via DevTools.
- O reaper só finaliza `msedgedriver` órfão (`ppid=1`), nunca o navegador.

## 4. Limite conhecido (restrição do Edge 151)

Como o Edge 151 recusa remote debugging no diretório padrão, a reutilização
automática do perfil corporativo real via WebDriver **não é tecnicamente
possível**. Portanto, com o Edge fechado, o app usa automaticamente o **perfil
dedicado** com um único login SSO (a sessão persiste no Keychain + cookies do
perfil dedicado). A detecção do perfil corporativo permanece para orientar o
caso "Edge aberto" e o diagnóstico, mas não é mais o alvo de abertura via
WebDriver. O `EDGE_REMOTE_DEBUGGING_REFUSED` permanece como rede de segurança
se uma abertura de diretório padrão for tentada fora desse fluxo.
