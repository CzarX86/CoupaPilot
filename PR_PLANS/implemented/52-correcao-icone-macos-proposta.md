# Proposta de Mudança: corrigir o ícone ativo no macOS

## Contexto

O ícone do Contract Downloader aparece nítido no Finder quando o aplicativo está fechado, mas fica desfocado no Dock e no multitarefa enquanto o aplicativo está aberto.

## Objetivo

Permitir que o macOS use o `icon.icns` de alta resolução do bundle durante toda a execução.

## Escopo

- não passar o `favicon.ico` ao backend Cocoa do pywebview no macOS;
- preservar o override de ícone nas plataformas que precisam dele;
- adicionar teste para evitar regressão;
- gerar um novo bundle macOS.

## Critérios de aceitação

1. No macOS, o pywebview não recebe o favicon como ícone de runtime.
2. O bundle mantém `icon.icns` e `NSHighResolutionCapable=true`.
3. O comportamento nas demais plataformas permanece preservado.
4. Os testes focados e a assinatura do bundle passam.
