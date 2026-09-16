# Proposta de Mudança: Corrigir a abertura do perfil corporativo do Edge

## Contexto

O detector do perfil corporativo identifica corretamente o nome do perfil do Edge, mas retorna a pasta do perfil como `user_data_dir`. O launcher então combina essa pasta com `--profile-directory`, fazendo o Edge receber o diretório raiz incorreto e impedindo a reabertura do perfil SSO.

## Escopo

- Retornar o diretório raiz de dados do Edge no candidato detectado.
- Manter o nome (`Default`, `Profile 1`, etc.) separado para `--profile-directory`.
- Adicionar uma regressão unitária para o contrato detector/launcher.

## Critérios de Aceitação

- Um perfil corporativo detectado produz `--user-data-dir` apontando para a raiz `Microsoft Edge`.
- O nome do perfil aparece somente em `--profile-directory`.
- Os testes de autenticação e a suíte unitária passam sem abrir o Edge real.

## Decisão de Design

Não foi criado documento de design separado: a mudança é local, não altera a arquitetura nem o contrato externo da aplicação.
