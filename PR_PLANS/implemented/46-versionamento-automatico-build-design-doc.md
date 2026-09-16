# Documento de Design: Versionamento automático do build

## Solução

O script `build.py` lê `.version`, valida o formato `MAJOR.MINOR.PATCH`, incrementa somente o patch e grava o novo valor antes de chamar o PyInstaller. O mesmo arquivo é incluído no bundle por `--add-data`.

Se o PyInstaller retornar erro, o script restaura a versão anterior antes de encerrar. Não foi adicionada dependência nem alterado o contrato da API da aplicação.

## Teste

Um teste unitário usa um arquivo temporário para verificar leitura, incremento e persistência da versão sem executar o PyInstaller.

