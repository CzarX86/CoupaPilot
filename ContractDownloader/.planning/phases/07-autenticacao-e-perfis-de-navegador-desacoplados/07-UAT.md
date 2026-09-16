---
phase: "07"
name: "Autenticacao e perfis de navegador desacoplados"
created: 2026-08-02
status: pending
---

# Phase 7 — UAT manual

Executar em Windows e macOS, com o aplicativo fechado entre cenarios quando indicado.

| # | Cenário | Resultado esperado | Status |
|---|---|---|---|
| 1 | Edge instalado e Chrome fechado | Settings lista Edge; login abre perfil exclusivo do app | Pendente |
| 2 | Chrome instalado e escolhido em Settings | Login abre Chrome, sem tocar no perfil pessoal | Pendente |
| 3 | Edge/Chrome pessoal já aberto | Login do app continua funcionando em perfil separado | Pendente |
| 4 | Login Coupa novo | `_coupa_session` é capturado, salvo e o browser de login fecha | Pendente |
| 5 | Reabrir o app após login | Sessão aparece válida sem abrir browser | Pendente |
| 6 | Coupa/rede temporariamente indisponível | Estado aparece indisponível; cache não é apagado | Pendente |
| 7 | Sessão expirada | Estado aparece expirado e o login é solicitado novamente | Pendente |
| 8 | Iniciar execução pela GUI | CLI reutiliza o cache e não abre um segundo browser | Pendente |
| 9 | Executar CLI diretamente sem cache | CLI pode abrir o browser escolhido para login | Pendente |
| 10 | Abrir link de PO | URL é entregue ao launcher/default browser do sistema operacional | Pendente |
| 11 | Reset sign-in state | Cache e perfil do app são removidos; perfis pessoais e downloads permanecem | Pendente |

## Resultado

Pendente de validação manual nativa, especialmente Windows.
