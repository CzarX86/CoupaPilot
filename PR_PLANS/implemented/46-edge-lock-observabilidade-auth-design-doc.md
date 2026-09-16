# Documento de Design: Lock real e rastreamento do login Coupa

## Decisão

O processo principal do Edge continua sendo detectado pelo nome exato no macOS. Processos auxiliares são contados apenas para diagnóstico. A autoridade para decidir se o perfil está ocupado passa a ser o `SingletonLock`: o PID é extraído do link, sua existência é verificada e o comando do processo é inspecionado para confirmar vínculo com o Edge.

Se o PID estiver morto ou tiver sido reutilizado por outro processo, o marcador é considerado órfão. O aplicativo não o remove do perfil corporativo; o Edge/WebDriver continua responsável pela recuperação nativa.

## Observabilidade

Cada autenticação recebe um identificador e grava eventos em `~/.contract_downloader/auth_diagnostics.jsonl` com:

- estado atual e estado anterior;
- duração acumulada;
- mensagem e código amigável do erro;
- data/hora da etapa.

Consultas, tokens, cookies e diretórios completos do usuário são sanitizados. Falhas na escrita do diagnóstico não interrompem a autenticação.

O diagnóstico do host apresenta o perfil detectado, processos auxiliares não bloqueantes, proprietário do lock, acessibilidade do armazenamento seguro, presença de sessão e último evento de autenticação.

## Armazenamento de sessão

No macOS, o Keychain é consultado diretamente; no Windows, o Credential Manager. O health check informa apenas se o backend está disponível, legível e se contém uma sessão. Uma falha de leitura sem cache legado deixa de ser interpretada como simples ausência de credencial.

## Alternativa não adotada

Não foi implementada cópia temporária do perfil corporativo. Ela copiaria dados pessoais, poderia capturar bancos SQLite/WAL inconsistentes e não resolveria um perfil ainda em uso. Poderá ser avaliada como fallback somente se houver falha comprovada após esta correção.

