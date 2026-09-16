# Documento de Design: Hierarquia de pastas do download Power BI

## Decisão

O provider Power BI será a autoridade dos campos `crg` e `year`. Esses campos permanecem opcionais no catálogo, mas são incluídos no preview e no snapshot interno para que estejam disponíveis na confirmação da hierarquia sem depender da seleção analítica da tabela.

## Snapshot e contrato de dados

CRG usa `Cost Centre[Cost Reporting Group Code]` e Ano usa `PurchaseOrder_Allocated[Year]`. O snapshot mantém os códigos de fornecedor antes do separador `<|>`, como metadados, enquanto os campos que podem formar pastas ficam depois do separador. O worker usa apenas os campos posteriores ao separador como candidatos opcionais.

O Ano possui fallback para o ano da data de criação da PO quando o valor calculado não estiver presente na resposta. Valores ausentes dos campos adicionados não quebram respostas antigas de teste ou snapshots incompletos.

## Hierarquia

O frontend inicia o fluxo Power BI com `SUPPLIER` ativo e CRG/Ano desativados. A seleção passa em `hierarchyOrder` para o backend. O worker filtra explicitamente os candidatos por essa ordem; portanto, uma seleção explícita não reativa todos os campos disponíveis.

Ao montar o caminho, os componentes são comparados sem distinção entre maiúsculas e minúsculas. Um valor igual a um nível já incluído é descartado, evitando repetição do fornecedor e de níveis opcionais.

## Compatibilidade

O caminho de retry que reconstrói o mapa de subpastas também reaplica `COUPA_HIERARCHY_ORDER`. O caminho legado da API recebe a mesma proteção contra níveis e valores duplicados.

Não há decisão arquitetural nova: a mudança reutiliza o formato `<|>` e o contrato de ordem de hierarquia existentes.

## Verificação

- testes do provider cobrem o catálogo, as referências DAX e a inclusão de CRG/Ano;
- testes do snapshot cobrem a separação dos códigos do fornecedor e dos níveis de pasta;
- testes do worker cobrem seleção explícita, a estrutura `Fornecedor/CRG/Ano` e o caso `EY/EY/EY`;
- `node --check` valida a sintaxe do frontend.
