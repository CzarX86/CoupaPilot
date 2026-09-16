# Plan: Bootstrapping Contract Downloader (Independent Standalone App)

> **Nota de arquitetura (2026-08-12):** Este é um plano histórico de bootstrapping. A versão oficial 1.0.0 usa `SecureSessionStore`, captura o perfil corporativo existente do Edge somente após o usuário fechar o Edge e processa documentos por Direct HTTP. Consulte [`authentication-architecture.md`](authentication-architecture.md) para as regras atuais.

Este plano descreve as etapas técnicas detalhadas para criar, estruturar, implementar e empacotar a nova aplicação portátil **Contract Downloader** na pasta isolada `/ContractDownloader`.

## User Review Required

> [!IMPORTANT]
> **Isolamento Total & Referência Estrita**: A nova aplicação viverá exclusivamente dentro da pasta `/ContractDownloader` no repositório. O ambiente Python será gerenciado de forma independente via `uv` com suas próprias dependências leves.
> 
> **IMPORTANTE**: O projeto legado em `src/` ou `tools/` **nunca** será alterado, modificado ou copiado. Ele servirá puramente como referência conceitual e de regras de negócio. Todo o desenvolvimento do `ContractDownloader` será construído totalmente do zero, sem copiar ou colar arquivos do projeto original.
> 
> **Portabilidade Sem Admin & Web UI Premium (Padrão Bravo BI)**: Substituiremos o Tkinter pelo framework **pywebview**. Ele abre uma janela desktop nativa utilizando a engine de WebView nativa do sistema operacional (Microsoft Edge WebView2 no Windows e WebKit no macOS). Isso permite renderizar uma interface gráfica ultra-premium baseada em HTML5, CSS3 (TailwindCSS/Glassmorphism real) e JavaScript, consumindo apenas ~35MB de RAM e mantendo o executável leve (~18MB), 100% portátil e sem requisição de privilégios de administrador.

## Decisões Técnicas Consolidadas

> [!IMPORTANT]
> ### 1. Captura de Cookies (Login)
> *   **Captura SSO do Edge existente**: Ao solicitar autenticação, o app orienta o usuário a fechar todas as janelas do Edge, detecta o perfil com `@unilever.com`, abre-o uma única vez via WebDriver, captura os cookies e fecha somente o WebDriver. A sessão segue para a Engine Direct HTTP assíncrona.
> 
> ### 2. Ajuste de Concorrência e Banda
> *   **Network Benchmarker com Sliders**: A UI exibirá sliders interativos de concorrência e delays. Antes de iniciar, o usuário clica em "Analisar Conexão", o módulo `benchmarker.py` realiza testes de latência rápidos contra o Coupa e pré-preenche na UI as recomendações ótimas (ex: 11 conexões concorrentes, 0.03s delay). O usuário valida e clica em "Iniciar" manualmente.
> 
> ### 3. Tipografia Offline
> *   **Fontes Nativas do SO**: Utilizaremos estritamente fontes profissionais presentes nos próprios sistemas operacionais (como *Segoe UI* no Windows, e *San Francisco* no macOS) para assegurar carregamento instantâneo offline e velocidade de inicialização.
> 
> ### 4. Self-Updater Portátil
> *   **Version Checker & Autoupdate**: A UI exibirá notificações estéticas de novas versões a partir da API de Releases do GitHub. Ao clicar em atualizar, o app baixa o executável em segundo plano, executa um script batch/shell nativo temporário que substitui os arquivos antigos e reinicia o app automaticamente.

---

## Proposed Changes

### [NEW] [ContractDownloader Directory Structure](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader)

Toda a infraestrutura do subprojeto será construída sob este novo diretório.

#### [NEW] [pyproject.toml](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/pyproject.toml)
- Definição do pacote independente Python 3.12.
- Dependências enxutas: `pywebview`, `httpx`, `beautifulsoup4`, `lxml`, `pyinstaller`.

