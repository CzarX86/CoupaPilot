# Proposta de Mudança: Robustez e observabilidade do login Coupa no Edge

## Contexto

No macOS, processos auxiliares do Microsoft Edge podem permanecer ativos após o encerramento da janela. A busca ampla por qualquer processo contendo `Microsoft Edge` produzia falsos positivos. Além disso, a simples existência de `SingletonLock` era tratada como bloqueio mesmo quando o PID proprietário já não existia, e as falhas do WebDriver não indicavam com precisão a etapa afetada.

## Escopo

- Bloquear o perfil somente quando o processo principal do Edge estiver ativo ou quando o proprietário vivo do `SingletonLock` estiver relacionado ao Edge.
- Ignorar locks órfãos sem removê-los do perfil corporativo.
- Manter helpers, updater e crash reporter apenas como informação diagnóstica quando não possuírem o lock.
- Registrar etapas da autenticação em JSONL sem cookies, tokens ou caminhos completos do usuário.
- Verificar acesso ao macOS Keychain/Windows Credential Manager sem revelar o conteúdo armazenado.
- Diferenciar ausência de sessão de falha de leitura do armazenamento seguro.
- Exibir perfil selecionado, lock, processos, sessão segura e último evento no diagnóstico do host.

## Critérios de Aceitação

- Um helper isolado não impede a abertura do perfil.
- Um lock cujo PID vivo pertence ao Edge impede a abertura e orienta o uso de `⌘Q`.
- Um lock órfão não é apagado nem bloqueia preventivamente o WebDriver.
- O perfil passado em `--profile-directory` é sempre o candidato detectado, não um nome fixo.
- Cookies válidos permanecem no armazenamento seguro e são reutilizados até o Coupa invalidá-los.
- O relatório identifica a fase anterior ao erro sem registrar segredos.

