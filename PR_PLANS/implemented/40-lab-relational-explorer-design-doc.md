# Documento de Design: explorador relacional da LAB

## Fonte de dados

O SQLite atual possui `sessions`, `po_downloads` e `po_attachments`. A primeira versão consulta essas tabelas sem criar uma camada paralela de persistência.

## Normalização experimental

- anexos cujo nome contém `SOW` ou `Statement of Work` são candidatos a SOW;
- anexos cujo nome contém `Invoice` ou `Inv` são candidatos a invoice;
- referências explícitas são extraídas do nome do arquivo;
- quando a SOW não possui número, o hash exato ou o nome normalizado vira um candidato marcado como tal;
- a associação do anexo à PO continua sendo a associação persistida em `po_attachments`.

O módulo `src/reports/lab_relationships.py` produz a árvore e os achados de cardinalidade como uma função determinística. A API apenas escolhe a execução e fornece os registros.

## Regras de validação

- uma PO sem SOW identificável: aviso;
- uma PO com mais de uma SOW candidata: erro de relacionamento;
- uma PO sem invoice identificável: aviso;
- a mesma referência de invoice sob mais de uma PO: erro de relacionamento.

As regras não alteram registros nem assumem que um nome de arquivo seja uma chave oficial.

## Interface

A subaba usa tabela hierárquica com botões `+`/`−`, expansão/recolhimento global, seletor de execução, métricas e lista de achados. O preview de navegador recebe uma árvore simulada para permitir inspeção visual sem credenciais.
