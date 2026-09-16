# ADR 001: Consulta Power BI pelo Fabric CLI oficial

## Status

Aceito para o protótipo macOS.

## Contexto

O aplicativo precisa consultar um semantic model Power BI com a sessão do usuário, sem App Registration próprio e sem automação da UI do relatório.

## Decisão

Usar o cliente oficial Microsoft Fabric CLI (`fab api -A powerbi`) como adaptador inicial para o endpoint `ExecuteQueries`. A aplicação invoca o comando e interpreta a resposta JSON; não acessa cookies, local storage ou arquivos internos de token.

O cache de autenticação permanece sob responsabilidade do MSAL/Fabric CLI e do sistema operacional. A aplicação mantém somente o catálogo funcional de suppliers e seus estados de validação.

## Consequências

### Positivas

- funciona no macOS sem MSOLAP, ADOMD.NET ou COM;
- usa a sessão interativa do usuário;
- evita scraping da UI do Power BI;
- mantém a integração isolada do pipeline Coupa.

### Limitações

- o executável precisa localizar o helper `fab` ou `uv`;
- o empacotamento Windows exigirá uma estratégia própria para transportar o cliente;
- falhas do helper precisam ser apresentadas como indisponibilidade do Power BI.

## Alternativas rejeitadas nesta etapa

- MSOLAP/ADOMD.NET: dependência nativa e pouco adequada ao bundle macOS portátil;
- REST com App Registration: depende de autorização administrativa não disponível;
- scraping do relatório: frágil e desnecessário após a validação do endpoint de consulta.
