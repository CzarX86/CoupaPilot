# Proposta de Mudança: Recuperar autenticação Coupa com DevTools e fallback dedicado

## Contexto

O fluxo recente passou a iniciar o WebDriver diretamente no diretório real do Microsoft Edge. Esse diretório é compartilhado pelo Edge normal, pode estar bloqueado e não é uma fonte confiável para uma sessão Coupa reutilizável. A regressão produziu falhas `DevToolsActivePort` mesmo quando o perfil dedicado usado por versões anteriores ainda continha dados de sessão.

## Objetivo

Voltar a oferecer o caminho de autenticação funcional e, quando possível, conectar a uma instância Edge já aberta por DevTools sem assumir o lock do perfil pessoal.

## Critérios de aceitação

- Usar DevTools somente quando houver um endpoint Edge local verificável.
- Não iniciar WebDriver apontando para o diretório pessoal real quando não houver endpoint DevTools.
- Reutilizar o perfil dedicado do aplicativo como fallback, preservando o onboarding SSO existente.
- Não exibir nem registrar valores de cookies.
- Manter o Edge do usuário aberto após um attach DevTools.
- Cobrir fallback, attach e seleção de opções por testes automatizados.
