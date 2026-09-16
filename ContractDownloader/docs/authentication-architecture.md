# Arquitetura de autenticação — Contract Downloader 1.0.0

## Objetivo

O Contract Downloader usa o Microsoft Edge corporativo existente apenas para capturar a sessão SSO quando necessário. Depois do preflight, o motor oficial é HTTP/2 (`httpx.AsyncClient`) e não inicia Selenium, Playwright ou um browser por worker.

## Fluxo SSO

1. O app valida primeiro a sessão no armazenamento seguro nativo. Uma sessão válida não abre o Edge.
2. Quando a sessão está ausente ou expirada, a interface informa claramente: **feche todas as janelas do Microsoft Edge**.
3. O app somente detecta se `msedge.exe`/Microsoft Edge ainda está ativo. Ele nunca executa `taskkill`, `pkill` ou encerramento forçado.
4. Após o Edge ser fechado, `CorporateEdgeProfileDetector` lê `Local State` e `Preferences` e procura uma referência a `@unilever.com`.
   - Um único candidato segue automaticamente.
   - Nenhum ou vários candidatos geram `ACTION_REQUIRED` para o usuário corrigir ou escolher o perfil.
5. O WebDriver abre o perfil existente, navega ao Coupa e captura os cookies. Ao final, `driver.quit()` fecha somente o browser criado pelo app.
6. O perfil pessoal não é copiado, apagado, alterado ou registrado como cache do aplicativo.

O Edge só é aberto após a ação explícita de autenticação. Se o usuário fechá-lo durante o preflight, pode continuar usando o Edge normalmente depois que a captura terminar.

## Armazenamento

`SecureSessionStore` grava a sessão em:

- Windows: Windows Credential Manager via `CredWriteW`, `CredReadW` e `CredDeleteW` usando `ctypes`.
- macOS: Keychain nativo via o comando `security`.

O cache legado `cookies.json`/`auth_cache.db` é lido somente para migração. Após a gravação nativa confirmada, os arquivos plaintext são removidos. Se o armazenamento nativo estiver indisponível, o app não cria novo plaintext: mantém a sessão em memória e mostra um aviso.

Cookies, tokens e credenciais não aparecem em logs, diagnósticos ou relatórios.

## Motor oficial e estados HIL

Uma única sessão de cookies é entregue ao `CoupaCrawler`, com concorrência padrão de 11 workers, rate limiter, cooldown e retry de rede. O parser mantém as duas passagens (`data-url` e `href`).

Erros de autenticação pausam o lote e preservam os POs pendentes como `PENDING`. Timeout, 429 e 5xx usam retry controlado. Erros de parser, PO ou anexo registram diagnóstico e continuam o lote.

Os estados de interação são `SESSION_VALID`, `EDGE_MUST_BE_CLOSED`, `PROFILE_DETECTED`, `CAPTURING_SESSION`, `SESSION_READY`, `AUTH_REQUIRED`, `ACTION_REQUIRED` e `RUN_PAUSED`.

Quando uma sessão expira no meio do lote, o SQLite recebe `RUN_PAUSED`, novas requisições são interrompidas e os POs concluídos não são reprocessados. O usuário fecha o Edge quando solicitado, executa a captura explícita e usa **Resume**.

Não existe fallback automático para Selenium/Playwright nem para o projeto legado da raiz. A versão antiga permanece disponível somente como backup operacional separado.

## Componentes

- `src/auth/cookie_store.py`: `SecureSessionStore`, Credential Manager, Keychain e migração legada.
- `src/auth/browser.py`: detecção segura do Edge corporativo e captura controlada pelo WebDriver.
- `src/auth/service.py`: política única usada pela GUI e CLI.
- `src/auth/session_validator.py`: validação HTTP rápida contra o Coupa.
- `src/engine/crawler.py`: crawler HTTP/2 oficial sem browser.
- `process_all_pos.py`: preflight, processamento concorrente e pausa/retomada.
- `src/engine/authenticator.py`: fachada de compatibilidade para integrações antigas; não é o caminho oficial.

OAuth administrativo não faz parte do produto oficial porque depende de configuração do tenant fora do escopo do usuário desenvolvedor.
