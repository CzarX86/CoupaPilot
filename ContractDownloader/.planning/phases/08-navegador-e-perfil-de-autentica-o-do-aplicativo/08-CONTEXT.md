# Phase 8 Context: navegador e perfil de autenticação do aplicativo

## Objetivo

Consolidar o fluxo aprovado para que o Contract Downloader escolha automaticamente o navegador de autenticação a partir do navegador padrão suportado do sistema, permita override nas configurações e use perfis persistentes exclusivos do aplicativo.

## Workflow aprovado

1. Detectar Edge e Chrome instalados.
2. Em `auto`, usar o navegador padrão do sistema quando ele for Edge ou Chrome; se o padrão for outro ou não puder ser detectado, usar o fallback suportado determinístico.
3. Permitir que o usuário selecione Edge ou Chrome em Settings. Essa preferência afeta somente o Contract Downloader; não altera o navegador padrão do sistema nem links externos.
4. Criar e registrar um perfil dedicado por navegador no diretório de estado do aplicativo.
5. Na primeira autenticação daquele navegador, abrir o perfil dedicado para login manual no Coupa.
6. Persistir o perfil e copiar apenas os cookies necessários para o cache compartilhado do pipeline.
7. Validar o cache nas execuções seguintes; abrir o perfil dedicado novamente apenas quando for necessária renovação/reautenticação.

## Fora do escopo

- Copiar perfil pessoal, banco de senhas, histórico ou extensões.
- Ler ou descriptografar diretamente o banco de cookies do perfil pessoal.
- Alterar o navegador padrão do macOS/Windows.
- Embutir a página de login em WebView.

## Critérios de aceitação

- `auto` seleciona o navegador padrão suportado do sistema.
- A preferência explícita em Settings é persistida e usada pela GUI, CLI e diagnósticos.
- Cada navegador usa somente seu perfil app-owned persistente e o caminho fica registrado localmente sem segredos.
- Login manual no primeiro uso captura e valida cookies; execução posterior reutiliza o cache sem abrir outro navegador.
- Troca de navegador não remove o perfil do navegador anterior.
- Links externos continuam usando o launcher padrão do sistema.
