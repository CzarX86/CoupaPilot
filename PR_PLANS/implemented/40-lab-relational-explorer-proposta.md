# Proposta de Mudança: explorador relacional da LAB

## Objetivo

Adicionar uma visualização experimental em árvore para validar a cadeia SOW → PO → invoice a partir dos registros locais capturados pelo aplicativo.

## Escopo

- nova subaba `Relationship Explorer` dentro da `LAB`;
- seleção da execução SQLite analisada;
- expansão mãe/filho SOW → PO → documentos;
- contadores e achados de validação para chaves ausentes, múltiplos SOWs por PO e invoices associadas a múltiplas POs;
- evidência explícita quando uma chave foi inferida por nome ou hash do documento.

## Fora de escopo

- alteração automática de dados;
- criação de uma relação definitiva sem uma chave canônica extraída do documento;
- alteração das consultas Power BI de GRIR/FX;
- integração automática com Timesheet.

## Critérios de aceitação

- a subaba aparece dentro da LAB e não altera a seleção existente de POs;
- cada nível pode ser expandido ou recolhido;
- uma execução sem SOW/invoice continua visível e gera um achado;
- a interface deixa claro que o SQLite atual possui POs e anexos, não tabelas canônicas de SOW/invoice;
- regras de cardinalidade têm testes automatizados.
