# Relatório de Implementação: correção do ícone no macOS

## Resultado

O pywebview deixou de sobrescrever o ícone de alta resolução do bundle macOS com o `favicon.ico` de baixa resolução. O macOS continuará usando `icon.icns` no Dock, no multitarefa e nas demais representações da aplicação.

## Entregas

- adicionada a seleção de ícone de runtime em `ContractDownloader/src/main.py`;
- macOS retorna `None` para que o ícone do bundle seja usado;
- Windows/Linux preservam o comportamento anterior;
- teste de regressão adicionado em `ContractDownloader/tests/test_main.py`;
- bundle gerado em `ContractDownloader/dist/ContractDownloader.app`, versão `1.0.22`.

## Verificações

- `uv run pytest ContractDownloader/tests/test_main.py ContractDownloader/tests/test_python_portable_build.py -q`: 8 aprovados;
- `git diff --check`: aprovado;
- `codesign --verify --deep --strict ContractDownloader/dist/ContractDownloader.app`: aprovado;
- bundle contém `CFBundleIconFile=icon.icns` e `NSHighResolutionCapable=true`.
