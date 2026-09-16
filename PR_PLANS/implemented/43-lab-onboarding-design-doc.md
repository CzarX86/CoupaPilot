# Documento de Design: onboarding dos projetos da LAB

## Solução

O Overview recebe uma seção de onboarding e uma grade de cards com `data-lab-subtab`. A navegação já existente em `app.js` é reutilizada, evitando novo estado ou novo fluxo de JavaScript.

Cada `lab-panel-intro` recebe um bloco visual `lab-project-brief` com três campos: `Objective`, `Approach` e `Method`. O CSS define a grade, estados de foco/hover e a adaptação para telas estreitas.

## Decisões

- manter os textos da interface em inglês, conforme a convenção do projeto;
- usar botões nativos para os cards, garantindo foco e ativação por teclado;
- alterar apenas HTML/CSS e um teste estático, sem tocar na lógica analítica;
- atualizar o identificador de cache do stylesheet para que a versão local reflita o novo layout após reload.
