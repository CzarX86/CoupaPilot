# Proposta de Mudança — UX do fluxo Power BI e isolamento do input

## Contexto

O fluxo New run precisava explicar pendências antes da navegação, permitir encontrar suppliers fora da lista NGSI, expor o catálogo completo de colunas do dataset, lembrar a seleção de colunas e separar completamente o workflow Excel do snapshot Power BI.

## Objetivo

Tornar a preparação de uma execução previsível e reutilizável, mantendo a origem do input explícita e levando o usuário para Active run assim que a execução for acionada.

## Critérios de aceitação

- A ação superior de cada etapa informa o que ainda está pendente quando a etapa não pode avançar.
- O supplier picker busca qualquer supplier, UU, GU ou código SAP no dataset e permite adicioná-lo à lista salva.
- O catálogo de colunas usa todas as colunas descobertas e a seleção é persistida no SQLite.
- A troca para Excel limpa snapshot, filtros e metadados Power BI do workflow atual.
- O clique em Start download abre Active run antes de autenticação, importação ou início do backend.