#### [NEW] [config.json](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/.planning/config.json)
- Configurações do GSD específicas para este subprojeto (YOLO mode, Balanced AI profile, auto-advance).

#### [NEW] [PROJECT.md](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/.planning/PROJECT.md)
- Contexto de valor e metas (69.44 POs/m, zero-browser, multiplataforma).

#### [NEW] [REQUIREMENTS.md](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/.planning/REQUIREMENTS.md)
- Requisitos funcionais (UI Web-Native pywebview, Sliders de Parâmetros, Engine Concorrente, DB SQLite de Resiliência, Cooldowns, Autoupdater, Build Standalone).

#### [NEW] [ROADMAP.md](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/.planning/ROADMAP.md)
- Fases de implementação:
  - Fase 1: Setup do ambiente `uv` e esqueleto estrutural.
  - Fase 2: Implementação do Banco SQLite e Engine de Continuidade.
  - Fase 3: Implementação do Core Async Crawler (Engine Turbo HTTP/2) e Benchmarker.
  - Fase 4: Implementação da Web UI Estática (HTML/CSS/JS) e Ponte de Comunicação IPC (`src/gui/api.py`).
  - Fase 5: Integração global, Edge Authenticator, Rate Limiting e Updater.
  - Fase 6: Automação de builds via PyInstaller e validação.

---

### UI & Styling System (pywebview Web UI)

#### [NEW] [index.html](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/gui/assets/index.html)
- Estrutura HTML5 premium com efeito Glassmorphic, dashboard de telemetria, controles deslizantes de rede, console de logs atrativo, área de **Drag-and-Drop** para planilhas e aba dedicada para **Histórico de Execuções**.

#### [NEW] [style.css](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/gui/assets/style.css)
- Tokens de design: Cores escuras HSL/RGB, efeitos de desfoque de fundo (`backdrop-filter`), transições e estilos responsivos.

#### [NEW] [script.js](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/gui/assets/script.js)
- Gestão de cliques, inicialização de benchmark, importação de planilhas via drag-and-drop, exibição do histórico de execuções anteriores e telemetria dinâmica via ponte IPC exposta sob `window.pywebview.api`.

#### [NEW] [api.py](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/gui/api.py)
- Mapeamento C#-like de funções Python expostas ao Javascript.

---

### Core Crawler & Scraper Engine

#### [NEW] [crawler.py](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/engine/crawler.py)
- Motor HTTP assíncrono usando `asyncio` e `httpx.AsyncClient` com semáforo concorrente (default `11` workers).
- Mecanismo de exportação de relatório Excel consolidado mesclando as informações da planilha importada original com os dados salvos de download.
- **Circuit Breaker de Company Codes (coluna `legal entity`)**: Monitora a taxa de erro de cada código de companhia em tempo real. A coluna que representa a companhia na planilha de entrada do usuário será lida diretamente sob o nome **`legal entity`** (sem necessidade de detecção ou dedução autônoma). Se $\ge 15\%$ das POs de uma companhia (com mínimo amostral de 3) forem processadas e o rate de erro for exatamente **100%**, suspende as POs restantes de tal companhia marcando-as como `SKIPPED_VERIFICATION_REQUIRED`.
- **Criação Tardia e Limpeza Segura (Clean Folders)**: Utiliza *Lazy Creation* (só cria a pasta física da PO no disco ao baixar o primeiro anexo com sucesso) e disparadores de limpeza automática (`shutil.rmtree`) que removem pastas vazias/órfãs em caso de falha de download da PO, garantindo que o diretório não tenha "lixo".

#### [NEW] [parser.py](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/engine/parser.py)
- Parser BeautifulSoup unificado. Busca em duas passagens para extrair links em elementos `<span>` modernizados com `data-url` e tags de âncora `<a>` tradicionais.

#### [NEW] [authenticator.py](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/engine/authenticator.py)
- Selenium Edge WebDriver temporário para extração automática de cookies de login.

