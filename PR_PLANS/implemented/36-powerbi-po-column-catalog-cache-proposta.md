# Proposta de Mudança: Cache do catálogo de colunas de POs do Power BI

> Esta etapa foi complementada pela Proposta 38, que adiciona a descoberta dinâmica do metadata do datamodel.

## Contexto

O seletor de colunas da prévia de POs precisa exibir um inventário estável dos campos que o provider consegue consultar no semantic model. Recarregar esse inventário a cada abertura da modal é desnecessário e dificulta a transparência sobre quando a lista foi atualizada.

## Objetivo

Persistir o catálogo de colunas em SQLite, reutilizá-lo por até 30 dias e oferecer uma ação explícita para atualização sob demanda.

## Escopo

- criar um cache singleton para o catálogo de colunas de POs;
- atualizar automaticamente o cache quando ele estiver ausente ou vencido;
- expor uma operação de atualização forçada pela ponte da GUI;
- mostrar no modal a data da última atualização;
- preservar a seleção de colunas que ainda existir após uma atualização.

## Fora do escopo

- descoberta automática de novas colunas por introspecção do Power BI;
- mudança no contrato DAX ou no pipeline de download do Coupa;
- persistência das escolhas pessoais do usuário entre sessões.

## Critérios de aceitação

1. A primeira leitura grava o inventário no SQLite.
2. Leituras dentro de 30 dias usam o cache sem consultar o provider.
3. Um cache vencido é atualizado automaticamente.
4. O botão `Refresh catalog` força uma nova gravação.
5. A interface informa a última atualização do catálogo.
