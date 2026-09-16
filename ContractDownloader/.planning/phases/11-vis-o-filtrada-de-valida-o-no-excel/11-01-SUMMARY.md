# Summary 11-01: abrir cópia filtrada no Excel

## Entregue

- Nova API `open_filtered_input_view` revalida o input e gera uma cópia de trabalho.
- A cópia preserva todas as linhas e colunas originais.
- Colunas compreensíveis `Source Row`, `Validation Status` e `Validation Issues` identificam os problemas.
- AutoFilter é configurado para mostrar `ERROR` e `WARNING`; linhas `OK` também são ocultadas explicitamente para que a visão filtrada funcione ao abrir no Excel.
- CSV e XLS legado são exportados para uma cópia XLSX; XLSX/XLSM preservam a cópia do workbook.
- O arquivo original nunca é alterado.
- A GUI adiciona o botão `Open filtered copy in Excel` com mensagem de segurança.
- Microsoft Excel é priorizado no macOS; o aplicativo associado é usado como fallback.
- O seletor de arquivos passou a aceitar XLSM.

## Validação

- Suíte completa: `182 passed, 32 warnings`.
- `compileall`, `node --check` e `git diff --check` aprovados.
- Testes verificam filtro, linhas afetadas e preservação byte a byte do original.
- Build macOS arm64 regenerada em `dist/ContractDownloader.app` e sincronizada em `ContractDownloader.app` após o encerramento do app anterior.
- `codesign --verify --deep --strict` aprovado.
- Smoke launch nativo aprovado, sem processos residuais.
- Build regenerada novamente após o ajuste do filtro, com `codesign --verify --deep --strict` aprovado.
