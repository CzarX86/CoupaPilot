# Documento de Design: Proteção contra lock do Edge no macOS

## Solução

No macOS, `CorporateEdgeProfileDetector.edge_is_running()` passa a usar `pgrep -f "Microsoft Edge"`, cobrindo o processo principal e os helpers. Depois que o diretório raiz é localizado, o detector verifica `SingletonLock`, `SingletonCookie` e `SingletonSocket`. Um lock residual resulta em ação requerida, sem remoção automática do arquivo.

O launcher mantém os argumentos atuais de perfil. Quando o WebDriver retorna `DevToolsActivePort`, `SeleniumBrowserLauncher` converte a falha em uma mensagem curta orientando o usuário a encerrar o Edge com `⌘Q` e tentar novamente.

## Segurança

O aplicativo não encerra processos do usuário nem remove locks do perfil pessoal. A mudança apenas detecta o estado e bloqueia uma inicialização potencialmente corrompida.

