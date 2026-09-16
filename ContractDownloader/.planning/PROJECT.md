# Contract Downloader

## What This Is

Aplicativo desktop independente, cross-platform, de alta performance para download de anexos de POs do Coupa. Substitui o fluxo manual de download por uma engine HTTP/2 assincrona com interface web-nativa premium (pywebview + Glassmorphism). Totalmente isolado do projeto legado CoupaPilot — nao altera, modifica ou copia codigo existente.

## Core Value

Baixar anexos de POs do Coupa com maxima velocidade (69.44 POs/min), resiliencia a falhas e experiencia de usuario premium — zero dependencia do projeto legado.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] ISOL-01: Isolamento total do legado CoupaPilot
- [ ] GUI-01: Interface pywebview com HTML5/CSS3/JS Glassmorphism
- [ ] ENG-01: Engine HTTP/2 assincrona (httpx, 11 workers default)
- [ ] ENG-02: Relatorio Excel consolidado
- [ ] PERS-01: SQLite multi-sessao com tracking de status
- [ ] INPT-01: Drag-and-drop .xlsx/.csv
- [ ] ERR-01: Circuit Breaker por Company Code (coluna `legal entity`)
- [ ] ERR-02: Lazy Creation + limpeza automatica de pastas
- [ ] OUT-01: Exportacao de relatorio consolidado
- [ ] UI-01: Dashboard de historico de execucoes
- [ ] NET-01: Network benchmarker com recomendacoes automaticas
- [ ] NET-02: Rate limiter (0.03s delay, cooldown >500 POs)
- [ ] AUTH-01: Edge Authenticator (Selenium → cookies → HTTP engine)
- [ ] TRAF-01: Controle de trafego e cooldown
- [ ] UPDT-01: Self-updater via GitHub Releases API
- [ ] PLAT-01: Cross-platform Windows + macOS
- [ ] PARS-01: Parser HTML two-pass (data-url + href)

### Out of Scope

- Alteracao do projeto legado CoupaPilot — isolamento total
- Tkinter — substituido por pywebview
- Fontes customizadas — fontes nativas do SO (Segoe UI / San Francisco)
- Instalador com privilegios admin — app 100% portatil single-file exe
- Suporte Linux — Windows e macOS apenas

## Context

- **Ambiente Python:** Gerenciado via `uv` com dependencias leves e independentes
- **Legado CoupaPilot:** Referencia conceitual e de regras de negocio apenas; nunca alterado
- **Pacotes criticos:** pywebview, httpx, beautifulsoup4, lxml, pyinstaller, selenium
- **Tipografia:** Fontes nativas do SO (Segoe UI / San Francisco) — carregamento offline instantaneo
- **Build:** PyInstaller single-file, assets Web UI acessiveis via `sys._MEIPASS`

## Constraints

- **Isolamento:** Nenhum import ou dependencia de arquivos do legado (src/, tools/)
- **Portabilidade:** Executavel unico, sem instalador, sem privilegios admin
- **Concorrencia:** Default 11 workers via semaforo httpx, ajustavel via UI
- **Timeline:** Definir durante discussao de fases
- **Plataformas:** Windows (Edge WebView2) + macOS (WebKit)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| pywebview sobre Tkinter | UI premium nativa, ~35MB RAM, sem admin, cross-platform | — Pending |
| AuthService com browser controlado | Selenium extrai cookies 1x em perfil exclusivo do app, fecha o browser e entrega a sessao ao pipeline HTTP; Edge e Chrome sao suportados | — Pending |
| Navegador externo sob controle do SO | Links externos usam o launcher/default browser do sistema; o app nao gerencia essa preferencia | — Pending |
| Network Benchmarker com sliders | Teste de latencia preenche recomendacoes; usuario valida manualmente | — Pending |
| Fontes nativas do SO | Segoe UI / San Francisco — carregamento offline instantaneo | — Pending |
| Self-Updater portatil | GitHub API → download em background → script atomico de replace | — Pending |
| Concorrencia default 11 workers | Semaforo httpx.AsyncClient, configuravel via UI | — Pending |
| Circuit Breaker: coluna `legal entity` | Leitura direta, sem deteccao autonoma | — Pending |
| Circuit Breaker: 15% threshold, min 3 POs, 100% erro | Suspende companhia e marca SKIPPED_VERIFICATION_REQUIRED | — Pending |
| Lazy Creation + Cleanup | So cria pasta ao baixar 1o anexo; remove orfas em falha | — Pending |
| SQLite com schema sessions + po_downloads | 5 statuses, timestamps, erros detalhados, funcoes de resume | — Pending |
| Rate limiter: 0.03s delay, cooldown >500 POs | Previne sobrecarga no servidor Coupa | — Pending |
| Parser HTML two-pass | data-url em spans + href em anchors | — Pending |
| Build PyInstaller single-file | sys._MEIPASS para assets, sem dependencias externas | — Pending |
| API contract — Authenticator | `async def get_coupa_cookies() -> dict` | — Pending |
| API contract — Benchmarker | `async def benchmark(urls: list[str]) -> dict` | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-21 after ingest of 3 docs (1 PRD + 2 SPECs)*
