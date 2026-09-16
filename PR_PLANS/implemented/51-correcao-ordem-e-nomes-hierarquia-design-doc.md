# Documento de Design: correção de ordem e nomes da hierarquia

## Decisão

Uma ordem explícita recebida pelo pipeline representa a lista completa de níveis de pasta, incluindo o fornecedor. Quando nenhuma ordem explícita é enviada, o comportamento padrão continua colocando o fornecedor antes dos demais níveis.

## Implementação

- `process_all_pos.py` passa a extrair e persistir os níveis completos na ordem recebida, usando o nome real da coluna de fornecedor para inputs mapeados.
- O frontend deixa de aplicar uma segunda regra que reposicionava o fornecedor para o primeiro nível durante a validação.
- A função de limpeza de nomes converte separadores de caminho, troca espaços por `_` e colapsa `_+` antes de remover bordas inseguras.
- A API usa a mesma normalização ao gerar a prévia e ao persistir o `output_subdir` da sessão.

## Compatibilidade

Chamadas internas antigas que fornecem apenas níveis opcionais continuam recebendo o fornecedor como fallback. O caminho explícito do worker fornece o nome da coluna e, portanto, respeita exatamente a seleção da interface.

Não há decisão arquitetural nova e não é necessário criar ADR.

## Verificação

- teste de unidade para `Year / Supplier / CRG` no helper de hierarquia;
- teste de sessão do worker para confirmar o `output_subdir` persistido;
- teste da API para os dois formatos de nome reportados;
- `node --check` no frontend;
- suíte `pytest --ignore=tests/e2e`.
