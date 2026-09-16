# ADR 005: Catálogo de POs derivado do metadata do dataset Power BI

## Status

Aceito.

## Contexto

O seletor de campos de PO precisa representar o datamodel real, e não somente uma lista manual de campos usados em consultas anteriores. A aplicação já possui um adaptador Fabric CLI e um cache SQLite persistente.

## Decisão

Usar o metadata do dataset para descobrir tabelas e colunas e persistir um snapshot normalizado. Cada campo mantém sua tabela, referência completa, tipo e visibilidade. Os campos confirmados continuam como fallback porque medidas e alguns modelos semânticos podem não aparecer no endpoint de colunas.

## Consequências

### Positivas

- o usuário vê os campos disponíveis no metadata recebido do dataset;
- a origem de cada campo é auditável e reaproveitável na construção DAX;
- novas colunas podem aparecer no refresh mensal ou sob demanda;
- o cache reduz chamadas de metadata repetidas.

### Limitações

- a disponibilidade depende das permissões e do formato de resposta do Power BI;
- metadata indisponível mantém somente o catálogo confirmado;
- selecionar muitas colunas ou campos de tabelas sem relacionamento pode gerar uma consulta DAX inválida ou grande.

## Alternativas rejeitadas

- manter apenas catálogo manual: não atende ao inventário completo;
- consultar dados para inferir nomes: não é metadata confiável e aumenta custo;
- adicionar uma biblioteca Power BI: duplicaria o adaptador Fabric CLI e complicaria o empacotamento.
