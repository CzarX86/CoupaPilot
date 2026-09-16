# Requirements: Contract Downloader

**Defined:** 2026-05-20
**Updated:** 2026-05-21 after ingest of 3 docs (1 PRD, 2 SPEC)
**Core Value:** Baixar anexos de POs do Coupa com maxima velocidade, resiliência e zero dependência do projeto legado.

## v1 Requirements

### Isolation

- [ ] **ISOL-01**: Aplicacao deve ser totalmente independente do projeto legado CoupaPilot. Ambiente Python gerenciado via `uv` com dependencias proprias. Nenhum arquivo do legado (src/, tools/) é alterado, modificado ou copiado.

### GUI

- [ ] **GUI-01**: Interface renderizada via `pywebview` usando engine WebView nativa do SO (Edge WebView2 no Windows, WebKit no macOS). HTML5/CSS3/JavaScript com design Glassmorphism. Inclui: dashboard de telemetria, sliders interativos, console de logs, area de drag-and-drop e aba de historico de execucoes. ~35MB RAM, ~18MB executavel, sem privilegios de admin.

### Engine

- [ ] **ENG-01**: Motor HTTP assincrono com `httpx.AsyncClient`, HTTP/2, semaforo de concorrencia (default 11 workers).
- [ ] **ENG-02**: Gera relatorio Excel consolidado mesclando planilha original com resultados de download (status, metadados).

### Persistence

- [ ] **PERS-01**: Banco SQLite unificado com tabelas `sessions` (timestamps de execucao) e `po_downloads` (status: PENDING, DOWNLOADING, COMPLETED, FAILED, SKIPPED_VERIFICATION_REQUIRED; company_code; contagem de anexos; erros detalhados). Funcoes para carregar historico na UI, resetar status de companhias para retry e restaurar batches interrompidos.

### Input

- [ ] **INPT-01**: Area de drag-and-drop para arquivos .xlsx e .csv. Arquivo é parseado e exibido antes de iniciar downloads.

### Error Handling

- [ ] **ERR-01**: Circuit Breaker por Company Code — le coluna `legal entity`. Se >= 15% das POs de uma companhia (minimo 3 POs) forem processadas e a taxa de erro for exatamente 100%, suspende POs restantes marcando-as como SKIPPED_VERIFICATION_REQUIRED. UI exibe banner de alerta com opcao "Confirm and Retry" que reprocessa sem duplicados.
- [ ] **ERR-02**: Lazy Creation de pastas (so cria diretorio fisico ao baixar primeiro anexo com sucesso) + limpeza automatica (`shutil.rmtree`) de pastas vazias/orfas em caso de falha.

### Output

- [ ] **OUT-01**: Relatorio Excel consolidado salvo junto ao diretorio de saida.

### UI Features

- [ ] **UI-01**: Aba de Historico de Execucoes — revisar runs passadas, exportar reports, retomar execucoes pausadas/interrompidas.

### Network

- [ ] **NET-01**: Benchmarker de rede — modulo `benchmarker.py` que testa latencia contra endpoints Coupa, preenche sliders na UI com recomendacoes otimas de concorrencia e delay. Usuario clica "Analyze Connection", valida e clica "Start".
- [ ] **NET-02**: Rate limiter com delay controlado (default 0.03s) e janelas de cooldown para lotes acima de 500 POs.

### Authentication

- [ ] **AUTH-01**: Browser-assisted Authenticator — ao clicar "Connect to Coupa", abre um browser Chromium suportado via Selenium em perfil exclusivo do aplicativo, permite login manual, captura cookies de sessao, fecha o browser e migra autenticacao para a engine HTTP assincrona.
- [ ] **AUTH-02**: Auth state precisa distinguir rapidamente sessao valida, expirada, ausente e indisponivel sem apagar ou invalidar o cache por falha temporaria de rede.
- [ ] **AUTH-03**: GUI e CLI devem usar uma politica unica de cache e validacao; o worker CLI nao abre um segundo browser silenciosamente quando executado pela GUI.
- [ ] **AUTH-04**: Edge e Chrome instalados devem ser detectados e suportados sem exigir que o usuario informe diretorios de perfil; o perfil exclusivo do aplicativo e o padrao.
- [ ] **AUTH-05**: Links Coupa externos devem continuar sendo abertos pelo launcher/default browser configurado no sistema operacional, sem que o aplicativo imponha Safari, Edge ou Chrome.
- [x] **AUTH-06**: Em modo automático, o Contract Downloader deve usar o navegador padrão do sistema quando ele for Edge/Chrome, permitir override de navegador somente nas configurações do aplicativo, registrar o perfil dedicado por navegador e solicitar login manual apenas no primeiro uso ou após expiração.

### Traffic Control

- [ ] **TRAF-01**: Controle de trafego com delays configuraveis e cooldown para grandes lotes. Previne sobrecarga do servidor.

### Updater

- [ ] **UPDT-01**: Self-updater portatil — verifica novas versoes via GitHub Releases API, exibe notificacao na UI, baixa binario em background, executa script batch/shell nativo para substituicao atomica e reinicia o app.

### Platform

- [ ] **PLAT-01**: Suporte cross-platform Windows e macOS. Fontes nativas do SO (Segoe UI no Windows, San Francisco no macOS). Empacotamento PyInstaller para cada plataforma.

### Parser

- [ ] **PARS-01**: Parser HTML unificado com BeautifulSoup em duas passagens: (1) busca `data-url` em elementos `<span>`, (2) busca `href` em tags `<a>` tradicionais.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Alteracao do projeto legado CoupaPilot | Isolamento total — legado é referencia conceitual apenas |
| Tkinter | Substituido por pywebview para UI premium |
| Fontes customizadas/bundled | Fontes nativas do SO garantem carregamento offline instantaneo |
| Instalador com privilegios admin | App 100% portatil, single-file exe |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ISOL-01 | Phase 1 | Pending |
| GUI-01 | Phase 4 | Pending |
| ENG-01 | Phase 3 | Pending |
| ENG-02 | Phase 3 | Pending |
| PERS-01 | Phase 2 | Pending |
| INPT-01 | Phase 4 | Pending |
| ERR-01 | Phase 3 | Pending |
| ERR-02 | Phase 3 | Pending |
| OUT-01 | Phase 5 | Pending |
| UI-01 | Phase 4 | Pending |
| NET-01 | Phase 3 | Pending |
| NET-02 | Phase 3 | Pending |
| AUTH-01 | Phase 7 | Pending |
| AUTH-02 | Phase 7 | Pending |
| AUTH-03 | Phase 7 | Pending |
| AUTH-04 | Phase 7 | Pending |
| AUTH-05 | Phase 7 | Pending |
| AUTH-06 | Phase 8 | Complete |
| TRAF-01 | Phase 5 | Pending |
| UPDT-01 | Phase 5 | Pending |
| PLAT-01 | Phase 6 | Pending |
| PARS-01 | Phase 3 | Pending |

**Coverage:**

- requirements: 22 total (17 original v1 + 5 architecture refinements; AUTH-01 is refined in Phase 7)
- Mapped to phases: 22
- Unmapped: 0

---
*Requirements defined: 2026-05-20*
*Last updated: 2026-05-21 after ingest of implementation_plan.md + 2 SPECs*
