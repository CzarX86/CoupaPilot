# Relatório de Implementação: storytelling da LAB

## Resultado

A tab `LAB` agora começa com a subtab `Overview`, que apresenta a narrativa visual antes dos controles e resultados. O usuário vê o fluxo `Scope → PO set → GRIR → FX`, as fontes envolvidas e a indicação de que Timesheets ainda são uma análise independente. A narrativa deixou de ficar redundante no topo de todas as subtabs.

A tipografia e o espaçamento da LAB foram ampliados levemente para melhorar a leitura. Os cards analíticos também receberam `Method & data sources`, recolhido por padrão. Ao abrir, o usuário encontra cálculo, variáveis, regra de inclusão e fonte de dados sem transformar o dashboard em um texto contínuo.

Cada sub-tab recebeu:

- uma pergunta/objetivo analítico;
- uma descrição de método;
- badge da fonte de dados;
- nota `How to read it` ou indicação de limitação.

Os cards analíticos também receberam `Method & data sources`, recolhido por padrão. Ao abrir, o usuário encontra cálculo, variáveis, regra de inclusão e fonte de dados sem transformar o dashboard em um texto contínuo.

Os headers das tabelas agora permitem ordenação ascendente/descendente por clique ou teclado, com indicação visual e sem separar invoices dos respectivos POs na tabela FX.

GRIR e FX também mostram visualmente os principais componentes da decomposição. Nenhuma consulta, métrica, seleção, exportação ou regra de cálculo foi alterada.

## Verificação

- `node --check src/gui/web/app.js`: aprovado;
- `py_compile` dos módulos alterados: aprovado;
- `git diff --check`: aprovado;
- testes de provider e cache: 22 aprovados;
- testes Playwright focados da jornada: 2 aprovados;
- verificação estática dos marcadores de narrativa no HTML: aprovada.
- inspeção headless da tela LAB em 1440 px: estrutura editorial visível e screenshot gerado para QA.
- inspeção headless com card de método expandido: 3 cards no painel de fonte, abertura e conteúdo visíveis.
- teste headless de ordenação: PO textual/numericamente ordenado e grupos FX PO→invoice preservados.

O bundle macOS atualizado foi gerado em `ContractDownloader/dist/ContractDownloader.app`, passou pela verificação de assinatura e também está disponível em `ContractDownloader/ContractDownloader.app`.
