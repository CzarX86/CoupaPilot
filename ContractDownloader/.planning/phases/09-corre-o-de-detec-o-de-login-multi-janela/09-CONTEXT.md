# Phase 9 Context: detecção de login multi-janela

## Problema

No primeiro login macOS, Edge pode apresentar uma janela principal/nova aba e outra janela criada durante o fluxo Coupa/SSO. O detector anterior examinava apenas `driver.current_url`, podendo ignorar a janela autenticada indefinidamente.

## Objetivo

Detectar a sessão em qualquer `window_handle` controlado pelo Selenium e impedir que os gatilhos concorrentes de inicialização iniciem fluxos duplicados.

## Critérios

- Poll de autenticação percorre todas as janelas/tabs do driver.
- Cookies são coletados da janela Coupa autenticada.
- A UI informa quando múltiplas janelas são encontradas.
- `pywebviewready` e o timer de fallback não iniciam dois fluxos de autenticação.
- O perfil dedicado continua sendo usado; perfis pessoais não são tocados.
