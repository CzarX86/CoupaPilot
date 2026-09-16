# Diagnóstico: SSO do Edge corporativo no macOS

## 1. Evidência coletada (somente leitura)

Ambiente real inspecionado em 2026-08-24, sem matar processos do Edge e sem expor
e-mails completos ou cookies.

| Item | Valor observado |
|------|-----------------|
| Edge instalado | `/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge` |
| Versão do Edge (`--version` e `Info.plist`) | `151.0.4129.101` |
| EdgeDriver exato em cache | `~/.cache/selenium/msedgedriver/mac-arm64/151.0.4129.101/msedgedriver` |
| Processo principal do Edge | **ausente** (`pgrep -x "Microsoft Edge"` vazio) |
| `SingletonLock`/`SingletonCookie`/`SingletonSocket` na raiz | **ausentes** |
| Processos `msedgedriver` órfãos | 3 processos, `ppid=1` (ports 54053, 55531, 58747) |
| `Local State` → `profile.info_cache` | `Default` → `name=Perfil 1`, `user_name`/`gaia_name` **vazios** |
| `Default/Preferences.account_info[0].email` | contém `@unilever` |
| `Default/Preferences.account_info[0].edge_account_tenant_id` | preenchido |
| `Default/Preferences.account_info[0].edge_account_type` | `2` |
| `Default/Preferences.profile.is_relative_to_aad` | `true` |
| `Default/Preferences.custom_links` | 4 itens (potencial fonte de falso positivo) |

## 2. Causa raiz comprovada

### 2.1 Causa primária — Edge 151 recusa remote debugging no diretório de dados padrão

Ao lançar o Edge com o perfil corporativo real, o WebDriver (msedgedriver) sempre
adiciona `--remote-debugging-port=0` e espera o arquivo `DevToolsActivePort`.
Reprodução controlada com o EdgeDriver exato (`151.0.4129.101`) e o perfil real:

```
LAUNCH_FAILED elapsed=60.34s type=SessionNotCreatedException
message=Message: session not created: DevToolsActivePort file doesn't exist
```

O stderr do próprio Edge revela a causa exata:

```
DevTools remote debugging requires a non-default data directory.
Specify this using --user-data-dir.
```

Ou seja: **o Microsoft Edge 151 (stable) recusa ativar remote debugging quando o
`--user-data-dir` é o diretório de dados padrão
(`~/Library/Application Support/Microsoft Edge`)**, mesmo quando o caminho é
passado explicitamente e mesmo via symlink (o Edge canonicaliza o caminho).

Como o msedgedriver depende de `DevToolsActivePort` (que só existe com remote
debugging), a sessão WebDriver falha após ~60s com
`DevToolsActivePort file doesn't exist`. O launcher antigo traduzia esse erro de
forma incorreta para `EDGE_PROFILE_IN_USE` ("user data directory is already in
use"), que é a mensagem observada na UI.

Consequência técnica: **não é possível reutilizar o perfil corporativo real via
WebDriver/msedgedriver no macOS Edge 151**, pois isso exigiria remote debugging
no diretório padrão, que o Edge bloqueia por segurança. As únicas rotas seguras
são: (a) attach via DevTools a um Edge já aberto com remote debugging em
diretório não-padrão, ou (b) perfil dedicado do aplicativo (diretório
não-padrão, onde o WebDriver funciona) com login SSO feito uma vez.

### 2.2 Causa secundária — processos `msedgedriver` órfãos

Três processos `msedgedriver` (`ppid=1`, reparentados para o launchd) ficaram
vivos após falhas anteriores de criação de sessão. Eles seguram portas locais e
confundem tentativas posteriores. A limpeza antiga (`service.stop()`) não cobre
o caso em que o `Service` do Selenium já foi destruído (por exemplo, quando o
Selenium Manager cria o serviço internamente, sem handle acessível).

### 2.3 Causa terciária — detecção ampla de `@unilever`

`CorporateEdgeProfileDetector._contains_corporate_account` procurava
recursivamente `@unilever` em **qualquer** string de `Preferences` e
`Local State`. Isso aceita falso-positivos em `custom_links`, títulos, URLs,
favoritos e workspaces, que não provam identidade corporativa.

### 2.4 Causa quaternária — histórico de estratégia dedicada e timeout de 120s

O diagnóstico `auth_diagnostics.jsonl` mostra que tentativas anteriores
(2026-08-24 14:17–14:59) usaram `dedicated_profile_fallback` e falharam com
`HTTPConnectionPool Read timed out (read timeout=120)` ou aguardaram ~15 min
(`wait_timeout=900`).

## 3. Hipóteses validadas

| # | Hipótese | Resultado |
|---|----------|-----------|
| 1 | Detector seleciona `Default` mas o launcher não usa o diretório real | **Refutada** — o launcher já passava o diretório real; o problema é que o Edge recusa remote debugging nele |
| 2 | Detector aceita evidência falsa de `@unilever` | **Confirmada** — busca recursiva em strings não-identitárias |
| 3 | Edge aberto e app tenta iniciar o mesmo perfil sem DevTools | **Confirmada em parte** — o app tentava o perfil real e falhava; a mensagem era enganosa |
| 4 | Condição de corrida entre detecção e criação do WebDriver | **Não confirmada** — não observada; mitigada pelo lock check |
| 5 | `msedgedriver` órfão após falha | **Confirmada** — 3 processos órfãos |
| 6 | Selenium Manager escolhe versão diferente do Edge | **Já corrigida** — `EdgeDriverResolver` seleciona `151.0.4129.101` exato; não é a causa atual |
| 7 | App executando de cópia antiga em `/Applications` | **Plausível** — build antiga pode coexistir; a build nova foi gerada e a seleção exata do driver mitiga |
| 8 | Confusão entre nome técnico `Default` e identidade pessoal | **Confirmada** — o detector não distinguia nome técnico (`Default`) de nome visual (`Perfil 1`) |
| 9 | Navegação não usa a janela/aba correta | **Não confirmada** — `_authenticated_window` já varre todas as janelas |
| 10 | Captura de cookies antes do fim do redirect SSO | **Não confirmada** — `_is_authenticated` exige `_coupa_session` + URL Coupa sem marcador de login |
