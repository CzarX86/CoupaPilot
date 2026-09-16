---
phase: "07"
name: "Autenticacao e perfis de navegador desacoplados"
created: 2026-08-02
status: ready
---

# Phase 7 — Contexto

## Decisoes do usuario

- O navegador usado para abrir links externos continua sendo definido pelo sistema operacional; o aplicativo nao deve gerenciar nem impor esse navegador.
- O publico principal usa Windows e e composto majoritariamente por usuarios nao tecnicos.
- Edge e Chrome devem ser suportados para a autenticacao Coupa.
- Nao implementar armazenamento criptografado nesta fase.
- Ao consolidar GUI e CLI, preservar o comportamento que ja e funcional e adotar a interface de autenticacao com melhor experiencia e estado observavel.
- O login deve ser detectado de forma precisa e rapida.
- A logica de cache, autenticacao e perfis de navegador deve ser desacoplada do monolito e nao redundante.

## Decisoes de implementacao

- Selenium permanece como mecanismo de navegador controlado; a implementacao fica atras de uma abstracao para Edge e Chrome.
- Perfis exclusivos do aplicativo sao o caminho padrao, evitando bloqueio e descoberta heuristica de perfis pessoais.
- O cache existente (`cookies.json` e `auth_cache.db`) continua legivel para compatibilidade; o armazenamento criptografado fica fora do escopo.
- `AuthService` sera a politica unica de sessao. A GUI tera o fluxo interativo e o worker CLI validara o cache sem abrir um segundo navegador silenciosamente.
- `src/engine/authenticator.py` permanecera como facade de compatibilidade durante a migracao.

## Areas de discricao

- Escolher o navegador instalado automaticamente quando apenas um estiver disponivel; quando houver Edge e Chrome, manter uma selecao configuravel simples.
- Manter diagnosticos sem expor cookies, credenciais ou caminhos completos desnecessarios.
- Preservar as APIs publicas existentes sempre que isso nao impedir a separacao de responsabilidades.

## Fora desta fase

- Armazenamento criptografado via DPAPI/Keychain.
- Suporte a Safari para captura de cookies.
- Reutilizacao automatica de perfis pessoais existentes como comportamento padrao.
- Troca de Selenium por Playwright.
