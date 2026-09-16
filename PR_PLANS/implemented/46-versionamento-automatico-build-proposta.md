# Proposta de Mudança: Incrementar a versão a cada build

## Contexto

O build do Contract Downloader empacota o arquivo `.version`, que é usado pela interface e pelo mecanismo de atualização, mas a versão não era alterada automaticamente entre builds.

## Escopo

- Incrementar automaticamente o número de patch no início de cada build.
- Empacotar a nova versão no `.app` ou executável.
- Restaurar a versão anterior se o empacotamento falhar.

## Critérios de Aceitação

- `1.0.0` passa para `1.0.1` em um build.
- A interface recebe a mesma versão do artefato gerado.
- Versões inválidas são rejeitadas sem alteração silenciosa.

