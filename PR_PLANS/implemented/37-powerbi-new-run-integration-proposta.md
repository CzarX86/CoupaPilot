# Proposta de Mudança: Power BI como input preferencial do New run

## Contexto

O fluxo `New run` atualmente começa por um template Excel ou por um arquivo Excel/CSV preenchido pelo usuário. A seleção de POs construída no Power BI já consegue consultar fornecedor, Management Unit e informações do dataset de POs, mas permanece acoplada à LAB e não alimenta diretamente o download de documentos do Coupa.

Além disso, a execução do Coupa não oferece uma reconciliação clara quando a conta não possui acesso a todas as Company Codes. O dataset do Power BI contém Company Code e Legal Entity, permitindo comparar a expectativa analítica com o resultado obtido no Coupa.

## Objetivo

Tornar `Power BI PO Mass Download Dataset` o primeiro método de input do `New run`, permitindo:

- escolher explicitamente a fonte da lista de POs antes de abrir qualquer formulário;
- usar Power BI como método recomendado e Excel/CSV como fallback para casos específicos;
- selecionar Supplier UU, Management Unit e `PO Creation Date`;
- usar dropdowns compactos com checkboxes para Suppliers, MU Hierarchy e Dates, além do filtro de Purchase Family já existente;
- pesquisar o dataset Power BI e adicionar grupos UU ao grupo `NGSI Suppliers`, mantendo os fornecedores em cache no início;
- visualizar uma árvore de anos, quarters e meses entre o ano mínimo e máximo do dataset;
- consultar e revisar as POs encontradas, inicialmente todas selecionadas;
- excluir POs individualmente ou por seleção no cabeçalho da tabela;
- gerar um snapshot interno do dataset, sem exigir um arquivo preparado pelo usuário;
- manter as etapas atuais de validação, hierarquia de pastas, destino e início;
- registrar automaticamente a origem e os filtros da execução;
- comparar Company Code e Legal Entity esperados no Power BI com a resposta do Coupa;
- identificar no relatório as POs potencialmente bloqueadas por falta de acesso à Company Code.

## Ordem dos métodos de input

1. `Power BI PO Mass Download Dataset` — método preferencial;
2. `Create Excel template`;
3. `Use existing Excel/CSV input`.

## Escopo

- mover a seleção de POs usada pelo download para o painel de input do `New run`, mantendo a LAB desacoplada;
- adicionar cache do intervalo de `PO Creation Date`;
- filtrar a consulta pela coluna confirmada `PO Creation Date`;
- consolidar uma PO em uma única linha de input, ordenando Management Units pelo commitment alocado;
- preservar Supplier UU como agrupador de pasta e Company Code como expectativa de acesso;
- adicionar preflight por amostragem de Company Code e diagnóstico por PO;
- armazenar metadados de origem, filtros e diagnóstico no SQLite e no relatório final;
- dividir consultas Power BI por períodos quando necessário, evitando a divisão padrão por Management Unit.

## Fora do escopo

- adicionar um botão de integração entre LAB e New run;
- alterar as análises GRIR/FX da LAB;
- mudar a autenticação ou conceder acesso a Company Codes no Coupa;
- duplicar uma PO no download por ela possuir múltiplas Management Units.

## Critérios de aceitação

1. O usuário escolhe primeiro entre Power BI e Excel/CSV; ao escolher Power BI, o formulário de seleção é exibido.
2. O resultado mostra uma linha por PO, com todas selecionadas por padrão e seleção global no cabeçalho.
3. O snapshot gerado contém PO, Supplier UU, Management Units consolidadas por commitment, PO Creation Date, Company Code e Legal Entity.
4. A execução continua usando as etapas de validação, pastas, destino e início existentes.
5. A hierarquia `Supplier UU > Management Unit(s) > PO` não cria downloads duplicados para POs rateadas entre MUs.
6. A execução registra fonte, filtros, quantidade encontrada, quantidade selecionada e períodos consultados.
7. O preflight amplia a amostra quando encontra `Access denied` e marca a Company Code como suspeita somente com evidência consistente.
8. O relatório diferencia Company Code/Legal Entity esperados no Power BI, Company Code observado no Coupa e o motivo provável de falha de acesso.
9. Os métodos Excel/CSV continuam funcionando sem mudança de contrato para inputs antigos.
