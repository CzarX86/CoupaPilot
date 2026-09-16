# Proposta de Mudança: Sessão de autenticação segura e persistente (Coupa + Power BI)

## Contexto

O login do Coupa hoje depende de um fluxo customizado em `src/auth/` (~1.300 linhas): Selenium abre um perfil Edge/Chrome app-owned, captura cookies e valida a sessão com um GET heurístico em `/order_headers`, inspecionando a URL final em busca de marcadores (`/login`, `/oauth`, `/sso`, `pingfederate`...). Os cookies são persistidos em texto puro (`cookies.json` + SQLite em `~/.contract_downloader`). Não há previsão de expiração: o `expiry` do cookie `_coupa_session` é descartado na captura (`_cookies()` mantém só nome/valor), então toda sessão depende de revalidação online e qualquer expiração do SSO corporativo (PingFederate) obriga re-login via Selenium.

O Power BI (`src/powerbi_provider.py`) delega ao Fabric CLI oficial e já é mais robusto, mas o re-login depende de `fab auth login` quando o token expira.

## Pesquisa realizada

| Fonte | Achado | Impacto |
|---|---|---|
| Coupa Integration Technical Documentation (compass.coupa.com) | A Coupa Core API suporta **OAuth 2.0 `client_credentials`** (`POST /oauth2/token` com `client_id`, `client_secret`, `scope` → `access_token` + `expires_in`). **API keys estão deprecadas**; a Coupa orienta migrar para OAuth clients. | Caminho "profissional" definitivo: zero navegador, zero cookies, token renovável a cada execução. **Depende de admin do tenant** criar o OAuth client e dos scopes cobrirem as operações de download (fora do nosso controle). |
| MSAL Python (msal.readthedocs.io) | `SerializableTokenCache` + `acquire_token_silent` (refresh token) + `initiate_device_flow` permitem sessões de ~90 dias com renovação silenciosa e login sem navegador. | Melhoraria o Power BI, mas esbarra no mesmo bloqueio do ADR 001: **sem App Registration**, não há `client_id` público. |
| keyring (jaraco/keyring) | API simples (`set_password`/`get_password`), backends nativos: macOS Keychain, Windows Credential Manager, Secret Service no Linux; erros via `KeyringError`. | Armazenar o cookie jar no cofre do SO em vez de texto puro. Dependência pequena, estável, compatível com PyInstaller. |
| Selenium (`driver.get_cookies()`) | Cada cookie expõe `expiry` (Unix time) — hoje descartado. | Permite **predizer expiração offline** e evitar validação contra Coupa indisponível. |
| Código atual (`session_validator.py`) | Decisão `EXPIRED` depende de substring na URL final; `429` não é tratado; não há keep-alive nem refresh oportunista. | Falso-positivos de `EXPIRED` descartam sessões válidas → re-login desnecessário. |

## Objetivo

Reduzir a frequência de logins (idealmente eliminá-los por semanas) e elevar a segurança do armazenamento, em fases de risco crescente, sem mudar o fluxo de download.

## Escopo

### Fase 1 — Armazenamento seguro + previsão de expiração (implementável agora)

1. **`SecureCredentialStore`**: persistir o cookie jar no keyring do SO (Keychain/Credential Manager) via `keyring`, com fallback para o formato atual e migração transparente do cache existente.
2. **Persistir `expires_at`** do `_coupa_session` (capturado do `expiry` do Selenium) junto ao cache → o app conhece a expiração offline e não valida/abre navegador antes da hora.
3. **Endurecer `SessionValidator`**: decidir `EXPIRED` por status code + domínio + presença de cookie, não por substring na URL; tratar `429` como `UNAVAILABLE` (nunca descartar sessão); retry com backoff.
4. **Refresh oportunista**: ao final de cada execução bem-sucedida, revalidar e re-persistir a sessão (janela deslizante).
5. **Keep-alive em background** na GUI: revalidação periódica leve enquanto o app está aberto.

### Fase 2 — Login "zero-click" (média)

6. Tentar capturar cookies do perfil persistente em modo headless **antes** de abrir a janela visível; se o SSO do perfil ainda for válido, nenhuma interação do usuário.

### Fase 3 — Autenticação por API oficial (depende da organização)

7. Avaliar OAuth 2.0 `client_credentials` da Coupa Core API (substituiria Selenium+cookies por bearer token com renovação automática). Exige: admin do tenant criar OAuth client, confirmação de scopes (`core.*`) cobrindo leitura de POs e download de anexos, e ADR dedicado.
8. Reavaliar MSAL direto para o Power BI se uma App Registration for aprovada (eliminaria a dependência do helper `fab`).

## Fora do escopo

- Trocar Selenium por Playwright (engine atual funciona; a troca não resolve o problema de persistência).
- Alterar o fluxo de download, o pipeline ou os relatórios.
- Criar OAuth clients ou App Registrations no tenant (ação administrativa da organização).

## Critérios de aceitação

1. Nenhum cookie de sessão é persistido em texto puro quando o keyring está disponível; o cache legado é migrado sem perda.
2. O app conhece a expiração do `_coupa_session` e não abre navegador antes do vencimento.
3. Nenhuma sessão válida é descartada por falso-positivo do validador (substring na URL).
4. `429`/indisponibilidade do Coupa não forçam re-login.
5. Com SSO ainda válido no perfil, a sessão é recuperada sem janela visível (Fase 2).
6. Execuções consecutivas dentro da janela da sessão não exigem login (sem retries constantes).
7. Sem regressão na suíte existente (`uv run pytest`); fallback funcional se o keyring falhar (ex.: Linux headless).

## Riscos

- **keyring indisponível** (Linux sem Secret Service): mitigado por fallback + aviso claro na UI.
- **Sessão SSO curta definida pela organização** (PingFederate/MFA/conditional access): fora do controle do app; a Fase 2 reduz o impacto, mas não elimina.
- **Fase 3 depende de terceiros** (admin do tenant): não bloqueia as Fases 1–2.