#### [NEW] [benchmarker.py](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/engine/benchmarker.py)
- Testes concorrentes de ping e pacotes para calcular e sugerir parâmetros ideais baseados na rota local.

#### [NEW] [rate_limiter.py](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/engine/rate_limiter.py)
- Controle de tráfego: delays controlados (0.03s) e janelas de cooldown para lotes superiores a 500 POs.

#### [NEW] [updater.py](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/engine/updater.py)
- Validador de versão via GitHub API e script atômico de autoupdate de binário portátil.

---

### Persistence (SQLite)

#### [NEW] [session_db.py](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/src/db/session_db.py)
- Banco SQLite unificado para persistência de múltiplas execuções (tabelas `sessions` e `po_downloads`).
- Registra o status de cada PO vinculando-o à respectiva sessão e ao seu `company_code`.
- Registra status detalhado de cada PO (`PENDING`, `DOWNLOADING`, `COMPLETED`, `FAILED`, `SKIPPED_VERIFICATION_REQUIRED`), número de anexos identificados e baixados, erros detalhados e timestamps de início/fim das execuções do lote.
- Funções rápidas para carregar o histórico de execuções na UI, resetar status de companhias sinalizadas para reexecução (`PENDING`) e restaurar de forma resiliente qualquer lote interrompido no passado.

---

### Entrypoint & Packaging

#### [NEW] [main.py](file:///Users/juliocezar/Dev/ContractDownloader/src/main.py)
- Entrypoint principal do aplicativo executável.

#### [NEW] [build_standalone.py](file:///Users/juliocezar/Dev/CoupaPilot/ContractDownloader/build_standalone.py)
- Script Python para orquestrar o PyInstaller, incluindo a pasta de assets da Web UI (`src/gui/assets`) e gerando o executável final de arquivo único.

---

## Verification Plan

### Automated Tests
- Criaremos uma bateria de testes unitários isolados sob `ContractDownloader/tests/` usando `pytest` e `pytest-asyncio` para cobrir:
  - O parser de HTML híbrido (testando se encontra `data-url` e `href` em mocks HTML).
  - A escrita e atualização transacional do banco SQLite.
  - A integridade da ponte IPC (`AppAPI`).
  - **Algoritmo do Circuit Breaker**: Validar em testes unitários que a engine suspende o processamento de uma companhia ao atingir exatamente 100% de erro em 15% de progresso amostral.
  - **Criação de Pastas e Limpeza**: Testar se o diretório permanece totalmente limpo em caso de falha de download e se cria pastas apenas sob *Lazy Creation* bem-sucedida.

### Manual Verification
- **Execução Direta**: Rodar `uv run python -m src.main` para auditar a renderização gráfica, responsividade de sliders e logs locais na interface Web-Native.
- **Teste de Circuit Breaker**: Importar uma planilha contendo uma companhia propositalmente bloqueada no Coupa (gerando erros de acesso) para verificar a ativação do banner de alerta e a suspensão imediata do processamento das demais POs dessa companhia.
- **Teste de Retentativa**: Confirmar o acesso da companhia simulada, clicar em "Confirmar e Retentar" na UI e validar que a engine reprocessa todas as POs pendentes e falhas dela, gerando o output perfeito sem duplicados.
- **Validação de Limpeza**: Auditar a pasta física de downloads durante falhas de rede simuladas para garantir que nenhuma pasta física vazia ou sem anexos permaneça no diretório.
- **Teste de Build**: Gerar o binário via `build_standalone.py` e executá-lo em uma máquina limpa para garantir que a pasta de assets (`sys._MEIPASS`) extrai e lê corretamente sem dependências externas.
- **Resiliência**: Simular desconexão abrupta do cabo de rede no meio de um lote de downloads e reconectar para certificar que o SQLite retoma exatamente do ponto interrompido sem baixar novamente os itens já completados.
