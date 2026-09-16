# Documento de Design: Aba Timesheet Analysis

## Arquitetura mínima

Será criado `src/timesheet_provider.py`, usando pandas já presente no projeto e `pyxlsb` para leitura nativa de `.xlsb`. O provider normaliza somente as colunas necessárias, agrega por PWO e retorna dados serializáveis para a UI.

O snapshot será salvo em SQLite na tabela `timesheet_analysis_cache`, já que a aplicação possui `SessionDB` persistente por usuário. O cache contém o caminho da fonte, hash, sheet, timestamp e JSON analítico; o workbook original não é copiado para o repositório nem para o banco.

## Normalização

Colunas esperadas:

- `PWO`;
- `Billing Type`;
- `Title`;
- `Resource Name`;
- `Period Start Date`;
- `Days`;
- `Fees`;
- `Level`.

O fornecedor é lido de coluna dedicada quando existir. Na ausência, é inferido somente por aliases explícitos no título; os demais ficam como `Unknown`, sem criar um vínculo falso.

Classificação:

- `tm`: billing type contém T&M ou não contém Fixed Price quando a classificação é conhecida;
- `fixed_price`: billing type contém `Fixed Price`;
- `classification_pending`: billing type vazio ou não reconhecido;
- linhas sem PWO geram exceção de mapeamento e não entram na agregação por PWO.

## Contrato de API

- `select_timesheet_file()` seleciona a fonte;
- `load_timesheet_file(path)` lê e salva o snapshot;
- `get_timesheet_analysis_cache()` retorna o snapshot persistido;
- `filter_timesheet_analysis(supplier, scope)` recalcula a visão filtrada sobre o snapshot.

## Interface

A nova navegação será `Timesheet Analysis`, com cinco blocos sequenciais:

1. `Coverage`: fonte, última atualização, PWO T&M, Fixed Price não aplicável e cobertura de classificação;
2. `Reported work`: recursos, dias e fees reportados;
3. `Invoiced value`: estado `Pending invoice linkage`, sem inventar valor;
4. `Variances`: estado `Pending PWO/invoice mapping`;
5. `Exceptions & actions`: tabela por PWO e alertas de linhas sem PWO/classificação pendente.

A tabela fica agregada por PWO e fornecedor. O detalhe por recurso permanece fora da primeira entrega para evitar carregar 128 mil linhas no navegador.

## Limites conhecidos

O workbook não possui PO Number de forma confiável. O vínculo com as análises Power BI será adicionado quando existir uma chave de negócio confirmada entre SOW/PWO/PO.
