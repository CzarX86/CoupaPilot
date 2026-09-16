# Summary 08-01: seleção automática e perfil persistente

## Entregue

- `BrowserCatalog` detecta Edge/Chrome instalados e consulta o navegador padrão do sistema em macOS, Windows e Linux.
- `auto` usa o navegador padrão suportado; quando o padrão é Safari/Finicky/outro, usa fallback Edge/Chrome sem alterar o sistema.
- Settings continua permitindo escolher somente o navegador usado pelo Contract Downloader.
- `BrowserProfileManager` cria perfis em `~/.contract_downloader/browser_profiles/<browser>`, preserva o perfil Edge legado e registra caminhos/timestamps em `browser_profiles.json`.
- A GUI inicia o login manual automaticamente na primeira inicialização sem sessão válida ou após expiração.
- A interface usa linguagem neutra para Edge/Chrome e diferencia o navegador do aplicativo dos links externos.
- Diagnósticos exibem navegador selecionado, origem da seleção e perfis app-owned.
- O cache compartilhado continua sendo validado antes do pipeline; o worker CLI não abre navegador adicional.

## Validação

- `178 passed, 32 warnings`
- `compileall` aprovado
- `node --check src/gui/web/app.js` aprovado
- `git diff --check` aprovado

## Build macOS

- `ContractDownloader.app` regenerada em 2026-08-02 14:05:44.
- Arquitetura arm64.
- `codesign --verify --deep --strict` aprovado.
- Smoke launch nativo executado com sucesso e encerrado sem processos residuais.
- Backup anterior preservado em `ContractDownloader.app.old-20260802-140515-phase8`.

## Pendente

- UAT manual com Edge/Chrome reais, login Coupa, troca de navegador, expiração e Windows.
