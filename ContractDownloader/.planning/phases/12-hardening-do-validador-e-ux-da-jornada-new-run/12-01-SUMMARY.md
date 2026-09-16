# Summary 12-01: hardening integrado

## Entregue

### Validador e pipeline

- Visualização de correção XLSX/XLSM aplicada no próprio input, com backup de segurança, linhas limpas ocultas, células anotadas e comentários de validação; CSV/XLS são abertos sem conversão porque não suportam anotações Excel persistentes.
- Detecção de múltiplas POs antes da limpeza de caracteres, com divisão assistida em novas linhas somente após preview e confirmação.
- Separador CSV detectado por `csv.Sniffer` com fallback de consistência, compartilhado entre GUI e CLI.
- Mapeamento automático complementado por pontuação semântica dos valores e exemplos de amostra.
- Colunas de relatório anterior não são mais sinalizadas.
- PO canônica usa uppercase e somente `PO`/`PM` + dígitos; oito dígitos após o prefixo são o tamanho esperado e outros comprimentos geram aviso; correções exibem old/new antes de salvar.
- Leitura compartilhada de CSV/XLS/XLSX/XLSM com primeira planilha consistente e preservação de linhas CSV vazias.
- Fallback correto para UTF-8/CP1252.
- Normalização canônica de PO e Supplier para comparação, duplicidade e importação.
- Espaços no início/fim de PO/Supplier são ignorados no pipeline, exibidos como aviso e podem ser removidos pela ação segura `normalize_required_values`.
- Conflitos PO/Supplier bloqueados; reparo de duplicidade não remove relações ambíguas.
- Placeholders de PO/Supplier e valores convertidos pelo Excel bloqueados.
- Erros de fórmula (`#REF!`, `#VALUE!`, `#N/A` etc.) detectados.
- Headers vazios/ambíguos, colunas de relatório anterior, hierarquia vazia e riscos de nomes de pasta reportados.
- Reparo XLSM usa `keep_vba=True`; reparo/importação usam a primeira sheet como a validação.
- CLI passa pela mesma validação antes de criar a sessão.
- Destino de download validado antes da etapa 5.

### UX New Run 1–5

- Estado de arquivo, feedback e hierarquia resetados ao trocar/remover input.
- Revalidação preserva colunas desativadas e ordem escolhida.
- Colunas de hierarquia vazias não aparecem como níveis ativos.
- Mensagens agrupadas não são repetidas e grupos possuem tradução pt-BR.
- Mapeamento de PO/Supplier para a mesma coluna é bloqueado na UI e API.
- Verificação de destino com feedback contextual.
- Clique duplo em Start protegido por guard de requisição.
- XLSM aceito pelo seletor web.
- Review mostra o nome do input, mantendo o caminho completo no tooltip.

## Validação

- `196 passed, 32 warnings`.
- `compileall`, `node --check` e `git diff --check` aprovados.
- Build macOS arm64 regenerada, sincronizada em `ContractDownloader/ContractDownloader.app`, assinada ad hoc e smoke-tested.
- Build final regenerada após a regra estrita de PO; backup: `ContractDownloader.app.old-20260803-154250-strict-po-format`.
