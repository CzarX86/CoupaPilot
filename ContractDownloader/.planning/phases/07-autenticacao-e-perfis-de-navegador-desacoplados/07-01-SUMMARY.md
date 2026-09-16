---
phase: "07"
plan: "01"
status: completed
completed: 2026-08-02
---

# Phase 7 / Plan 01 — Summary

## Entregue

- Criado o pacote `src/auth` com modelos de estado, `CookieStore`, `SessionValidator`, catalogo Edge/Chrome, perfis exclusivos do aplicativo e `AuthService`.
- Mantida compatibilidade com `cookies.json`, `auth_cache.db` e imports antigos via facade em `src/engine/authenticator.py`.
- GUI usa o `AuthService` para autenticacao interativa e o CLI canonico usa o mesmo servico em modo nao interativo quando iniciado pela GUI.
- O worker CLI nao abre um segundo navegador silenciosamente; retorna erro de autenticacao quando o preflight da GUI nao deixou uma sessao utilizavel.
- Edge e Chrome podem ser escolhidos em Settings. Links externos continuam usando `open`, `os.startfile` ou `xdg-open` conforme o sistema operacional.
- O diagnostico passou a listar browsers suportados, drivers e perfis pertencentes ao aplicativo sem ler cookies.
- Textos da UI foram atualizados para nao prometer reutilizacao de perfil pessoal do Edge.

## Verificacao

- `uv run pytest -q` → **175 passed, 32 warnings**.
- `uv run python -m compileall -q src process_all_pos.py` → aprovado.
- `git diff --check` → aprovado.
- Selenium real com login Coupa e validacao nativa Windows ainda requer teste manual em ambiente correspondente.
- Build macOS arm64 regenerada em `ContractDownloader.app`; `codesign --verify --deep --strict` aprovado e smoke launch nativo executado com sucesso.

## Observacoes

- Armazenamento criptografado nao foi implementado, conforme decisao do usuario.
- O armazenamento legado continua em arquivo/SQLite e nao possui TTL artificial; o Coupa continua sendo a autoridade sobre validade.
- A selecao automatica prefere Edge quando ambos estao instalados; a preferencia pode ser alterada em Settings para Chrome.
