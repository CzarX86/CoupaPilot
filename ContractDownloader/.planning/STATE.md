---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Contract Downloader
status: executing
last_updated: "2026-08-03T00:30:00Z"
---

# Project State: Contract Downloader

## Project Reference

See: .planning/PROJECT.md

**Core value:** Baixar anexos de POs do Coupa com maxima velocidade, resiliencia e zero dependencia do legado.
**Current focus:** Phase 12 — Hardening do validador e UX da jornada New Run

## Phase Status

| Phase | Name | Status | Requirements |
|-------|------|--------|--------------|
| 1 | Setup & Estrutura | Completed in existing implementation | ISOL-01 |
| 2 | Database & Persistencia | Completed in existing implementation | PERS-01 |
| 3 | Engine Core | Completed in existing implementation | ENG-01, ENG-02, ERR-01, ERR-02, NET-01, NET-02, PARS-01 |
| 4 | Web UI & IPC Bridge | Completed in existing implementation | GUI-01, INPT-01, UI-01 |
| 5 | Integracao & Packaging | Completed in existing implementation | AUTH-01, TRAF-01, UPDT-01, OUT-01 |
| 6 | Testes & Validacao | Completed in existing implementation | PLAT-01 |
| 7 | Autenticacao e perfis de navegador desacoplados | Implemented; UAT pending | AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05 |
| 8 | Navegador e perfil de autenticação do aplicativo | Implemented; UAT pending | AUTH-06 |
| 9 | Correção de detecção de login multi-janela | Implemented; UAT pending | AUTH-01, AUTH-03 |
| 10 | Correções de validação e reparo de inputs | Implemented; UAT pending | GUI-01, INPT-01 |
| 11 | Visão filtrada de validação no Excel | Implemented; UAT pending | GUI-01, INPT-01 |
| 12 | Hardening do validador e UX da jornada New Run | Source improvements implemented; macOS build regenerated | GUI-01, INPT-01, ENG-01 |

**Progress:** 6/6 recent implementation plans complete | Phases 8–12 UAT pending

## Active Plan

- `phases/12-hardening-do-validador-e-ux-da-jornada-new-run/12-01-PLAN.md` — completed
- `phases/12-hardening-do-validador-e-ux-da-jornada-new-run/12-01-SUMMARY.md`
- `phases/11-vis-o-filtrada-de-valida-o-no-excel/11-01-PLAN.md` — completed
- `phases/11-vis-o-filtrada-de-valida-o-no-excel/11-01-SUMMARY.md`
- `phases/10-corre-es-de-valida-o-e-reparo-de-inputs/10-01-PLAN.md` — completed
- `phases/10-corre-es-de-valida-o-e-reparo-de-inputs/10-01-SUMMARY.md`
- `phases/09-corre-o-de-detec-o-de-login-multi-janela/09-01-PLAN.md` — completed
- `phases/09-corre-o-de-detec-o-de-login-multi-janela/09-01-SUMMARY.md`
- `phases/08-navegador-e-perfil-de-autentica-o-do-aplicativo/08-01-PLAN.md` — completed
- `phases/08-navegador-e-perfil-de-autentica-o-do-aplicativo/08-01-SUMMARY.md`
- `phases/07-autenticacao-e-perfis-de-navegador-desacoplados/07-01-PLAN.md` — completed
- `phases/07-autenticacao-e-perfis-de-navegador-desacoplados/07-01-SUMMARY.md`

## Recent Decisions

- O navegador para links externos permanece sob controle do sistema operacional.
- Edge e Chrome devem funcionar para login; o perfil exclusivo do aplicativo e o padrao.
- Nao implementar armazenamento criptografado nesta fase.
- Selenium permanece atras de uma abstracao; AuthService e a politica unica para GUI e CLI.
- A GUI faz login interativo no perfil dedicado; o worker CLI iniciado pela GUI apenas valida o cache.
- `auto` usa o navegador padrão do sistema quando Edge/Chrome; Settings altera somente o navegador do Contract Downloader.
- Perfis novos ficam em `~/.contract_downloader/browser_profiles/<browser>` e são registrados em `browser_profiles.json`; o perfil Edge legado é preservado.

## Blockers

- Agentes GSD especializados nao estao instalados no ambiente pi; o plano e os artefatos foram registrados pelo CLI GSD/manual protocol.
- Validacao nativa Windows depende de ambiente Windows.
- Login real no Coupa requer uma conta/sessao manual e nao foi automatizado nos testes.

## Next Action

Executar UAT com a build macOS regenerada: confirmar que POA16839021 é bloqueada, validar POs com oito dígitos, abrir/anotar o próprio XLSX, backup, divisão assistida de múltiplas POs, preview old/new de Fix, mapeamento automático e separadores CSV; depois validar Windows.
