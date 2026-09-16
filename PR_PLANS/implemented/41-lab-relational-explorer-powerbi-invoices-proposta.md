# Proposta de Mudança: invoices do Power BI no Relationship Explorer

## Objetivo

Completar a árvore da LAB para exibir a relação `contrato/SOW → PO → invoice`, combinando os anexos baixados do Coupa com os datasets de PO e invoice já conectados ao Power BI.

## Escopo

- usar o número identificado da SOW como chave principal do contrato;
- usar o SHA-256 do documento SOW baixado quando o número não for identificado;
- agrupar POs de uma mesma execução sob o mesmo contrato quando compartilharem essa chave;
- consultar no Power BI o commitment de cada PO e as invoices relacionadas;
- renderizar as invoices do dataset Power BI como filhos da PO;
- manter a visão local disponível com um aviso quando o Power BI não puder ser consultado.

## Fora do escopo

- identificação semântica definitiva de contratos;
- extração de número ou valor de contrato a partir do conteúdo PDF;
- criação de tabelas canônicas de SOW, contrato ou invoice no SQLite;
- alteração das consultas de seleção de POs ou do fluxo de download.

## Critérios de aceitação

- duas POs com o mesmo número de SOW aparecem sob o mesmo contrato;
- duas POs sem número de SOW, mas com o mesmo SHA-256 do documento SOW, aparecem sob o mesmo contrato;
- cada PO exibe seu commitment e suas invoices retornadas pelo dataset Invoice;
- uma PO sem invoice Power BI permanece na árvore e gera um aviso;
- a tela continua exibindo a árvore local se a consulta Power BI falhar;
- testes automatizados cobrem a chave SHA-256, o enriquecimento Power BI e a renderização das invoices.
