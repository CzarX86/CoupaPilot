# Proposta de Mudança: Aba Timesheet Analysis

## Objetivo

Adicionar uma aba independente para carregar, persistir e analisar timesheets, seguindo o storytelling:

```text
Coverage → Reported Work → Invoiced Value → Variances → Exceptions & Actions
```

A primeira fonte será o workbook de Project Services fornecido pelo usuário, com foco na aba `Resource Timesheet`.

## Contexto

O workbook contém `PWO`, `Billing Type`, recursos, período, dias e fees. Ele não contém, de forma confiável, o número da PO nem um código UU dedicado. Portanto, nesta etapa a análise terá granularidade principal PWO e deixará o vínculo PWO→PO/invoice explicitamente pendente.

Timesheets só são aplicáveis a contratos T&M. Linhas Fixed Price serão classificadas como `Not applicable` e não entrarão nos totais de trabalho T&M.

## Escopo

- selecionar e carregar workbook `.xlsb`, `.xlsx` ou `.csv`;
- ler a aba `Resource Timesheet` quando disponível;
- persistir o snapshot analítico localmente para reabrir a aba já preenchida;
- classificar linhas T&M, Fixed Price e classificação pendente;
- agregar por fornecedor e PWO;
- exibir cobertura, trabalho reportado, fees, reconciliação pendente e exceções;
- permitir filtrar fornecedor e escopo de cobrança;
- manter a aba separada do fluxo de PO, GRIR e FX.

## Fora de escopo nesta etapa

- inferir vínculo PWO→PO apenas pelo título;
- comparar invoice real sem uma chave de ligação confirmada;
- extrair timesheet de documentos Coupa;
- tratar Fixed Price como ausência de timesheet.

## Critérios de aceitação

- o usuário consegue carregar o workbook e ver a data da última atualização;
- ao reabrir o app, o snapshot anterior aparece sem recarregar o arquivo;
- Fixed Price não altera os totais T&M;
- os cards e a tabela usam a mesma seleção de fornecedor/escopo;
- a interface mostra claramente que a reconciliação de invoice e PO está pendente enquanto não houver vínculo;
- erros de colunas ausentes ou formato incompatível são apresentados sem corromper o cache anterior.
