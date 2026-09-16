# Contract Downloader — instruções rápidas

## 1. Baixar e extrair

1. Baixe o arquivo ZIP enviado pela equipe.
2. Extraia **todo o conteúdo** do ZIP. Não execute o aplicativo de dentro do ZIP.
3. Se o Windows informar **Erro 0x80010135: caminho muito longo**, extraia em uma pasta curta, por exemplo:

   `C:\ContractDownloader`

Não renomeie nem remova as pastas `runtime` e `app`.

## 2. Iniciar o aplicativo

Abra duas vezes o arquivo:

`Start-ContractDownloader.cmd`

Não é necessário instalar Python, instalar bibliotecas ou executar como administrador.

Somente na primeira abertura de uma pasta extraída, o Windows pode demorar alguns segundos para preparar os arquivos; as próximas aberturas pulam essa etapa.
Durante os downloads, o processo auxiliar roda sem abrir uma janela de terminal; o painel de logs permanece dentro do aplicativo.

Para uma distribuição com aparência nativa do Windows, use `ContractDownloader.exe` quando ele estiver disponível. Esse executável pode ser fixado na barra de tarefas e usa o ícone do aplicativo. O arquivo `Start-ContractDownloader.cmd` continua sendo o launcher da edição Python portátil.

Para gerar esse executável em uma máquina Windows de desenvolvimento, execute `build_windows.cmd` na pasta do projeto. O resultado fica em `dist\ContractDownloader.exe`; o build deve ser feito no próprio Windows para incluir as dependências nativas corretas.

O aplicativo mostra uma tela de carregamento durante a inicialização e impede duas instâncias simultâneas. Se ele já estiver aberto, a segunda tentativa informa isso e encerra com segurança.

## 3. Fazer o login

Quando solicitado:

1. Se todas as janelas do Edge estiverem fechadas, o app detecta automaticamente o perfil que contém `@unilever.com`.
2. Se o app solicitar, feche todas as janelas do Microsoft Edge. O app apenas espera; ele nunca encerra o Edge à força.
3. O WebDriver abre o perfil corporativo detectado, captura o SSO do Coupa e fecha somente a janela criada pelo app.
4. Retorne ao Contract Downloader e aguarde a confirmação da sessão.

O perfil pessoal nunca é copiado, apagado ou alterado. A sessão fica no armazenamento seguro nativo do Windows ou macOS e o Edge não é aberto nas execuções seguintes enquanto o Coupa aceitar a sessão.

O processamento oficial usa HTTP/2 com 11 workers e não abre browser por worker. Não há fallback automático para a versão legada.

## 4. Executar uma lista de POs

1. Escolha o arquivo Excel ou CSV de input.
2. Valide o arquivo.
   - Se as colunas obrigatórias (PO e Fornecedor) não forem encontradas, o aplicativo mostra **Map the file columns**: selecione qual coluna contém o número da PO e qual contém o fornecedor.
   - Erros são agrupados por tipo (linhas vazias, POs duplicadas, caracteres estranhos). Use o botão **Fix** de cada grupo para corrigir automaticamente, ou **Open file to fix** para editar manualmente.
3. Escolha a estrutura de pastas — **Fornecedor** é sempre o primeiro nível e a **PO** o último. Use os botões ×/+ para ativar ou desativar níveis intermediários.
4. Revise a árvore de pastas e escolha a pasta de destino.
5. Revise as informações e clique em **Start download**.

O arquivo original de input é preservado durante a execução. Inputs de execuções anteriores são protegidos (somente leitura) e, se reutilizados, uma cópia de trabalho é criada para a nova execução.

## 5. Corrigir uma PO com erro

1. Abra **Run History**.
2. Abra os detalhes da execução.
3. Clique em **Retry** na PO com erro.
4. Corrija o número da PO e confirme.
5. Se o retry funcionar, escolha **Save correction** para atualizar o input e o relatório.
6. Escolha **Discard retry** somente se não quiser manter os arquivos baixados nem a correção.

## 6. Se o aplicativo não abrir

1. Verifique o arquivo `startup.log` na pasta do aplicativo.
2. Execute `ContractDownloader-Diagnostics.cmd`.
3. Envie o conteúdo de `startup.log` e o relatório de diagnóstico para a equipe de suporte.

Não apague `runtime`, `app` ou os arquivos `.cmd`.

## 7. Arquivos importantes

- `Start-ContractDownloader.cmd`: inicia o aplicativo.
- `ContractDownloader-Diagnostics.cmd`: gera um diagnóstico do ambiente.
- `startup.log`: registra problemas de inicialização.
- `runtime`: Python portátil usado pelo aplicativo.
- `app`: arquivos do Contract Downloader.

Downloads, autenticação, histórico e configurações são armazenados fora da pasta do aplicativo.
