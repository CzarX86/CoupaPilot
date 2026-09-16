# Contract Downloader 1.0.0

Aplicativo portátil para baixar anexos de POs do Coupa.

## Caminho oficial

O produto usa uma única autenticação SSO do Microsoft Edge corporativo e processa os documentos com `httpx.AsyncClient`/HTTP2. A sessão é validada antes de cada lote e armazenada no Windows Credential Manager ou no macOS Keychain. O legado da raiz não é importado, empacotado nem usado como fallback.

Na primeira autenticação, feche todas as janelas do Edge somente quando o aplicativo solicitar. O app detecta o perfil com `@unilever.com`, captura os cookies uma única vez e fecha apenas o WebDriver que criou.

## Execução portátil

```text
Start-ContractDownloader.cmd
```

Não é necessário instalar Python, bibliotecas ou executar como administrador. A distribuição oficial usa `ContractDownloader.exe` no Windows quando disponível.

Consulte [`docs/INSTRUCOES_CONTRACT_DOWNLOADER.md`](docs/INSTRUCOES_CONTRACT_DOWNLOADER.md) para o fluxo completo e [`docs/authentication-architecture.md`](docs/authentication-architecture.md) para os estados HIL e a política de sessão.
