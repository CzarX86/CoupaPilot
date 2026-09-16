# Proposta de Mudança: Aba de integração Power BI para seleção de POs

## 1. Identificação

- **Número da proposta**: 29
- **Título**: Aba isolada para consulta Power BI e preparação de POs
- **Data**: 4 de agosto de 2026
- **Status**: Implementado preliminar
- **Escopo**: somente `ContractDownloader`; o fluxo atual de downloads não será alterado

## 2. Contexto

O usuário precisa consultar o semantic model `Committed Spend BG Dataset` no Power BI para localizar suppliers, selecionar grupos UU, visualizar a hierarquia de Management Unit e preparar uma lista de POs antes do processamento no Coupa.

O acesso direto ao endpoint `ExecuteQueries` foi validado com o cliente oficial Microsoft Fabric CLI. A consulta agregada da hierarquia de Management Unit também foi validada, retornando 1.086 caminhos.

## 3. Objetivo

Adicionar uma aba independente no app macOS para:

1. exibir suppliers prioritários armazenados localmente;
2. pesquisar suppliers no Power BI com correspondência textual/fuzzy;
3. permitir cadastrar resultados encontrados na lista local;
4. validar códigos UU armazenados e avisar quando deixarem de existir;
5. carregar a hierarquia Management Unit independentemente de ano e supplier;
6. permitir a seleção dos níveis da hierarquia para uso posterior na consulta de POs.

## 4. Fora de escopo nesta entrega

- alteração do fluxo atual de New run/downloads;
- início automático de downloads no Coupa;
- alteração do formato oficial do input file;
- confirmação definitiva dos códigos dos 10 suppliers prioritários;
- build Windows.

## 5. Critérios de aceitação

- A nova aba abre sem quebrar New run, Active run, History, Learn ou Settings.
- A lista inicial de suppliers prioritários aparece mesmo antes de uma consulta remota.
- O usuário consegue pesquisar, marcar e adicionar suppliers encontrados.
- Suppliers adicionados são persistidos no estado local do aplicativo.
- A validação remota informa códigos UU ausentes sem removê-los silenciosamente.
- A hierarquia de Management Unit é carregada sem filtro de ano/supplier.
- A execução local do app macOS pode ser empacotada com `build.py --macos`.
- Nenhum token, cookie ou conteúdo de PO é gravado em log ou no repositório.
