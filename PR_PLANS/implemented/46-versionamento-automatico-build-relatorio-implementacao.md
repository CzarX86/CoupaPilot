# Relatório de Implementação: Versionamento automático do build

## Entrega

- `build.py` agora incrementa o patch da versão automaticamente.
- O `.version` atualizado continua sendo incluído no artefato.
- Falhas do PyInstaller restauram a versão anterior.
- Foi adicionado teste unitário para o incremento.

## Verificação

- Testes do build: `5 passed`.
- A próxima build macOS será publicada como `1.0.1`.

