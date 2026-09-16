# ADR 004: Snapshot local para análise de timesheets

## Status

Aceito

## Contexto

Timesheets chegam como workbooks locais e podem ser atualizados fora do aplicativo. A aba precisa abrir com o último resultado conhecido, mas o arquivo original não deve ser duplicado nem depender de um serviço remoto.

## Decisão

Ler `.xlsb`/`.xlsx`/`.csv` com o provider local, normalizar e agregar por PWO, e persistir somente o snapshot analítico no SQLite da aplicação. O caminho, hash, sheet e timestamp ficam junto do snapshot para auditoria local.

## Consequências

- a primeira abertura da aba continua útil mesmo sem o workbook presente;
- o cache é pequeno comparado ao workbook bruto;
- alterações no workbook só aparecem após novo carregamento;
- o vínculo PWO→PO não será inventado quando a fonte não o fornecer.
