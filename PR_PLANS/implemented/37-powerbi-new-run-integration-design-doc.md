# Documento de Design: Power BI como input preferencial do New run

## Decisão

O Power BI será integrado ao primeiro passo do `New run`, mas o pipeline Coupa continuará recebendo um arquivo tabular internamente. Esse arquivo será um snapshot gerado pelo aplicativo a partir das POs selecionadas; ele não será um artefato que o usuário precisa criar ou manter.

Essa decisão reaproveita a validação, o arquivamento de input, a criação de pastas e o relatório existentes, reduzindo o risco de uma segunda implementação do pipeline.

O primeiro passo agora começa com uma escolha explícita de fonte. Power BI é o caminho recomendado e abre o formulário de filtros; Excel/CSV permanece como fallback e abre o fluxo de template/arquivo. Ao continuar pelo Power BI, o snapshot é criado automaticamente antes da etapa de validação.

## Contrato do snapshot interno

Cada PO selecionada será emitida uma única vez com os campos principais:

- `PO_NUMBER`;
- `SUPPLIER` — Supplier UU, usado como agrupador principal de pasta;
- `COMPANY_CODE` — Company Code esperada no Coupa;
- `LEGAL_ENTITY_CODE` e `LEGAL_ENTITY_NAME`;
- `PO_CREATION_DATE`;
- `MANAGEMENT_UNIT` — concatenação determinística das MUs, em ordem decrescente de commitment alocado;
- campos de evidência Power BI, como valores de commitment e goods received.

Para uma PO rateada entre MUs, os registros analíticos serão agregados apenas no snapshot. A PO continuará sendo uma unidade de download. O nome da pasta de MU será sanitizado, limitado e, quando necessário, receberá um sufixo curto de hash para evitar colisões.

Inputs legados sem `COMPANY_CODE` continuam usando a coluna configurada de fornecedor como fallback do agrupamento de acesso, preservando compatibilidade.

## Seleção de datas

O provider consulta `MIN` e `MAX` de `PurchaseOrder_Allocated[PO Creation Date]` e persiste esse intervalo em SQLite. A interface usa dropdowns compactos com checkboxes para Suppliers, MU Hierarchy e Dates, além do filtro de Purchase Family já existente. O menu de Suppliers exibe apenas o grupo `NGSI Suppliers`, começando pelos fornecedores em cache e permitindo pesquisar o dataset Power BI e adicionar novos grupos UU. O menu Dates constrói uma árvore completa entre os anos mínimo e máximo, incluindo todos os quarters e meses desse intervalo, mesmo quando uma combinação específica não possui PO; por padrão, apenas os anos ficam visíveis e recolhidos.

O filtro enviado ao provider é uma lista normalizada de períodos (`YYYY`, `YYYY-QN`, `YYYY-MM`). O provider converte os períodos em intervalos semiabertos de datas e aplica o predicado sobre `PurchaseOrder_Allocated[PO Creation Date]`. A coluna também pode ser incluída na prévia para auditoria.

## Consulta e particionamento

O caminho normal consulta períodos de data consolidados. Quando houver mais de um intervalo independente, o provider executa consultas menores por período e deduplica somente registros idênticos; linhas distintas de uma mesma PO, especialmente por Management Unit, são preservadas para o rateio.

Management Unit não é uma partição padrão porque uma PO pode aparecer em várias MUs. Se uma consulta ainda exceder o limite de resposta, a mensagem orienta a refinar o período/fornecedor; o frontend exibe o progresso das consultas por período.

## Diagnóstico de Company Code

Antes dos downloads, o pipeline agrupa as POs do snapshot pela `COMPANY_CODE` esperada e faz uma amostra pequena de páginas Coupa por grupo. Se uma amostra receber `Access denied`, a amostra é ampliada. O grupo só é marcado como bloqueado quando as respostas ampliadas forem consistentes; caso contrário, as POs seguem para processamento normal.

Durante o processamento, respostas HTTP 401/403 ou páginas com sinais explícitos de bloqueio gravam diagnóstico `ACCESS_DENIED_CONFIRMED`. O preflight consistente grava `ACCESS_DENIED_LIKELY` para as POs ainda pendentes da Company Code. Falhas de rede, timeout, autenticação e PO inexistente permanecem categorias distintas.

O SQLite armazenará, quando disponível, `expected_company_code`, `expected_legal_entity` e `access_diagnosis`. O relatório combina esses campos com `COUPA_COMPANY_CODE` extraído da página Coupa, permitindo distinguir:

- Company Code esperada e confirmada;
- Company Code divergente;
- acesso negado confirmado/provável;
- falha técnica ou autenticação;
- ausência da PO no Coupa.

## Histórico da execução

Os filtros serão registrados automaticamente em `sessions.source_metadata_json`, sem nova tarefa para o usuário. O objeto conterá a fonte oficial, filtros de Supplier UU/MU/data, intervalo consultado, total encontrado, total selecionado e quantidade de chunks.

## Interface

Os controles atuais de fornecedor, Management Unit e prévia serão renderizados dentro do painel Power BI do primeiro passo do New run, inicialmente recolhido atrás da escolha de fonte. A LAB permanece disponível como área desacoplada e não é necessária para iniciar o download. A prévia não exporta CSV e não exige um botão intermediário para transferir as POs: `Continue to validation` prepara o snapshot internamente.

O cabeçalho do painel usa o nome `Power BI PO Mass Download Dataset` e concentra as instruções do método. O status de conexão do Power BI fica no próprio toolbar e assume a ação de login somente quando a sessão está expirada ou não autenticada. A jornada usa uma navbar sticky com a ação da etapa atual no lado direito; os controles de avanço são movidos temporariamente para essa área e devolvidos aos seus containers originais quando a etapa muda.

A tabela terá checkbox por PO e checkbox no cabeçalho. Todas as POs começam selecionadas. Um botão `Use selected POs in New run` grava o snapshot interno e habilita a sequência atual de validação.

## Verificação

- testes unitários do intervalo de datas, normalização dos períodos, DAX e consolidação de MUs;
- testes do cache de datas e dos metadados de sessão;
- testes do preflight e da classificação de access denied;
- teste da criação do snapshot Power BI e compatibilidade com inputs legados;
- `py_compile`, `node --check`, `pytest` focado e `git diff --check`.
