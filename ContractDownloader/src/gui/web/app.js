function isDigitalManagementUnit(value) {
    const normalized = String(value || "")
        .trim()
        .toLowerCase()
        .replace(/\s*&\s*/g, " & ")
        .replace(/\s+/g, " ");
    return [
        "digital",
        "technology",
        "digital & technology",
        "digital and technology",
    ].includes(normalized);
}

document.addEventListener("DOMContentLoaded", () => {
    const $ = (selector) => document.querySelector(selector);
    const legacyPowerBIScreen = $("#screen-powerbi");
    const legacyTimesheetScreen = $("#screen-timesheet");
    const newRunPowerBIArea = $("#new-run-powerbi-source-area");
    const labPanels = {
        overview: $("#lab-panel-overview"),
        source: $("#lab-panel-source"),
        relationships: $("#lab-panel-relationships"),
        grir: $("#lab-panel-grir"),
        fx: $("#lab-panel-fx"),
        timesheet: $("#lab-panel-timesheet"),
    };
    const labPowerBISourceHost = $("#lab-powerbi-source-host");
    if (legacyPowerBIScreen) {
        [...legacyPowerBIScreen.children].forEach((child) => {
            const target = child.classList.contains("powerbi-grir-card")
                ? labPanels.grir
                : child.classList.contains("powerbi-fx-card") ? labPanels.fx : newRunPowerBIArea;
            target?.appendChild(child);
        });
    }
    if (legacyTimesheetScreen && labPanels.timesheet) {
        [...legacyTimesheetScreen.children].forEach((child) => labPanels.timesheet.appendChild(child));
    }
    const powerBISourceWorkspace = document.createElement("div");
    powerBISourceWorkspace.id = "powerbi-source-workspace";
    powerBISourceWorkspace.className = "powerbi-source-workspace";
    if (newRunPowerBIArea) {
        while (newRunPowerBIArea.firstChild) powerBISourceWorkspace.appendChild(newRunPowerBIArea.firstChild);
        newRunPowerBIArea.appendChild(powerBISourceWorkspace);
    }
    const mountPowerBISourceWorkspace = (host) => {
        if (host && powerBISourceWorkspace.parentElement !== host) host.appendChild(powerBISourceWorkspace);
    };
    mountPowerBISourceWorkspace(newRunPowerBIArea);
    const screens = { new: $("#screen-new"), lab: $("#screen-lab"), progress: $("#screen-progress"), history: $("#screen-history"), learn: $("#screen-learn"), settings: $("#screen-settings") };
    const navButtons = { new: $("#btn-new"), lab: $("#btn-lab"), progress: $("#btn-progress"), history: $("#btn-history"), learn: $("#btn-learn"), settings: $("#btn-settings") };
    const tableSortState = new WeakMap();

    function sortableNumber(value) {
        const normalized = String(value || "").trim().replace(/\s/g, "").replace(/[€$£%]/g, "");
        if (!/^-?[\d.,]+$/.test(normalized) || !/[\d]/.test(normalized)) return null;
        const lastComma = normalized.lastIndexOf(",");
        const lastDot = normalized.lastIndexOf(".");
        const canonical = lastComma > lastDot
            ? normalized.replace(/\./g, "").replace(",", ".")
            : normalized.replace(/,/g, "");
        const number = Number(canonical);
        return Number.isFinite(number) ? number : null;
    }

    function sortableValue(row, columnIndex, headerLabel) {
        const value = row.cells[columnIndex]?.textContent.trim() || "";
        const dateColumn = /date|started|updated|period|time/i.test(headerLabel);
        if (dateColumn) {
            const timestamp = Date.parse(value);
            if (Number.isFinite(timestamp)) return { kind: "number", value: timestamp };
        }
        const number = sortableNumber(value);
        return number === null ? { kind: "text", value: value.toLocaleLowerCase() } : { kind: "number", value: number };
    }

    function compareSortableRows(left, right, columnIndex, headerLabel) {
        const a = sortableValue(left, columnIndex, headerLabel);
        const b = sortableValue(right, columnIndex, headerLabel);
        if (a.value === "" && b.value !== "") return 1;
        if (a.value !== "" && b.value === "") return -1;
        if (a.kind === "number" && b.kind === "number") return a.value - b.value;
        return String(a.value).localeCompare(String(b.value), undefined, { numeric: true, sensitivity: "base" });
    }

    function groupedFxRows(table) {
        const groups = [];
        let current = null;
        [...table.tBodies[0].children].forEach((row) => {
            if (row.classList.contains("powerbi-fx-po-row")) {
                current = { rows: [row] };
                groups.push(current);
            } else if (current) current.rows.push(row);
            else groups.push({ rows: [row] });
        });
        return groups;
    }

    function sortTable(table, columnIndex) {
        const body = table.tBodies[0];
        if (!body) return;
        const header = table.tHead?.rows[0]?.cells[columnIndex];
        const headerLabel = header?.textContent.trim() || "";
        const previous = tableSortState.get(table) || {};
        const direction = previous.columnIndex === columnIndex && previous.direction === "asc" ? "desc" : "asc";
        const multiplier = direction === "asc" ? 1 : -1;
        const rows = [...body.children];
        if (rows.length < 2) return;
        if (body.id === "powerbi-fx-rows") {
            groupedFxRows(table).sort((left, right) => multiplier * compareSortableRows(
                left.rows.find((row) => row.cells[columnIndex]?.textContent.trim()) || left.rows[0],
                right.rows.find((row) => row.cells[columnIndex]?.textContent.trim()) || right.rows[0],
                columnIndex,
                headerLabel,
            )).forEach((group) => group.rows.forEach((row) => body.appendChild(row)));
        } else {
            rows.sort((left, right) => multiplier * compareSortableRows(left, right, columnIndex, headerLabel));
            rows.forEach((row) => body.appendChild(row));
        }
        tableSortState.set(table, { columnIndex, direction });
        table.tHead.rows[0].querySelectorAll("th").forEach((cell, index) => {
            cell.setAttribute("aria-sort", index === columnIndex ? (direction === "asc" ? "ascending" : "descending") : "none");
        });
    }

    function initializeSortableTables() {
        document.querySelectorAll("table").forEach((table) => {
            const headerCells = table.tHead?.rows[0]?.cells;
            if (!headerCells || !table.tBodies.length) return;
            [...headerCells].forEach((header, index) => {
                if (header.dataset.sortableBound === "1") return;
                const label = header.textContent.trim();
                if (!label || /^(actions?|retry)$/i.test(label)) {
                    header.classList.add("sortable-disabled");
                    return;
                }
                header.classList.add("sortable-header");
                header.setAttribute("role", "button");
                header.setAttribute("tabindex", "0");
                header.setAttribute("aria-sort", "none");
                const activate = () => sortTable(table, index);
                header.addEventListener("click", activate);
                header.addEventListener("keydown", (event) => {
                    if (event.key !== "Enter" && event.key !== " ") return;
                    event.preventDefault();
                    activate();
                });
                header.dataset.sortableBound = "1";
            });
        });
    }
    initializeSortableTables();

    let selectedFilePath = null;
    let generatedTemplatePath = null;
    let importedSessionId = null;
    let activePollInterval = null;
    let fileMonitorInterval = null;
    let validatedFingerprint = null;
    let selectedFileValidated = false;
    let hierarchyOrder = [];
    let disabledHierarchyColumns = [];
    let hierarchyColumnsLoaded = false;
    let mappingColumns = [];
    let mappingProbeToken = 0;
    let mappingDetected = null;
    let mappingSuggestions = { po: [], supplier: [] };
    let validationCopyValues = new Map();
    let validationCopyId = 0;
    let hierarchySorter = null;
    let runInProgress = false;
    let startRequestActive = false;
    let completionSessionId = null;
    let completionAlertKey = "";
    let completionStats = null;
    let pendingUpdate = null;
    let authInFlight = null;
    let appSettings = { download_root: "", concurrency: 11, retry_attempts: 1, msg_processing: "convert_extract", deduplicate_files: true, auto_updates: true, retention: "all", auth_browser: "auto", language: "en", font_scale: 1.1, python_portable: false, version: "unknown" };
    let journeyStep = 1;
    let journeyMaxStep = 1;
    let powerbiSupplierCache = [];
    let powerbiSearchResults = [];
    let powerbiSelectedSuppliers = new Map();
    let powerbiCheckedCandidates = new Set();
    let powerbiHierarchyPaths = [];
    let powerbiHierarchyUpdatedAt = null;
    let powerbiDateRange = { min_date: null, max_date: null, updated_at: null };
    let powerbiSelectedDatePeriods = new Set();
    let powerbiPathByKey = new Map();
    let powerbiSelectedPathKeys = new Set();
    let powerbiNodeMap = new Map();
    let powerbiExpandedNodeKeys = new Set();
    let powerbiFamilies = [];
    let powerbiFamilyHierarchy = [];
    let powerbiSelectedFamilies = new Set();
    let powerbiFamiliesLoaded = false;
    let powerbiFamilyColumn = null;
    let powerbiFamilyUpdatedAt = null;
    let powerbiPreviewRows = [];
    let powerbiExcludedPOs = new Set();
    let powerbiQueryCancelled = false;
    let powerbiQueryDiagnostics = null;
    let powerbiPoColumns = [];
    let powerbiPoColumnsUpdatedAt = null;
    let powerbiPoColumnsWarning = "";
    let powerbiSelectedColumns = new Set();
    let powerbiColumnDraft = new Set();
    let powerbiColumnSelectionLoaded = false;
    const POWERBI_SELECTED_COLUMNS_STORAGE_KEY = "contract-downloader.powerbi.selected-columns";
    let powerbiGrirRows = [];
    let powerbiGrirLoaded = false;
    let powerbiGrirFxRows = [];
    let powerbiGrirFxLoaded = false;
    let powerbiGrirFxExpanded = new Set();
    let powerbiScreenLoaded = false;
    let selectedInputMethod = null;
    let selectedInputSource = "file";
    let powerbiSourceMetadata = null;
    let timesheetAnalysis = null;
    let timesheetSelectedPath = "";
    let timesheetScreenLoaded = false;
    let labActiveSubtab = "overview";
    let labRelationshipData = null;
    let labRelationshipExpanded = new Set();
    let labRelationshipLoading = false;
    const journeyContent = {
        en: {
            1: ["Choose an input source", "Choose Power BI to build the PO list, or Excel for a specific fallback case."],
            2: ["Validate your input", "Check the file before configuring the download."],
            3: ["Arrange the folders", "Choose the save location and arrange the folder hierarchy."],
        },
        "pt-BR": {
            1: ["Escolha a fonte do input", "Use o Power BI para montar a lista de POs ou o Excel em um caso específico."],
            2: ["Valide o input", "Verifique o arquivo antes de configurar o download."],
            3: ["Organize as pastas", "Escolha o local e organize a hierarquia de pastas."],
        },
    };

    function getJourneyCopy(step) {
        const numericStep = Number(step);
        const languageCopy = journeyContent[appSettings.language] || journeyContent.en;
        return languageCopy[numericStep] || journeyContent.en[numericStep] || journeyContent.en[1];
    }

    const api = () => window.pywebview && window.pywebview.api ? window.pywebview.api : null;
    const hasApi = (name) => Boolean(api() && typeof api()[name] === "function");

    function setButtonBusy(button, busy) {
        if (!button) return;
        button.classList.toggle("is-busy", Boolean(busy));
        button.dataset.busy = busy ? "1" : "0";
        button.setAttribute("aria-busy", busy ? "true" : "false");
    }

    // Immediate pressed feedback covers synchronous actions; async handlers
    // keep the busy state until their existing promise finishes.
    document.addEventListener("click", (event) => {
        const button = event.target.closest?.("button");
        if (!button || button.disabled) return;
        if (button.dataset.busy === "1") {
            event.preventDefault();
            event.stopImmediatePropagation();
            return;
        }
        button.classList.add("is-pressed");
        window.setTimeout(() => button.classList.remove("is-pressed"), 180);
    }, true);

    function syncUpdateButton() {
        const button = $("#btn-download-update");
        if (!button) return;
        button.disabled = runInProgress || !pendingUpdate;
        button.title = runInProgress ? "Updates are disabled while a run is executing." : "Download and install update";
    }

    function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
        }[char]));
    }

    const uiCopy = {
        en: { newRun: "New run", activeRun: "Active run", history: "Run history", learn: "Learn", settings: "Settings", prepare: "Prepare a new run", validate: "Validate input", createTemplate: "Create template", chooseFile: "Choose input file", openInput: "Open", continueValidation: "Continue to validation", continueFolders: "Continue to folders", start: "Start download", back: "Back", chooseFolder: "Choose folder", saveSettings: "Save settings", resetDefaults: "Reset defaults", openReport: "Open Excel report", openFolder: "Open download folder" },
        "pt-BR": { newRun: "Nova execução", activeRun: "Execução ativa", history: "Histórico", learn: "Aprenda", settings: "Configurações", prepare: "Prepare uma nova execução", validate: "Validar input", createTemplate: "Criar template", chooseFile: "Escolher arquivo de input", openInput: "Abrir", continueValidation: "Continuar para validação", continueFolders: "Continuar para pastas", start: "Iniciar download", back: "Voltar", chooseFolder: "Escolher pasta", saveSettings: "Salvar configurações", resetDefaults: "Restaurar padrões", openReport: "Abrir relatório Excel", openFolder: "Abrir pasta de download" },
    };

    function t(key, fallback = key) {
        return (uiCopy[appSettings.language] || uiCopy.en)[key] || fallback;
    }

    function applyFontScale(value = appSettings.font_scale) {
        const scale = Math.max(1, Math.min(1.3, Number(value) || 1.1));
        appSettings.font_scale = scale;
        document.documentElement.style.setProperty("--font-scale", String(scale));
    }

    function updateSidebarVersion() {
        const label = $("#sidebar-version");
        if (!label) return;
        const version = String(appSettings.version || "unknown").replace(/^v/i, "");
        label.innerText = `${appSettings.language === "pt-BR" ? "Versão" : "Version"} ${version}`;
    }

    function applyLanguage() {
        const selectors = { "#btn-new .nav-label": "newRun", "#btn-progress .nav-label": "activeRun", "#btn-history .nav-label": "history", "#btn-learn .nav-label": "learn", "#btn-settings .nav-label": "settings", "#btn-download-template": "createTemplate", "#btn-browse": "chooseFile", "#btn-open-selected-input": "openInput", "#btn-next-input": "continueValidation", "#btn-next-hierarchy": "continueFolders", "#btn-start-run": "start", "#btn-start-over": "startOver", "#btn-validate-file": "validate", "#btn-choose-dir": "chooseFolder", "#btn-save-settings": "saveSettings", "#btn-reset-settings": "resetDefaults", "#btn-open-complete-report": "openReport", "#btn-open-complete-folder": "openFolder" };
        Object.entries(selectors).forEach(([selector, key]) => { const element = $(selector); if (element) element.innerText = t(key); });
        const content = getJourneyCopy(journeyStep);
        $("#journey-title").innerText = content[0];
        $("#journey-subtitle").innerText = content[1];
        document.querySelectorAll("[data-journey-step] span").forEach((element, index) => { element.innerText = (appSettings.language === "pt-BR" ? ["Input", "Validar", "Pastas"] : ["Input", "Validate", "Folders"])[index]; });
        document.querySelectorAll(".learn-card h3").forEach((element, index) => { element.innerText = (appSettings.language === "pt-BR" ? ["Prepare o input", "Siga a jornada", "O que acontece durante uma execução?", "Erros e retries", "Histórico e relatórios", "Autenticação e privacidade"] : ["Prepare the input", "Follow the journey", "What happens during a run?", "Errors and retries", "History and reports", "Authentication and privacy"])[index]; });
        const learnParagraphs = appSettings.language === "pt-BR" ? ["Use um arquivo Excel ou CSV com PO_NUMBER e SUPPLIER. O template inclui o separador <|>. Salve e feche o Excel antes de validar.", "A jornada possui três etapas: input, validação e configuração final das pastas. O download só começa após a aprovação da árvore exibida.", "O app usa requisições HTTP autenticadas para o Coupa, lê páginas de PO e PR, encontra anexos e os salva na pasta da execução.", "Abra Active Run para acompanhar o progresso e os logs. Retries automáticos podem ser configurados em Settings, e POs com erro também podem ser refeitos pelo histórico.", "O histórico armazena resultados por PO, retries, inputs preservados, relatórios e links para o Coupa. É possível excluir uma execução ou todo o histórico.", "A autenticação reutiliza o perfil corporativo existente do Microsoft Edge. Na primeira captura, feche todas as janelas do Edge quando solicitado; depois o app guarda a sessão no armazenamento seguro nativo e processa os documentos por HTTP."] : ["Use an Excel or CSV file with PO_NUMBER and SUPPLIER. The template includes the <|> separator. Save and close Excel before validating.", "The journey has three stages: input, validation, and final folder setup. The download starts only after you approve the visible folder tree.", "The app uses authenticated HTTP requests to Coupa, reads PO and PR pages, discovers attachments, and saves them inside the run folder.", "Open Active Run to monitor progress and logs. Automatic retries can be configured in Settings, and failed POs can also be retried manually from History.", "History stores PO-level results, retry history, preserved inputs, reports, and Coupa links. You can delete one run or clear all history.", "Authentication reuses the existing Microsoft Edge work profile. During the first capture, close all Edge windows when asked; the app then keeps the session in native secure storage and processes documents over HTTP."];
        document.querySelectorAll(".learn-card p").forEach((element, index) => { element.innerText = learnParagraphs[index]; });
        const learnNotes = appSettings.language === "pt-BR" ? ["Colunas após <|> viram níveis de pasta. Campos obrigatórios vazios são informados antes do download.", "Etapas concluídas continuam disponíveis; etapas futuras explicam o que ainda falta.", "O motor oficial usa 11 downloads HTTP concorrentes, com backoff adaptativo quando o Coupa aplica rate limit.", "O retry usa a mesma pasta e preserva arquivos válidos existentes.", "Excluir uma execução remove sua pasta; inputs originais fora dela são preservados.", "Não há telemetria. Cookies, credenciais e documentos permanecem na máquina local."] : ["Columns after <|> become folder levels. Blank required fields are reported before downloading.", "Completed steps remain available; future steps explain what is still missing.", "The official engine uses 11 concurrent HTTP downloads, with adaptive backoff when Coupa rate-limits requests.", "A retry uses the same folder and preserves valid files.", "Deleting a run removes its folder; original inputs outside it are preserved.", "No telemetry is sent. Cookies, credentials, and documents remain on the local machine."];
        document.querySelectorAll(".learn-note").forEach((element, index) => { element.innerText = learnNotes[index]; });
        const settingsHeadings = appSettings.language === "pt-BR" ? ["Idioma", "Tamanho do texto", "Downloads", "Downloads simultâneos", "Política de retry", "Arquivos de e-mail (.msg)", "Arquivos duplicados", "Atualizações", "Navegador do Contract Downloader", "Login do Coupa", "Começar limpo", "Retenção do histórico"] : ["Language", "Text size", "Downloads", "Downloads simultaneous", "Retry policy", "Email files (.msg)", "Duplicate files", "Updates", "Contract Downloader browser", "Coupa sign-in", "Start clean", "History retention"];
        document.querySelectorAll(".settings-section h3").forEach((element, index) => { element.innerText = settingsHeadings[index]; });
        const panelHeadings = appSettings.language === "pt-BR" ? ["Escolha a fonte do input", "Valide o input", "Organize as pastas", "Revise e inicie a execução"] : ["Choose an input source", "Validate your input", "Arrange the folders", "Review and start the run"];
        document.querySelectorAll("[data-journey-panel] > article > .card-heading:not(.destination-heading) h3").forEach((element, index) => { element.innerText = panelHeadings[index]; });
        const settingsDescriptions = appSettings.language === "pt-BR" ? ["Altera o idioma da interface. A saída do CLI e os logs permanecem em inglês.", "Ajusta a escala da interface para facilitar a leitura. A prévia é aplicada imediatamente e salva neste computador.", "Escolha a pasta base. Cada execução recebe uma subpasta com timestamp.", "Quantos POs o app processa ao mesmo tempo. O motor HTTP oficial permite até 11 workers.", "Tentativas automáticas para um PO antes de marcá-lo como erro. O retry manual continua disponível no histórico.", "Escolha se arquivos de e-mail baixados são convertidos para PDF e se seus anexos são extraídos.", "Compara arquivos com SHA-256. Arquivos idênticos usam hard link quando possível ou um arquivo de referência.", "A verificação ao iniciar é opcional. Você sempre pode verificar, baixar, validar e instalar uma atualização manualmente.", "O login oficial reutiliza o perfil corporativo existente do Microsoft Edge; o navegador só é aberto após ação explícita.", "O app detecta o perfil com @unilever.com, captura a sessão e fecha somente o WebDriver criado; perfis pessoais não são modificados.", "Esquece o histórico local e o login, preservando arquivos baixados, relatórios e inputs.", "A limpeza automática só se aplica a execuções concluídas e nunca remove uma execução ativa."] : ["Changes the application interface language. CLI output and logs remain in English.", "Adjusts the interface scale for readability. The preview is applied immediately and saved on this computer.", "Choose the base folder. Each run receives its own timestamped subfolder.", "How many POs the app processes at the same time. The official HTTP engine supports up to 11 workers.", "Automatic attempts for a PO before marking it as failed. Manual retry remains available from History.", "Choose whether downloaded email files are converted to PDF and whether their attachments are extracted.", "Compare files with SHA-256. Identical files use a hard link when possible or a reference sidecar.", "Startup checks are optional. You can always check, download, verify, and install an update manually.", "The official sign-in reuses the existing Microsoft Edge work profile; the browser opens only after an explicit action.", "The app detects the profile containing @unilever.com, captures the session, and closes only the WebDriver it created; personal profiles are not modified.", "Forget local run history and sign-in state while preserving downloaded files, reports, and original inputs.", "Automatic cleanup only applies to completed runs and never removes an active run."];
        document.querySelectorAll(".settings-section > div:first-child p").forEach((element, index) => { element.innerText = settingsDescriptions[index]; });
        const setMany = (selector, values) => document.querySelectorAll(selector).forEach((element, index) => { if (values[index] !== undefined) element.innerText = values[index]; });
        const pt = appSettings.language === "pt-BR";
        setMany("[data-settings-tab]", pt ? ["Geral", "Downloads", "Atualizações", "Autenticação", "Dados e histórico"] : ["General", "Downloads", "Updates", "Authentication", "Data & history"]);
        if (hierarchyOrder.length) renderHierarchy();
        setMany("#screen-new .template-actions strong", [pt ? "Começando do zero?" : "Starting from scratch?"]);
        setMany("#screen-new .template-actions span", [pt ? "Crie o template Excel, preencha, salve e feche o arquivo." : "Create the Excel template, fill it in, then save and close it."]);
        setMany("#screen-new .choice-divider span", [pt ? "OU" : "OR"]);
        setMany("#screen-new .dropzone h3", [pt ? "Arraste o arquivo preenchido aqui" : "Drop your completed file here"]);
        setMany("#screen-new .dropzone p", [pt ? "Excel ou CSV · o arquivo original será preservado" : "Excel or CSV · the original file is preserved"]);
        setMany("#screen-new .journey-hint", [pt ? "O próximo passo verifica se todas as colunas obrigatórias existem." : "The next step checks that all required columns are present."]);
        setMany("#btn-start-over", [pt ? "Começar de novo" : "Start over"]);
        setMany("[data-journey-panel] > article > .card-heading p", pt ? ["Escolha como a lista de POs será criada. Power BI é o método recomendado; Excel fica disponível para casos específicos.", "Revise o arquivo antes de qualquer execução. Corrija o mesmo arquivo se necessário.", "Escolha o local e organize a hierarquia de pastas."] : ["Choose how the PO list will be created. Power BI is recommended; Excel remains available for specific cases.", "Review the file before any run is created. Correct it in the same file if needed.", "Choose the save location and arrange the folder hierarchy."]);
        setMany("[data-journey-panel] .journey-folder-guide small", [pt ? "Colunas após <|> viram pastas. Valores vazios viram Unknown." : "Columns after <|> become folders. Empty values become Unknown."]);
        setMany("[data-journey-panel='3'] .field-label", [pt ? "Pasta de download" : "Download folder"]);
        setMany("[data-journey-panel='3'] .destination-note span:last-child", [pt ? "Arquivos válidos existentes são preservados durante retries." : "Existing valid files are preserved during retries."]);
        setMany("#folder-preview-title, #folder-preview-description, #folder-approval-label", pt ? ["Estrutura final de pastas", "Esta é a árvore que será criada.", "Aprovo esta estrutura final de pastas e o local de salvamento."] : ["Final folder structure", "This is the folder tree that will be created.", "I approve this final folder structure and save location."]);
        setMany("#screen-progress .metric-card > span", pt ? ["Progresso", "Velocidade", "ETA", "Erros"] : ["Progress", "Speed", "ETA", "Errors"]);
        setMany("#screen-progress .section-header h3", [pt ? "Log de execução" : "Execution log"]);
        setMany("#screen-progress .section-header p", [pt ? "Progresso e eventos importantes de autenticação, alertas, erros e relatório." : "Key progress, authentication, warning, error, and report events."]);
        setMany("#speed-note, #eta-note", pt ? ["POs concluídas recentemente", "Atualizado pela velocidade recente"] : ["Recent completed POs", "Updates with recent speed"]);
        setMany("#btn-back-new, #btn-pause-resume, #btn-stop-session, #btn-clear-log", pt ? ["Nova execução", "Pausar", "Parar execução", "Limpar"] : ["New run", "Pause", "Stop run", "Clear"]);
        setMany("#screen-history .intro-block .eyebrow, #screen-history .intro-block h2", pt ? ["TRILHA DE AUDITORIA", "Histórico de execuções"] : ["AUDIT TRAIL", "Run history"]);
        setMany("#active-run-banner strong", [pt ? "Uma baixa já está em andamento." : "A download is already running."]);
        setMany("#active-run-banner span", [pt ? "Volte para Execução ativa para acompanhar." : "Return to Active run to monitor it."]);
        setMany("#btn-go-active-run", [pt ? "Ver execução ativa" : "View active run"]);
        setMany("#mapping-title, #mapping-subtitle", pt ? ["Mapeie as colunas do arquivo", "As colunas obrigatórias não foram encontradas automaticamente. Informe quais colunas contêm o número da PO e o fornecedor."] : ["Map the file columns", "The required columns were not found automatically. Tell the app which columns hold the PO number and the supplier."]);
        setMany("#btn-map-columns", [pt ? "Mapear colunas" : "Map columns"]);
        setMany("#mapping-notice-title", [pt ? "Este arquivo não tem as colunas padrão." : "This file does not have the standard columns."]);
        setMany("#mapping-notice-text", [pt ? "Mapeie as colunas de PO e fornecedor para continuar." : "Map the PO and supplier columns to continue."]);
        setMany("#btn-apply-mapping", [pt ? "Aplicar mapeamento e validar" : "Apply mapping and validate"]);
        setMany("#column-mapping-card .mapping-fields label span", pt ? ["Coluna de número da PO", "Coluna de fornecedor"] : ["PO number column", "Supplier column"]);
        setMany("#hierarchy-disabled h4", [pt ? "Colunas desativadas" : "Disabled columns"]);
        setMany("#hierarchy-disabled p", [pt ? "Estas colunas permanecem no input e no relatório final, mas não criam pastas." : "These columns stay in the input and in the final report, but do not create folders."]);
        setMany("#run-description-input", [pt ? "Por que esta execução foi feita? Para quem?" : "Why was this run made? For whom?"]);
        setMany("#btn-save-run-description", [pt ? "Salvar" : "Save"]);
        setMany(".description-hint", [pt ? "Texto livre que aparece no histórico para explicar o objetivo da execução (solicitação, análise, solicitante)." : "Free text shown in history to explain this run's purpose (request, analysis, requester)."]);
        setMany("#screen-history .intro-block p:not(.eyebrow)", [pt ? "Revise resultados, erros por PO e relatórios." : "Review results, inspect PO-level errors, and export reports."]);
        setMany("#btn-refresh-history, #btn-clear-history", pt ? ["Atualizar", "Excluir todo o histórico"] : ["Refresh", "Delete all history"]);
        setMany("#history-list ~ *", []);
        setMany(".history-header-label", pt ? ["Execução", "Início", "Resultado", "Ações"] : ["Run", "Started", "Result", "Actions"]);
        updateHistoryTimezoneLabel();
        setMany("#screen-learn .intro-block .eyebrow", [pt ? "APRENDA" : "LEARN"]);
        setMany("#screen-learn .intro-block p:not(.eyebrow)", [pt ? "Guia prático para preparar inputs, baixar anexos e recuperar erros com segurança." : "A practical guide to prepare inputs, download attachments, and recover safely from errors."]);
        setMany("#screen-settings .intro-block .eyebrow", [pt ? "CONFIGURAÇÕES" : "SETTINGS"]);
        setMany("#screen-settings .intro-block p:not(.eyebrow)", [pt ? "Controle downloads, retries, atualizações e o tempo de permanência no histórico." : "Control downloads, retries, updates, and how long runs remain in history."]);
        setMany("#settings-auth-browser-section h3", [pt ? "Navegador do Contract Downloader" : "Contract Downloader browser"]);
        setMany("#settings-auth-browser-section p", [pt ? "O login oficial reutiliza o perfil corporativo existente do Microsoft Edge. Feche todas as janelas do Edge somente quando o app solicitar." : "The official sign-in reuses your existing Microsoft Edge work profile. Close all Edge windows only when the app asks."]);
        setMany("#btn-check-updates", [pt ? "Verificar agora" : "Check now"]);
        setMany("#btn-reset-auth", [pt ? "Zerar estado do login" : "Reset sign-in state"]);
        setMany("#btn-reset-application", [pt ? "Zerar estado local" : "Reset local state"]);
        setMany("#settings-language option", pt ? ["English (padrão)", "Português (Brasil)"] : ["English (default)", "Português (Brasil)"]);
        setMany("#settings-font-scale option", pt ? ["Padrão — 100%", "Confortável — 110%", "Grande — 120%", "Extra grande — 130%"] : ["Standard — 100%", "Comfortable — 110%", "Large — 120%", "Extra large — 130%"]);
        setMany("#settings-concurrency option",  pt ? ["Conservador — 2 downloads", "Balanceado — 4 downloads", "Rápido — 6 downloads", "Oficial — 11 downloads"] : ["Conservative — 2 downloads", "Balanced — 4 downloads", "Fast — 6 downloads", "Official — 11 downloads"]);
        setMany("#settings-retry option", pt ? ["Sem retry automático", "Tentar novamente uma vez", "Tentar novamente duas vezes"] : ["No automatic retry", "Retry once", "Retry twice"]);
        setMany("#settings-retention option", pt ? ["Tudo", "Últimas 10 execuções", "Últimas 30 execuções", "Execuções dos últimos 90 dias"] : ["Everything", "Last 10 runs", "Last 30 runs", "Runs from the last 90 days"]);
        setMany("#settings-msg-processing option", pt ? ["Desabilitado", "Converter para PDF", "Converter para PDF e extrair anexos"] : ["Disabled", "Convert to PDF", "Convert to PDF and extract attachments"]);
        setMany("#settings-auth-browser option", pt ? ["Automático", "Microsoft Edge", "Google Chrome"] : ["Automatic", "Microsoft Edge", "Google Chrome"]);
        syncAuthBrowserOptions();
        setMany("#settings-field-does-not-exist", []);
        setMany("#screen-settings .settings-field label", pt ? ["Idioma da interface", "Tamanho do texto da interface", "Pasta padrão de download", "Perfil de velocidade", "Retry automático", "Processamento automático", "Navegador do Contract Downloader", "Manter"] : ["Interface language", "Interface text size", "Default download folder", "Speed profile", "Automatic retry", "Automatic processing", "Contract Downloader browser", "Keep"]);
        setMany("#details-modal .modal-header .eyebrow, #modal-title", pt ? ["DETALHES DA EXECUÇÃO", "Detalhes da sessão"] : ["RUN DETAILS", "Session details"]);
        setMany("#retry-history-list h4, .company-status-list h4, .po-details-list h4", pt ? ["Histórico de retries", "Resumo da execução", "Pedidos de compra"] : ["Retry history", "Run summary", "Purchase orders"]);
        setMany("#status-filter legend, #status-filter label span", pt ? ["Exibir status", "Todos", "Sucesso", "Erro", "Pendente", "Ignorado"] : ["Show statuses", "All", "Success", "Error", "Pending", "Skipped"]);
        setMany(".modal-pos-table th", pt ? ["PO", "Fornecedor", "Status", "Retry", "Mensagem"] : ["PO", "Supplier", "Status", "Retry", "Message"]);
        setMany("#btn-retry-errors, #btn-export-modal-report", pt ? ["Refazer POs com erro", "Exportar relatório"] : ["Retry failed POs", "Export report"]);
        setMany("#diagnostics-modal .modal-header .eyebrow, #diagnostics-modal .modal-header h3, #btn-save-diagnostics, #btn-copy-diagnostics", pt ? ["FERRAMENTA DE SUPORTE", "Diagnóstico do computador", "Salvar relatório", "Copiar relatório"] : ["SUPPORT TOOL", "Host diagnostics", "Save report", "Copy report"]);
        setMany(".toggle-field span", pt ? ["Identificar arquivos idênticos", "Verificar automaticamente"] : ["Identify identical files", "Check automatically"]);
        setMany("#settings-status", [pt ? "As alterações são salvas localmente neste computador." : "Changes are saved locally on this computer."]);
        setMany("#sidebar-does-not-exist", []);
        if (completionStats) showRunCompletion(completionStats);
        setMany("#btn-diagnostics .nav-label", [pt ? "Executar diagnóstico do computador" : "Run host diagnostics"]);
        const currentAuthState = $("#btn-authenticate")?.dataset.authState;
        if (currentAuthState) updateAuthUI(currentAuthState, $("#auth-detail")?.innerText);
        else setMany("#auth-context", [pt ? "ACESSO COUPA" : "COUPA ACCESS"]);
        if (!currentAuthState) setMany(".auth-action", [pt ? "Entrar" : "Sign in"]);
        syncJourneyNavAction(journeyStep, journeyStep > journeyMaxStep);
        $("#screen-learn h2").innerText = appSettings.language === "pt-BR" ? "Como o Contract Downloader funciona" : "How Contract Downloader works";
        $("#screen-settings h2").innerText = appSettings.language === "pt-BR" ? "Preferências" : "Preferences";
        const languageOption = $("#settings-language option[value='pt-BR']");
        if (languageOption) languageOption.innerText = "Português (Brasil)";
        const msgOptions = $("#settings-msg-processing").options;
        if (msgOptions) { msgOptions[0].innerText = appSettings.language === "pt-BR" ? "Desabilitado" : "Disabled"; msgOptions[1].innerText = appSettings.language === "pt-BR" ? "Converter para PDF" : "Convert to PDF"; msgOptions[2].innerText = appSettings.language === "pt-BR" ? "Converter para PDF e extrair anexos" : "Convert to PDF and extract attachments"; }
        updateSidebarVersion();
    }

    function journeyRequirement(step) {
        const requirements = appSettings.language === "pt-BR" ? {
            2: "Selecione e salve um arquivo de input primeiro.",
            3: "Valide o input com sucesso antes de organizar as pastas.",
        } : {
            2: "Select and save an input file first.",
            3: "Validate the input successfully before arranging folders.",
        };
        return requirements[step] || (appSettings.language === "pt-BR" ? "Conclua o passo anterior primeiro." : "Complete the previous step first.");
    }

    function journeyPendingMessage(step) {
        const pt = appSettings.language === "pt-BR";
        if (Number(step) === 1) {
            if (!selectedInputMethod) return pt ? "Selecione Power BI ou Excel para continuar." : "Choose Power BI or Excel to continue.";
            if (selectedInputMethod === "powerbi") {
                if (!powerbiSelectedSuppliers.size) return pt ? "Pendente: selecione pelo menos um supplier no Power BI." : "Pending: select at least one Power BI supplier.";
                if (!groupedPowerBIPreviewRows().length) return pt ? "Pendente: clique em Fetch Data e revise os POs encontrados." : "Pending: click Fetch Data and review the matching POs.";
            } else if (!selectedFilePath) {
                return pt ? "Pendente: crie um template novo ou escolha um arquivo Excel/CSV." : "Pending: create a new template or choose an Excel/CSV file.";
            }
            return pt ? "Conclua os dados pendentes antes de continuar." : "Complete the pending input details before continuing.";
        }
        if (Number(step) === 2) {
            if (!selectedFilePath) return pt ? "Pendente: selecione um arquivo de input." : "Pending: select an input file.";
            if (!selectedFileValidated) return pt ? "Pendente: valide o input e corrija os erros indicados." : "Pending: validate the input and fix the reported errors.";
        }
        if (Number(step) === 3) {
            if (!hierarchyColumnsLoaded) return pt ? "Pendente: valide o input para carregar a hierarquia de pastas." : "Pending: validate the input to load the folder hierarchy.";
            if (!$("#download-dir")?.value.trim()) return pt ? "Pendente: escolha a pasta de destino." : "Pending: choose a download destination.";
            if (!$("#folder-approval")?.checked) return pt ? "Pendente: aprove a estrutura final de pastas." : "Pending: approve the final folder structure.";
        }
        return journeyRequirement(step);
    }

    function showJourneyPendingDialog(step) {
        window.alert(journeyPendingMessage(step));
    }

    const journeyActionByStep = {
        1: "btn-next-input",
        2: "btn-next-hierarchy",
        3: "btn-start-run",
    };

    function syncJourneyNavAction(step, locked) {
        const action = $("#journey-nav-action");
        const actionStep = Number(step);
        const source = document.getElementById(journeyActionByStep[actionStep] || "");
        if (!action || !source) return;
        const proxy = source.cloneNode(true);
        proxy.id = "journey-top-action";
        proxy.classList.add("journey-nav-button");
        proxy.hidden = false;
        proxy.disabled = Boolean(locked);
        proxy.addEventListener("click", () => {
            if (locked || source.disabled) {
                showJourneyPendingDialog(actionStep);
                return;
            }
            proxy.disabled = true;
            source.click();
        });
        action.replaceChildren(proxy);
    }

    function hasJourneyState() {
        return Boolean(
            selectedFilePath
            || generatedTemplatePath
            || powerbiSelectedSuppliers.size
            || powerbiSelectedPathKeys.size
            || powerbiSelectedDatePeriods.size
            || powerbiSelectedFamilies.size
            || powerbiPreviewRows.length
            || journeyMaxStep > 1
        );
    }

    function syncStartOverAction() {
        const button = $("#btn-start-over");
        if (!button) return;
        button.hidden = !hasJourneyState();
        button.disabled = runInProgress;
        button.title = runInProgress
            ? (appSettings.language === "pt-BR" ? "Disponível após a execução terminar" : "Available after the run finishes")
            : (appSettings.language === "pt-BR" ? "Limpar esta preparação e voltar ao início" : "Clear this preparation and return to the beginning");
    }

    function showJourneyStep(step) {
        const target = Number(step);
        if (target < 1 || target > 3) return;
        const locked = target > journeyMaxStep;
        journeyStep = target;
        document.querySelectorAll("[data-journey-panel]").forEach((panel) => {
            const active = Number(panel.dataset.journeyPanel) === target;
            panel.hidden = !active;
            panel.classList.toggle("active", active);
            panel.classList.toggle("locked", active && locked);
            if (active) {
                panel.querySelectorAll("button:not([data-journey-back])").forEach((button) => {
                    if (locked) {
                        button.disabled = true;
                        button.dataset.journeyLocked = "true";
                    } else if (button.dataset.journeyLocked) {
                        button.disabled = false;
                        delete button.dataset.journeyLocked;
                    }
                });
                panel.querySelectorAll("input, select").forEach((field) => { field.disabled = locked; });
            }
        });
        document.querySelectorAll("[data-journey-step]").forEach((button) => {
            const value = Number(button.dataset.journeyStep);
            button.classList.toggle("active", value === target);
            button.classList.toggle("completed", value < journeyMaxStep);
            button.classList.toggle("locked", value > journeyMaxStep);
            button.disabled = false;
            button.title = value > journeyMaxStep ? journeyRequirement(value) : `Go to ${getJourneyCopy(value)[0]}`;
        });
        const content = getJourneyCopy(target);
        if (content) {
            $("#journey-title").innerText = locked ? (appSettings.language === "pt-BR" ? `Etapa ${target} bloqueada` : `Step ${target} is locked`) : content[0];
            $("#journey-subtitle").innerText = locked ? journeyRequirement(target) : content[1];
            $("#journey-subtitle").classList.toggle("journey-subtitle-warning", locked);
        }
        const lockMessage = $("#journey-lock-message");
        lockMessage.hidden = true;
        lockMessage.innerText = "";
        if (hierarchySorter) hierarchySorter.setDisabled(target !== 3 || locked);
        if (target === 2 && selectedFilePath) $("#validation-filename").innerText = $("#selected-filename").innerText;
        if (target === 3 && !locked) { renderDestinationPreview(); ensureDefaultDestination(); syncStepThreeAction(); }
        syncJourneyNavAction(target, locked);
        syncStartOverAction();
    }

    function completeJourneyStep(nextStep) {
        journeyMaxStep = Math.max(journeyMaxStep, Number(nextStep));
        showJourneyStep(nextStep);
    }

    function updateInputMethodUI() {
        const powerbiSelected = selectedInputMethod === "powerbi";
        const excelSelected = selectedInputMethod === "excel";
        const powerbiPanel = $("#powerbi-input-method-panel");
        const excelPanel = $("#excel-input-method-panel");
        const footer = $("#input-method-footer");
        const nextButton = $("#btn-next-input");
        const hint = $("#input-method-hint");
        if (powerbiPanel) powerbiPanel.hidden = !powerbiSelected;
        if (excelPanel) excelPanel.hidden = !excelSelected;
        if (footer) footer.hidden = !selectedInputMethod;
        document.querySelectorAll("[data-input-method]").forEach((choice) => {
            const active = choice.dataset.inputMethod === selectedInputMethod;
            choice.classList.toggle("selected", active);
            choice.setAttribute("aria-pressed", active ? "true" : "false");
        });
        if (!nextButton || !hint) return;
        if (powerbiSelected) {
            const ready = groupedPowerBIPreviewRows().length > 0;
            nextButton.disabled = !ready;
            hint.innerText = ready
                ? "Review the selected POs, then continue to validation."
                : "Choose the filters and click Fetch Data to load the PO list.";
        } else if (excelSelected) {
            if (!selectedFilePath) nextButton.disabled = true;
            hint.innerText = selectedFilePath
                ? "The next step checks that all required columns are present."
                : "Create a template or choose a completed Excel/CSV file to continue.";
        } else {
            nextButton.disabled = true;
            hint.innerText = "Choose Power BI or Excel to continue.";
        }
        if (journeyStep === 1) syncJourneyNavAction(1, false);
        syncStartOverAction();
    }

    function selectInputMethod(method) {
        if (!["powerbi", "excel"].includes(method)) return;
        const switchingSource = selectedInputMethod && selectedInputMethod !== method;
        const powerBIStateMustBeDiscarded = method === "excel" && (
            selectedInputSource === "powerbi" || powerbiPreviewRows.length || powerbiSourceMetadata
        );
        const excelStateMustBeDiscarded = method === "powerbi" && selectedInputSource === "file" && selectedFilePath;
        if (switchingSource || powerBIStateMustBeDiscarded || excelStateMustBeDiscarded) clearFile();
        selectedInputMethod = method;
        selectedInputSource = method === "powerbi" ? "powerbi" : "file";
        updateInputMethodUI();
        syncStartOverAction();
        if (method === "powerbi") {
            setPowerBIMessage("Choose filters and fetch the PO list.");
        }
    }

    function setPowerBIMessage(message, tone = "") {
        const target = $("#powerbi-status-message");
        if (!target) return;
        target.innerText = message || "";
        target.className = `powerbi-status-message ${tone}`;
    }

    function setPowerBIConnectionStatus(state, message) {
        const target = $("#powerbi-connection-status");
        if (!target) return;
        const text = String(message || "Power BI session status unknown.");
        const needsSignIn = state === "expired" || state === "unauthenticated" || /sign in|login required|authenticate/i.test(text);
        const dot = target.querySelector(".status-dot");
        if (dot) dot.className = `status-dot ${state || "authenticating"}`;
        const label = target.querySelector("span:last-child");
        if (label) label.innerText = needsSignIn ? "Sign in to Power BI" : text;
        target.disabled = !needsSignIn;
        target.classList.toggle("is-sign-in", needsSignIn);
        target.title = needsSignIn ? "Sign in to Power BI" : text;
    }

    function renderPowerBIFilterLabels() {
        const supplierLabel = $("#powerbi-supplier-filter-label");
        const managementUnitLabel = $("#powerbi-management-unit-filter-label");
        const dateLabel = $("#powerbi-date-filter-label");
        const familyLabel = $("#powerbi-family-filter-label");
        if (supplierLabel) supplierLabel.innerText = powerbiSelectedSuppliers.size ? `${powerbiSelectedSuppliers.size} selected` : "Select suppliers";
        if (managementUnitLabel) managementUnitLabel.innerText = powerbiSelectedPathKeys.size ? `${powerbiSelectedPathKeys.size} selected path(s)` : "All Management Units";
        if (familyLabel) familyLabel.innerText = powerbiSelectedFamilies.size ? `${powerbiSelectedFamilies.size} selected` : "All families";
        const months = powerBIMonthsInRange(powerbiDateRange.min_date, powerbiDateRange.max_date);
        if (dateLabel) dateLabel.innerText = !powerbiSelectedDatePeriods.size || (months.length && powerbiSelectedDatePeriods.size === months.length)
            ? "All PO Creation Dates"
            : `${powerbiSelectedDatePeriods.size} period(s) selected`;
    }

    function renderPowerBIFamilyResults() {
        const body = $("#powerbi-family-results");
        if (!body) return;
        if (!powerbiFamilies.length) {
            body.innerHTML = `<div class="empty-state">No purchase families available.</div>`;
            return;
        }
        const term = ($("#powerbi-family-search")?.value || "").trim().toLowerCase();
        const allNames = new Set(powerbiFamilies.map((item) => String(item.name || "").trim()).filter(Boolean));
        const sourceHierarchy = powerbiFamilyHierarchy.length
            ? powerbiFamilyHierarchy
            : [{ name: "Purchase families", families: powerbiFamilies }];
        const filteredHierarchy = sourceHierarchy.map((group) => {
            const parent = String(group.name || "Unassigned").trim() || "Unassigned";
            const children = (Array.isArray(group.families) ? group.families : [])
                .map((item) => ({ name: String(item.name || "").trim() }))
                .filter((item) => item.name && allNames.has(item.name))
                .filter((item) => !term || parent.toLowerCase().includes(term) || item.name.toLowerCase().includes(term));
            return { name: parent, families: [...new Map(children.map((item) => [item.name, item])).values()] };
        }).filter((group) => group.families.length);
        const filteredNames = [...new Set(filteredHierarchy.flatMap((group) => group.families.map((item) => item.name)))];
        if (!filteredNames.length) {
            body.innerHTML = `<div class="empty-state">No families match the filter.</div>`;
            return;
        }
        const selectedCount = filteredNames.filter((name) => powerbiSelectedFamilies.has(name)).length;
        const allSelected = selectedCount === filteredNames.length;
        const branchMarkup = filteredHierarchy.map((group, index) => {
            const names = group.families.map((item) => item.name);
            const branchSelected = names.filter((name) => powerbiSelectedFamilies.has(name)).length;
            const branchAllSelected = branchSelected === names.length;
            const rows = group.families.map((item) => `<label class="powerbi-tree-row"><input type="checkbox" data-powerbi-family="${escapeHtml(item.name)}" ${powerbiSelectedFamilies.has(item.name) ? "checked" : ""}><span class="powerbi-tree-level">L2</span><span class="powerbi-tree-value" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</span></label>`).join("");
            return `<details class="powerbi-tree-branch powerbi-family-branch" ${term || index < 2 ? "open" : ""}><summary class="powerbi-tree-row powerbi-tree-row-group"><input type="checkbox" data-powerbi-family-group="${escapeHtml(group.name)}" ${branchAllSelected ? "checked" : ""} aria-label="Select ${escapeHtml(group.name)}"><span class="powerbi-tree-level">L1</span><span class="powerbi-tree-value" title="${escapeHtml(group.name)}">${escapeHtml(group.name)}</span><small>${branchSelected}/${names.length}</small></summary><div class="powerbi-tree-children">${rows}</div></details>`;
        }).join("");
        body.innerHTML = `<div class="powerbi-tree"><details class="powerbi-tree-branch" open><summary class="powerbi-tree-row powerbi-tree-row-all"><input type="checkbox" data-powerbi-group="family" ${allSelected ? "checked" : ""} aria-label="Select all purchase families"><span class="powerbi-tree-level">ALL</span><span class="powerbi-tree-value">All purchase families</span><small>${selectedCount}/${filteredNames.length}</small></summary><div class="powerbi-tree-children">${branchMarkup}</div></details></div>`;
        const groupInput = body.querySelector("input[data-powerbi-group=\"family\"]");
        if (groupInput) {
            groupInput.indeterminate = selectedCount > 0 && !allSelected;
            groupInput.addEventListener("click", (event) => event.stopPropagation());
            groupInput.addEventListener("change", () => {
                filteredNames.forEach((name) => groupInput.checked ? powerbiSelectedFamilies.add(name) : powerbiSelectedFamilies.delete(name));
                renderPowerBIFamilyResults();
                renderPowerBIFilterLabels();
            });
        }
        body.querySelectorAll("input[data-powerbi-family-group]").forEach((input) => {
            input.addEventListener("click", (event) => event.stopPropagation());
            input.addEventListener("change", () => {
                const group = filteredHierarchy.find((item) => item.name === input.dataset.powerbiFamilyGroup);
                (group?.families || []).forEach((item) => input.checked ? powerbiSelectedFamilies.add(item.name) : powerbiSelectedFamilies.delete(item.name));
                renderPowerBIFamilyResults();
                renderPowerBIFilterLabels();
            });
        });
        body.querySelectorAll("input[data-powerbi-family]").forEach((input) => input.addEventListener("change", () => {
            const name = input.dataset.powerbiFamily || "";
            if (input.checked) powerbiSelectedFamilies.add(name);
            else powerbiSelectedFamilies.delete(name);
            renderPowerBIFamilyResults();
            renderPowerBIFilterLabels();
        }));
        renderPowerBIFilterLabels();
    }

    function renderPowerBIQueryDiagnostics() {
        const details = $("#powerbi-query-details");
        if (!details) return;
        if (!powerbiQueryDiagnostics) {
            details.hidden = true;
            return;
        }
        details.hidden = false;
        const filters = powerbiQueryDiagnostics.filters || {};
        const queries = Array.isArray(powerbiQueryDiagnostics.queries) ? powerbiQueryDiagnostics.queries : [];
        const filterOutput = {
            dataset_id: powerbiQueryDiagnostics.dataset_id || "—",
            supplier_uu_codes: filters.supplier_uu_codes || [],
            management_unit_paths: filters.management_unit_paths || [],
            po_creation_periods: filters.po_creation_periods || [],
            date_ranges: filters.date_ranges || [],
            purchase_families: filters.purchase_families || [],
            selected_columns: powerbiQueryDiagnostics.selected_columns || [],
        };
        const daxOutput = queries.length
            ? queries.map((item, index) => {
                const query = item.request?.queries?.[0]?.query || "—";
                const range = item.date_range ? ` | ${item.date_range.start} to ${item.date_range.end_exclusive} (end exclusive)` : "";
                const rows = item.rows_returned === undefined || item.rows_returned === null ? "" : ` | ${item.rows_returned} row(s) returned`;
                const error = item.error ? `\n-- Error: ${item.error}` : "";
                return `-- Query ${index + 1}${range}${rows}${error}\n${query}`;
            }).join("\n\n")
            : "No DAX query details were returned by the current Power BI bridge. The filters above are the values submitted by the UI.";
        const status = $("#powerbi-query-status");
        if (status) status.innerText = `${queries.length} query/chunk(s) captured${powerbiQueryDiagnostics.source ? ` from ${powerbiQueryDiagnostics.source}` : ""}.`;
        const filtersBox = $("#powerbi-query-filters");
        const daxBox = $("#powerbi-query-dax");
        if (filtersBox) filtersBox.innerText = JSON.stringify(filterOutput, null, 2);
        if (daxBox) daxBox.innerText = daxOutput;
    }

    function startPowerBIQueryDiagnostics(codes, paths, selectedPeriods, families) {
        return {
            source: "Power BI PO Mass Download Dataset",
            dataset_id: null,
            filters: {
                supplier_uu_codes: codes,
                management_unit_paths: paths,
                po_creation_periods: selectedPeriods,
                date_ranges: [],
                purchase_families: families,
            },
            selected_columns: [...powerbiSelectedColumns],
            queries: [],
        };
    }

    function mergePowerBIQueryDiagnostics(target, incoming) {
        if (!target || !incoming) return;
        if (incoming.source) target.source = incoming.source;
        if (incoming.dataset_id) target.dataset_id = incoming.dataset_id;
        if (Array.isArray(incoming.selected_columns) && incoming.selected_columns.length) target.selected_columns = incoming.selected_columns;
        const incomingFilters = incoming.filters || {};
        if (Array.isArray(incomingFilters.date_ranges)) {
            const ranges = [...target.filters.date_ranges, ...incomingFilters.date_ranges];
            target.filters.date_ranges = [...new Map(ranges.map((range) => [JSON.stringify(range), range])).values()];
        }
        if (Array.isArray(incoming.queries)) target.queries.push(...incoming.queries);
    }

    async function loadPowerBIPurchaseFamilies(forceRefresh = false) {
        if (!hasApi("get_powerbi_purchase_families")) return false;
        if (powerbiFamiliesLoaded && !forceRefresh) return true;
        const button = $("#btn-powerbi-refresh-families");
        if (button) setButtonBusy(button, true);
        try {
            const result = await api().get_powerbi_purchase_families();
            if (!result.success) throw new Error(result.error || "Could not load purchase families.");
            powerbiFamilies = Array.isArray(result.families) ? result.families : [];
            powerbiFamilyHierarchy = Array.isArray(result.hierarchy) ? result.hierarchy : [];
            powerbiFamilyColumn = result.column || null;
            powerbiFamilyUpdatedAt = result.updated_at || new Date().toISOString();
            const columnLabel = $("#powerbi-family-column-label");
            if (columnLabel) columnLabel.innerText = powerbiFamilyColumn ? `Power BI column: ${powerbiFamilyColumn}` : "Power BI Purchase Family column.";
            const count = $("#powerbi-family-count");
            if (count) count.innerText = `${powerbiFamilies.length} available`;
            const updated = $("#powerbi-family-updated");
            if (updated) {
                const parsed = new Date(powerbiFamilyUpdatedAt);
                updated.innerText = Number.isNaN(parsed.getTime()) ? `Loaded: ${powerbiFamilyUpdatedAt}` : `Loaded from Power BI: ${parsed.toLocaleString()}`;
            }
            const available = new Set(powerbiFamilies.map((item) => item.name));
            powerbiSelectedFamilies = new Set([...powerbiSelectedFamilies].filter((name) => available.has(name)));
            powerbiFamiliesLoaded = true;
            renderPowerBIFamilyResults();
            return true;
        } catch (error) {
            setPowerBIMessage(error.message || "Could not load purchase families.", "powerbi-status-invalid");
            return false;
        } finally {
            if (button) setButtonBusy(button, false);
        }
    }

    function powerbiSupplierGroups() {
        const savedCodes = new Set(powerbiSupplierCache.map((item) => String(item.uu || "")));
        const saved = powerbiSearchResults.filter((item) => savedCodes.has(String(item.uu || "")));
        const other = powerbiSearchResults.filter((item) => !savedCodes.has(String(item.uu || "")));
        return [
            ["Saved suppliers", saved, "saved"],
            ["Other Power BI suppliers", other, "other"],
        ].filter(([, items]) => items.length);
    }

    function updatePowerBIGroupStates() {
        document.querySelectorAll("input[data-powerbi-group]").forEach((input) => {
            const kind = input.dataset.powerbiGroup;
            const items = powerbiSupplierGroups().find(([, , key]) => key === kind)?.[1] || [];
            const selected = items.filter((item) => {
                const code = String(item.uu || "");
                return powerbiSelectedSuppliers.has(code) || powerbiCheckedCandidates.has(code);
            }).length;
            input.checked = items.length > 0 && selected === items.length;
            input.indeterminate = selected > 0 && selected < items.length;
            const count = input.closest(".powerbi-filter-group-title")?.querySelector("small");
            if (count) count.innerText = `${selected}/${items.length}`;
        });
    }

    function renderPowerBISupplierResults() {
        const body = $("#powerbi-supplier-results");
        if (!body) return;
        const cachedCodes = new Set(powerbiSupplierCache.map((item) => String(item.uu || "")));
        if (!powerbiSearchResults.length) {
            body.innerHTML = `<div class="empty-state">No suppliers found.</div>`;
            const addButton = $("#btn-powerbi-add-suppliers");
            if (addButton) addButton.disabled = true;
            renderPowerBIFilterLabels();
            return;
        }
        body.innerHTML = powerbiSupplierGroups().map(([label, items, kind]) => {
            if (!items.length) return "";
            const rows = items.map((item) => {
                const uu = String(item.uu || "");
                const invalid = item.valid === false;
                const status = invalid
                    ? `<span class="powerbi-status-invalid">Invalid</span>`
                    : item.provisional
                        ? `<span class="powerbi-status-provisional">Provisional</span>`
                        : `<span class="powerbi-status-valid">Available</span>`;
                const matches = Array.isArray(item.matches) ? item.matches.slice(0, 2).join(" · ") : "";
                const additional = !cachedCodes.has(uu);
                const aliasInput = additional
                    ? `<input class="powerbi-alias-input" data-powerbi-alias-for="${escapeHtml(uu)}" type="text" value="${escapeHtml(item.alias && item.alias !== item.official_name ? item.alias : "")}" placeholder="Alias" aria-label="Alias for ${escapeHtml(item.official_name || uu)}">`
                    : "";
                const checked = additional ? powerbiCheckedCandidates.has(uu) : powerbiSelectedSuppliers.has(uu);
                return `<label class="powerbi-filter-option ${invalid ? "powerbi-invalid-row" : ""}"><input type="checkbox" data-powerbi-result="${escapeHtml(uu)}" ${additional ? "data-powerbi-additional=\"true\"" : ""} ${checked ? "checked" : ""}><span class="powerbi-filter-option-text"><strong>${escapeHtml(item.alias || item.official_name || "Supplier")}</strong><small>${escapeHtml(item.official_name || "—")} · ${escapeHtml(uu || "—")}${matches ? ` · ${escapeHtml(matches)}` : ""}</small></span>${aliasInput}${status}</label>`;
            }).join("");
            return `<section class="powerbi-filter-group powerbi-filter-group-${kind}"><div class="powerbi-filter-group-title"><label class="powerbi-filter-group-select" title="Select or clear all ${escapeHtml(label.toLowerCase())}"><input type="checkbox" data-powerbi-group="${kind}" aria-label="Select or clear all ${escapeHtml(label)}"><span>${escapeHtml(label)}</span></label><small>0/${items.length}</small></div>${rows}</section>`;
        }).join("");
        body.querySelectorAll("input[data-powerbi-group]").forEach((input) => {
            const kind = input.dataset.powerbiGroup;
            const items = powerbiSupplierGroups().find(([, , key]) => key === kind)?.[1] || [];
            input.addEventListener("change", () => {
                items.forEach((item) => {
                    const code = String(item.uu || "");
                    if (input.checked) {
                        if (item.uu && !cachedCodes.has(String(item.uu))) powerbiCheckedCandidates.add(code);
                        else powerbiSelectedSuppliers.set(code, item);
                    } else {
                        powerbiCheckedCandidates.delete(code);
                        powerbiSelectedSuppliers.delete(code);
                    }
                });
                const addButton = $("#btn-powerbi-add-suppliers");
                if (addButton) addButton.disabled = !powerbiCheckedCandidates.size;
                renderPowerBISelectedSuppliers();
            });
        });
        body.querySelectorAll("input[data-powerbi-result]").forEach((input) => input.addEventListener("change", () => {
            const code = input.dataset.powerbiResult || "";
            const item = powerbiSearchResults.find((candidate) => String(candidate.uu || "") === code);
            if (!item) return;
            const aliasInput = [...body.querySelectorAll("input[data-powerbi-alias-for]")].find((candidate) => candidate.dataset.powerbiAliasFor === code);
            const alias = aliasInput?.value.trim() || "";
            const selectedItem = alias ? { ...item, alias } : item;
            if (input.checked) {
                if (cachedCodes.has(code)) powerbiSelectedSuppliers.set(code, selectedItem);
                else powerbiCheckedCandidates.add(code);
            } else {
                powerbiCheckedCandidates.delete(code);
                powerbiSelectedSuppliers.delete(code);
            }
            renderPowerBISelectedSuppliers();
            updatePowerBIGroupStates();
        }));
        updatePowerBIGroupStates();
        const addButton = $("#btn-powerbi-add-suppliers");
        if (addButton) addButton.disabled = !powerbiCheckedCandidates.size;
        renderPowerBIFilterLabels();
    }

    function focusPowerBIAdditionalResult() {
        const target = $("#powerbi-supplier-results input[data-powerbi-additional=\"true\"]");
        if (!target) return;
        target.closest("tr")?.scrollIntoView({ block: "nearest" });
        target.focus({ preventScroll: true });
    }

    function renderPowerBISelectedSuppliers() {
        const body = $("#powerbi-selected-suppliers");
        const count = $("#powerbi-selected-count");
        if (count) count.innerText = String(powerbiSelectedSuppliers.size);
        renderPowerBIFilterLabels();
        if (!body) return;
        if (!powerbiSelectedSuppliers.size) {
            body.innerHTML = `<tr><td colspan="4" class="empty-state">No suppliers added yet.</td></tr>`;
            return;
        }
        body.innerHTML = [...powerbiSelectedSuppliers.values()].map((item) => {
            const invalid = item.valid === false;
            return `<tr class="${invalid ? "powerbi-invalid-row" : ""}"><td><strong>${escapeHtml(item.alias || item.official_name || "Supplier")}</strong><small>${escapeHtml(item.official_name || "")}</small></td><td><code>${escapeHtml(item.uu || "—")}</code></td><td>${invalid ? `<span class="powerbi-status-invalid">Invalid</span>` : escapeHtml(item.source || "Local cache")}</td><td><button class="icon-btn" type="button" data-powerbi-remove="${escapeHtml(item.uu || "")}" aria-label="Remove supplier">×</button></td></tr>`;
        }).join("");
        body.querySelectorAll("button[data-powerbi-remove]").forEach((button) => button.addEventListener("click", () => {
            powerbiSelectedSuppliers.delete(button.dataset.powerbiRemove || "");
            renderPowerBISelectedSuppliers();
            updatePowerBIGroupStates();
        }));
    }

    function showPowerBICacheResults() {
        powerbiSearchResults = powerbiSupplierCache.map((item) => ({ ...item, source: item.source || "Local cache" }));
        powerbiCheckedCandidates.clear();
        renderPowerBISupplierResults();
    }

    function mergePowerBISupplierResults(additional) {
        const remoteByUU = new Map((additional || []).map((item) => [String(item.uu || ""), item]));
        const cachedCodes = new Set(powerbiSupplierCache.map((item) => String(item.uu || "")));
        const cached = powerbiSupplierCache.map((item) => {
            const remote = remoteByUU.get(String(item.uu || ""));
            return { ...item, ...(remote && Array.isArray(remote.matches) ? { matches: remote.matches } : {}), source: item.source || "Local cache" };
        });
        return [...cached, ...(additional || []).filter((item) => item.uu && !cachedCodes.has(String(item.uu)))];
    }

    let settingsNgsiResults = [];

    function renderSettingsNgsiCache() {
        const body = $("#settings-ngsi-cache");
        if (!body) return;
        const custom = powerbiSupplierCache.filter((item) => !item.provisional);
        body.innerHTML = `<h4>Saved mappings</h4>` + (custom.length
            ? custom.map((item) => `<div class="settings-ngsi-cache-row"><span><strong>${escapeHtml(item.alias || item.official_name || "Supplier")}</strong><small>${escapeHtml(item.official_name || "—")} · ${escapeHtml(item.uu || "—")}</small></span><button class="icon-btn" type="button" data-settings-ngsi-remove="${escapeHtml(item.uu || "")}" aria-label="Remove mapping">×</button></div>`).join("")
            : `<div class="empty-state">No custom mappings saved yet.</div>`);
        body.querySelectorAll("[data-settings-ngsi-remove]").forEach((button) => button.addEventListener("click", async () => {
            if (!hasApi("delete_powerbi_supplier")) return;
            button.disabled = true;
            const result = await api().delete_powerbi_supplier(button.dataset.settingsNgsiRemove || "");
            if (!result.success) {
                $("#settings-status").innerText = result.error || "Could not remove the supplier mapping.";
                button.disabled = false;
                return;
            }
            powerbiSupplierCache = Array.isArray(result.suppliers) ? result.suppliers : powerbiSupplierCache;
            showPowerBICacheResults();
            renderSettingsNgsiCache();
        }));
    }

    function renderSettingsNgsiResults() {
        const body = $("#settings-ngsi-results");
        const add = $("#btn-settings-ngsi-add");
        if (!body) return;
        if (!settingsNgsiResults.length) {
            body.innerHTML = `<div class="empty-state">No UU group was found for this search.</div>`;
            if (add) add.disabled = true;
            return;
        }
        body.innerHTML = settingsNgsiResults.map((item) => {
            const matches = Array.isArray(item.matches) ? item.matches.join(" · ") : "";
            return `<label class="powerbi-filter-option"><input type="checkbox" data-settings-ngsi-result="${escapeHtml(item.uu || "")}"><span class="powerbi-filter-option-text"><strong>${escapeHtml(item.official_name || item.uu || "UU group")}</strong><small>UU ${escapeHtml(item.uu || "—")}${item.gu ? ` · GU ${escapeHtml(item.gu)}` : ""}${matches ? ` · Matched: ${escapeHtml(matches)}` : ""}</small></span><input class="powerbi-alias-input" data-settings-ngsi-alias="${escapeHtml(item.uu || "")}" type="text" placeholder="Alias, e.g. Mindtree" aria-label="Alias for ${escapeHtml(item.official_name || item.uu || "UU group")}"></label>`;
        }).join("");
        body.querySelectorAll("[data-settings-ngsi-result]").forEach((input) => input.addEventListener("change", () => {
            if (add) add.disabled = !body.querySelector("[data-settings-ngsi-result]:checked");
        }));
    }

    async function loadSettingsNgsi() {
        if (!hasApi("get_powerbi_supplier_cache")) return;
        const result = await api().get_powerbi_supplier_cache();
        if (!result.success) return;
        powerbiSupplierCache = Array.isArray(result.suppliers) ? result.suppliers : [];
        renderSettingsNgsiCache();
    }

    async function searchSettingsNgsi() {
        const term = $("#settings-ngsi-search")?.value.trim() || "";
        if (!term || !hasApi("search_powerbi_suppliers")) return;
        const button = $("#btn-settings-ngsi-search");
        setButtonBusy(button, true);
        button.disabled = true;
        try {
            const result = await api().search_powerbi_suppliers(term);
            if (!result.success) throw new Error(result.error || "Supplier search failed.");
            settingsNgsiResults = Array.isArray(result.suppliers) ? result.suppliers : [];
            renderSettingsNgsiResults();
        } catch (error) {
            $("#settings-ngsi-results").innerHTML = `<div class="empty-state powerbi-status-invalid">${escapeHtml(error.message || "Supplier search failed.")}</div>`;
        } finally {
            button.disabled = false;
            setButtonBusy(button, false);
        }
    }

    async function addSettingsNgsi() {
        const body = $("#settings-ngsi-results");
        const selected = [...(body?.querySelectorAll("[data-settings-ngsi-result]:checked") || [])].map((input) => {
            const item = settingsNgsiResults.find((candidate) => String(candidate.uu || "") === input.dataset.settingsNgsiResult);
            const alias = body.querySelector(`[data-settings-ngsi-alias="${CSS.escape(input.dataset.settingsNgsiResult || "")}"]`)?.value.trim();
            return item && alias ? { ...item, alias, provisional: false } : null;
        }).filter(Boolean);
        if (!selected.length) {
            $("#settings-status").innerText = "Select a UU group and enter an alias before saving.";
            return;
        }
        const result = await api().save_powerbi_suppliers(selected);
        if (!result.success) {
            $("#settings-status").innerText = result.error || "Could not save supplier mappings.";
            return;
        }
        powerbiSupplierCache = Array.isArray(result.suppliers) ? result.suppliers : powerbiSupplierCache;
        settingsNgsiResults = [];
        renderSettingsNgsiResults();
        renderSettingsNgsiCache();
        showPowerBICacheResults();
        $("#settings-status").innerText = "NGSI supplier mappings saved on this computer.";
    }

    async function validateSettingsNgsi() {
        const result = await api().validate_powerbi_supplier_cache();
        if (!result.success) {
            $("#settings-status").innerText = result.error || "Could not validate supplier mappings.";
            return;
        }
        const invalid = new Set((result.invalid || []).map((item) => item.uu));
        powerbiSupplierCache = powerbiSupplierCache.map((item) => ({ ...item, valid: !invalid.has(item.uu) }));
        renderSettingsNgsiCache();
        $("#settings-status").innerText = invalid.size ? `${invalid.size} cached UU code(s) were not found in Power BI.` : `${result.checked} cached UU code(s) are valid.`;
    }

    async function loadPowerBISupplierCache() {
        if (!hasApi("get_powerbi_supplier_cache")) return;
        const result = await api().get_powerbi_supplier_cache();
        if (!result.success) throw new Error(result.error || "Could not load the local supplier cache.");
        powerbiSupplierCache = Array.isArray(result.suppliers) ? result.suppliers : [];
        showPowerBICacheResults();
        renderPowerBISelectedSuppliers();
    }

    async function refreshPowerBIConnectionStatus() {
        if (!hasApi("get_powerbi_status")) {
            setPowerBIConnectionStatus("unavailable", "Power BI is available in the desktop app.");
            return;
        }
        setPowerBIConnectionStatus("authenticating", "Checking Power BI session…");
        const result = await api().get_powerbi_status();
        if (result.authenticated) setPowerBIConnectionStatus("authenticated", result.message);
        else setPowerBIConnectionStatus(result.available ? "expired" : "unavailable", result.message || "Power BI sign-in required.");
    }

    function updatePowerBIHierarchyUpdatedAt(value) {
        powerbiHierarchyUpdatedAt = value || null;
        const label = $("#powerbi-hierarchy-updated");
        const button = $("#btn-powerbi-refresh-hierarchy");
        if (!label || !button) return;
        if (!powerbiHierarchyUpdatedAt) {
            label.innerText = "Management Unit has not been refreshed yet.";
            button.title = "Management Unit has not been refreshed yet. Click to refresh.";
            button.setAttribute("aria-label", "Refresh Management Unit. No previous refresh.");
            return;
        }
        const parsed = new Date(powerbiHierarchyUpdatedAt);
        const formatted = Number.isNaN(parsed.getTime()) ? powerbiHierarchyUpdatedAt : parsed.toLocaleString();
        label.innerText = `Last updated: ${formatted}`;
        button.title = `Last updated: ${formatted}. Click to refresh.`;
        button.setAttribute("aria-label", `Refresh Management Unit. Last updated ${formatted}.`);
    }

    async function loadPowerBIHierarchyCache() {
        if (!hasApi("get_powerbi_management_hierarchy_cache")) {
            renderPowerBIHierarchy();
            return;
        }
        const result = await api().get_powerbi_management_hierarchy_cache();
        if (!result.success) throw new Error(result.error || "Could not load the cached Management Unit hierarchy.");
        powerbiHierarchyPaths = Array.isArray(result.paths) ? result.paths : [];
        updatePowerBIHierarchyUpdatedAt(result.updated_at);
        $("#powerbi-hierarchy-count").innerText = powerbiHierarchyPaths.length ? `${powerbiHierarchyPaths.length} paths` : "Not loaded";
        renderPowerBIHierarchy();
    }

    function powerBIMonthsInRange(minDate, maxDate) {
        const minimum = new Date(`${String(minDate).slice(0, 4)}-01-01T00:00:00`);
        const maximum = new Date(`${String(maxDate).slice(0, 4)}-12-01T00:00:00`);
        if (Number.isNaN(minimum.getTime()) || Number.isNaN(maximum.getTime()) || minimum > maximum) return [];
        const months = [];
        const cursor = new Date(minimum);
        while (cursor <= maximum && months.length < 240) {
            months.push(`${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}`);
            cursor.setMonth(cursor.getMonth() + 1);
        }
        return months;
    }

    function powerBIDateGroupMonths(key, months) {
        if (key === "__all__") return months;
        if (/^\d{4}$/.test(key)) return months.filter((month) => month.startsWith(`${key}-`));
        const match = /^(\d{4})-Q([1-4])$/.exec(key);
        if (!match) return [];
        const quarter = Number(match[2]);
        return months.filter((month) => month.startsWith(`${match[1]}-`) && Math.floor((Number(month.slice(5)) - 1) / 3) + 1 === quarter);
    }

    function syncPowerBIDateStates(months) {
        const container = $("#powerbi-date-hierarchy");
        if (!container) return;
        container.querySelectorAll("input[data-powerbi-date-group]").forEach((input) => {
            const groupMonths = powerBIDateGroupMonths(input.dataset.powerbiDateGroup || "", months);
            const selectedCount = groupMonths.filter((month) => powerbiSelectedDatePeriods.has(month)).length;
            input.checked = groupMonths.length > 0 && selectedCount === groupMonths.length;
            input.indeterminate = selectedCount > 0 && selectedCount < groupMonths.length;
            const count = input.closest("details")?.querySelector("[data-powerbi-date-count]");
            if (count) count.innerText = `${selectedCount}/${groupMonths.length}`;
        });
        container.querySelectorAll("input[data-powerbi-date-month]").forEach((input) => {
            input.checked = powerbiSelectedDatePeriods.has(input.dataset.powerbiDateMonth || "");
        });
        renderPowerBIFilterLabels();
    }

    function renderPowerBIDateHierarchy() {
        const container = $("#powerbi-date-hierarchy");
        if (!container) return;
        const months = powerBIMonthsInRange(powerbiDateRange.min_date, powerbiDateRange.max_date);
        if (!months.length) {
            const count = $("#powerbi-date-count");
            if (count) count.innerText = "Not loaded";
            container.innerHTML = '<div class="hierarchy-empty">No PO Creation Date range is available.</div>';
            renderPowerBIFilterLabels();
            return;
        }
        const years = new Map();
        months.forEach((month) => {
            const year = month.slice(0, 4);
            if (!years.has(year)) years.set(year, []);
            years.get(year).push(month);
        });
        const treeMarkup = [...years.entries()].map(([year, yearMonths]) => {
            const quarters = [1, 2, 3, 4].map((quarter) => {
                const quarterMonths = yearMonths.filter((month) => Math.floor((Number(month.slice(5)) - 1) / 3) + 1 === quarter);
                if (!quarterMonths.length) return "";
                const quarterKey = `${year}-Q${quarter}`;
                const monthRows = quarterMonths.map((month) => `<label class="powerbi-tree-row powerbi-date-month-row"><input type="checkbox" data-powerbi-date-month="${month}" ${powerbiSelectedDatePeriods.has(month) ? "checked" : ""}><span class="powerbi-tree-level">M</span><span class="powerbi-tree-value">${new Date(`${month}-01T00:00:00`).toLocaleString("en-US", { month: "short" })}</span></label>`).join("");
                return `<details class="powerbi-tree-branch powerbi-date-branch powerbi-date-quarter"><summary class="powerbi-tree-row powerbi-tree-row-group"><input type="checkbox" data-powerbi-date-group="${quarterKey}" aria-label="Select Q${quarter} ${year}"><span class="powerbi-tree-level">L2</span><span class="powerbi-tree-value">Q${quarter}</span><small data-powerbi-date-count="${quarterKey}"></small></summary><div class="powerbi-tree-children">${monthRows}</div></details>`;
            }).join("");
            return `<details class="powerbi-tree-branch powerbi-date-branch powerbi-date-year"><summary class="powerbi-tree-row powerbi-tree-row-group"><input type="checkbox" data-powerbi-date-group="${year}" aria-label="Select ${year}"><span class="powerbi-tree-level">L1</span><span class="powerbi-tree-value">${year}</span><small data-powerbi-date-count="${year}"></small></summary><div class="powerbi-tree-children">${quarters}</div></details>`;
        }).join("");
        const selectedCount = months.filter((month) => powerbiSelectedDatePeriods.has(month)).length;
        container.innerHTML = `<div class="powerbi-tree"><details class="powerbi-tree-branch" open><summary class="powerbi-tree-row powerbi-tree-row-all"><input type="checkbox" data-powerbi-date-group="__all__" aria-label="Select all PO creation dates"><span class="powerbi-tree-level">ALL</span><span class="powerbi-tree-value">All PO Creation Dates</span><small data-powerbi-date-count="__all__">${selectedCount}/${months.length}</small></summary><div class="powerbi-tree-children">${treeMarkup}</div></details></div>`;
        container.querySelectorAll("summary input[data-powerbi-date-group]").forEach((input) => input.addEventListener("click", (event) => event.stopPropagation()));
        container.querySelectorAll("input[data-powerbi-date-group]").forEach((input) => {
            input.addEventListener("change", () => {
                const selected = input.checked;
                powerBIDateGroupMonths(input.dataset.powerbiDateGroup || "", months).forEach((month) => {
                    if (selected) powerbiSelectedDatePeriods.add(month);
                    else powerbiSelectedDatePeriods.delete(month);
                });
                syncPowerBIDateStates(months);
            });
        });
        container.querySelectorAll("input[data-powerbi-date-month]").forEach((input) => input.addEventListener("change", () => {
            const month = input.dataset.powerbiDateMonth || "";
            if (input.checked) powerbiSelectedDatePeriods.add(month);
            else powerbiSelectedDatePeriods.delete(month);
            syncPowerBIDateStates(months);
        }));
        syncPowerBIDateStates(months);
    }

    async function loadPowerBIDateRange(forceRefresh = false) {
        const method = forceRefresh ? "refresh_powerbi_po_date_range" : "get_powerbi_po_date_range";
        if (!hasApi(method)) return false;
        const result = await api()[method]();
        if (!result.success) throw new Error(result.error || "Could not load the PO Creation Date range.");
        powerbiDateRange = { min_date: result.min_date, max_date: result.max_date, updated_at: result.updated_at };
        const available = new Set(powerBIMonthsInRange(result.min_date, result.max_date));
        powerbiSelectedDatePeriods = new Set([...powerbiSelectedDatePeriods].filter((period) => available.has(period)));
        const count = $("#powerbi-date-count");
        if (count) count.innerText = available.size ? `${available.size} available` : "Not loaded";
        const updated = $("#powerbi-date-updated");
        if (updated) {
            const parsed = new Date(result.updated_at || "");
            updated.innerText = Number.isNaN(parsed.getTime()) ? `Loaded: ${result.updated_at || "unknown"}` : `Loaded from Power BI: ${parsed.toLocaleString()}`;
        }
        renderPowerBIDateHierarchy();
        return true;
    }

    async function loadPowerBIScreen() {
        if (powerbiScreenLoaded) {
            await refreshPowerBIConnectionStatus();
            return;
        }
        powerbiScreenLoaded = true;
        try {
            await loadPowerBIColumns();
            await loadPowerBISupplierCache();
            await loadPowerBIHierarchyCache();
            await loadPowerBIDateRange();
            await loadPowerBIPurchaseFamilies();
            await refreshPowerBIConnectionStatus();
        } catch (error) {
            powerbiScreenLoaded = false;
            setPowerBIConnectionStatus("unavailable", error.message || "Power BI integration unavailable.");
            setPowerBIMessage(error.message || "Could not load the Power BI tab.", "powerbi-status-invalid");
        }
    }

    async function searchPowerBISuppliers() {
        if (!hasApi("search_powerbi_suppliers")) {
            setPowerBIMessage("Power BI search is available in the desktop app after sign-in.", "powerbi-status-invalid");
            return;
        }
        const term = $("#powerbi-supplier-search").value.trim();
        if (!term) {
            showPowerBICacheResults();
            return;
        }
        const button = $("#btn-powerbi-search");
        setButtonBusy(button, true);
        button.disabled = true;
        setPowerBIMessage("Searching the Power BI supplier hierarchy…");
        try {
            const result = await api().search_powerbi_suppliers(term);
            if (!result.success) throw new Error(result.error || "Supplier search failed.");
            powerbiSearchResults = mergePowerBISupplierResults(Array.isArray(result.suppliers) ? result.suppliers : []);
            powerbiCheckedCandidates.clear();
            renderPowerBISupplierResults();
            focusPowerBIAdditionalResult();
            const cachedCodes = new Set(powerbiSupplierCache.map((item) => String(item.uu || "")));
            const additionalCount = powerbiSearchResults.filter((item) => !cachedCodes.has(String(item.uu || ""))).length;
            setPowerBIMessage(`${additionalCount} additional supplier group(s) found. Cached suppliers remain at the top.`);
        } catch (error) {
            setPowerBIMessage(error.message || "Supplier search failed.", "powerbi-status-invalid");
        } finally {
            button.disabled = false;
            setButtonBusy(button, false);
        }
    }

    async function addPowerBISuppliers() {
        const button = $("#btn-powerbi-add-suppliers");
        if (button.dataset.busy === "1") return;
        const selected = powerbiSearchResults
            .filter((item) => powerbiCheckedCandidates.has(String(item.uu || "")) && item.uu)
            .map((item) => {
                const aliasInput = [...document.querySelectorAll("input[data-powerbi-alias-for]")]
                    .find((input) => input.dataset.powerbiAliasFor === String(item.uu || ""));
                const alias = aliasInput?.value.trim() || "";
                return alias ? { ...item, alias } : item;
            });
        if (!selected.length) {
            setPowerBIMessage("Select at least one supplier result before adding.", "powerbi-status-invalid");
            return;
        }
        setButtonBusy(button, true);
        button.disabled = true;
        try {
            const result = await api().save_powerbi_suppliers(selected);
            if (!result.success) throw new Error(result.error || "Could not save suppliers.");
            powerbiSupplierCache = Array.isArray(result.suppliers) ? result.suppliers : powerbiSupplierCache;
            selected.forEach((item) => powerbiSelectedSuppliers.set(item.uu, item));
            renderPowerBISelectedSuppliers();
            setPowerBIMessage(`${selected.length} supplier(s) added to the local list.`);
        } catch (error) {
            setPowerBIMessage(error.message || "Could not save suppliers.", "powerbi-status-invalid");
        }
        powerbiCheckedCandidates.clear();
        renderPowerBISupplierResults();
        updatePowerBIGroupStates();
        button.disabled = false;
        setButtonBusy(button, false);
    }

    async function validatePowerBISuppliers() {
        const button = $("#btn-powerbi-validate");
        setButtonBusy(button, true);
        button.disabled = true;
        setPowerBIMessage("Validating cached supplier codes in Power BI…");
        try {
            const result = await api().validate_powerbi_supplier_cache();
            if (!result.success) throw new Error(result.error || "Supplier validation failed.");
            const invalid = new Set((result.invalid || []).map((item) => item.uu));
            powerbiSupplierCache = powerbiSupplierCache.map((item) => ({ ...item, valid: !invalid.has(item.uu) }));
            powerbiSearchResults = powerbiSearchResults.map((item) => ({ ...item, valid: !invalid.has(item.uu) }));
            powerbiSelectedSuppliers = new Map([...powerbiSelectedSuppliers.entries()].map(([key, item]) => [key, { ...item, valid: !invalid.has(item.uu) }]));
            renderPowerBISupplierResults();
            renderPowerBISelectedSuppliers();
            setPowerBIMessage(invalid.size ? `${invalid.size} cached code(s) were not found in Power BI.` : `${result.checked} cached supplier code(s) are valid.`, invalid.size ? "powerbi-status-invalid" : "powerbi-status-valid");
            await refreshPowerBIConnectionStatus();
        } catch (error) {
            setPowerBIMessage(error.message || "Supplier validation failed.", "powerbi-status-invalid");
        } finally {
            button.disabled = false;
            setButtonBusy(button, false);
        }
    }

    function renderPowerBIHierarchy() {
        const container = $("#powerbi-hierarchy");
        if (!container) return;
        if (!powerbiHierarchyPaths.length) {
            powerbiPathByKey = new Map();
            container.innerHTML = `<div class="hierarchy-empty">${powerbiHierarchyUpdatedAt ? "No Management Unit paths were returned." : "No cached Management Unit hierarchy. Click refresh to load it from Power BI."}</div>`;
            renderPowerBIFilterLabels();
            return;
        }
        const root = { key: "", children: new Map(), pathKeys: new Set() };
        powerbiPathByKey = new Map();
        powerbiHierarchyPaths.forEach((path) => {
            const values = [1, 2, 3, 4, 5, 6].map((index) => String(path[`l${index}`] || "").trim());
            const key = JSON.stringify(values);
            if (powerbiPathByKey.has(key)) return;
            powerbiPathByKey.set(key, path);
            let node = root;
            node.pathKeys.add(key);
            values.forEach((value, index) => {
                if (!value) return;
                let child = node.children.get(value);
                if (!child) {
                    const childKey = node.key ? `${node.key}\u001f${value}` : value;
                    child = { key: childKey, label: value, level: index + 1, children: new Map(), pathKeys: new Set() };
                    node.children.set(value, child);
                }
                child.pathKeys.add(key);
                node = child;
            });
        });

        const allNode = { key: "__powerbi_all__", label: "All", kind: "all", levelLabel: "ALL", alwaysExpanded: true, children: new Map(), pathKeys: new Set(root.pathKeys) };
        const groups = [
            { key: "__powerbi_group_digital__", label: "Digital and Technology", kind: "group", children: new Map(), pathKeys: new Set() },
            { key: "__powerbi_group_non_digital__", label: "Non-Digital and Technology", kind: "group", children: new Map(), pathKeys: new Set() },
        ];
        const l1Nodes = [...root.children.values()];
        const digitalL1s = l1Nodes.filter((node) => isDigitalManagementUnit(node.label));
        const nonDigitalL1s = l1Nodes.filter((node) => !isDigitalManagementUnit(node.label));
        if (digitalL1s.length === 1) {
            // The Digital group represents that single L1, so its children are
            // the L2 nodes directly (2nd level of the tree).
            digitalL1s[0].children.forEach((l2, label) => groups[0].children.set(label, l2));
            digitalL1s[0].pathKeys.forEach((key) => groups[0].pathKeys.add(key));
        } else {
            // Multiple digital L1s: keep each L1 as a branch inside the group.
            digitalL1s.forEach((l1) => {
                groups[0].children.set(l1.label, l1);
                l1.pathKeys.forEach((key) => groups[0].pathKeys.add(key));
            });
        }
        nonDigitalL1s.forEach((l1) => {
            groups[1].children.set(l1.label, l1);
            l1.pathKeys.forEach((key) => groups[1].pathKeys.add(key));
        });
        groups.filter((group) => group.children.size).forEach((group) => allNode.children.set(group.label, {
            ...group,
            levelLabel: "L1",
        }));
        const displayRoot = { key: "__powerbi_display_root__", children: new Map([[allNode.label, allNode]]), pathKeys: allNode.pathKeys };
        powerbiNodeMap = new Map();
        let nodeId = 0;
        const renderNode = (node, level) => [...node.children.values()].sort((a, b) => a.label.localeCompare(b.label)).map((child) => {
            const id = `powerbi-tree-${++nodeId}`;
            const keys = [...child.pathKeys];
            const selectedCount = keys.filter((key) => powerbiSelectedPathKeys.has(key)).length;
            const checked = keys.length > 0 && selectedCount === keys.length;
            const hasChildren = child.children.size > 0;
            const levelLabel = child.levelLabel || `L${child.level || level}`;
            const rowClass = child.kind ? ` powerbi-tree-row-${child.kind}` : "";
            powerbiNodeMap.set(id, { key: child.key, keys, level });
            const checkbox = `<input type="checkbox" data-powerbi-tree-node="${id}" aria-label="Select ${escapeHtml(child.label)}" ${checked ? "checked" : ""}>`;
            const levelBadge = child.kind === "group" ? "" : `<span class="powerbi-tree-level">${escapeHtml(levelLabel)}</span>`;
            const rowContent = `${levelBadge}<span class="powerbi-tree-value" title="${escapeHtml(child.label)}">${escapeHtml(child.label)}</span>`;
            if (hasChildren) {
                // Native <details> keeps expansion state without JS re-renders;
                // groups are expanded by default so the hierarchy is visible.
                const openAttr = child.alwaysExpanded || child.kind === "group" ? " open" : "";
                return `<details class="powerbi-tree-branch"${openAttr}><summary class="powerbi-tree-row${rowClass}">${checkbox}${rowContent}</summary><div class="powerbi-tree-children">${renderNode(child, level + 1)}</div></details>`;
            }
            return `<label class="powerbi-tree-row${rowClass}">${checkbox}${rowContent}</label>`;
        }).join("");
        container.innerHTML = `<div class="powerbi-tree">${renderNode(displayRoot, 1)}</div>`;
        container.querySelectorAll("input[data-powerbi-tree-node]").forEach((input) => {
            const node = powerbiNodeMap.get(input.dataset.powerbiTreeNode);
            const selectedCount = node.keys.filter((key) => powerbiSelectedPathKeys.has(key)).length;
            input.indeterminate = selectedCount > 0 && selectedCount < node.keys.length;
            input.addEventListener("click", (event) => event.stopPropagation());
            input.addEventListener("change", () => {
                node.keys.forEach((key) => input.checked ? powerbiSelectedPathKeys.add(key) : powerbiSelectedPathKeys.delete(key));
                // In-place sync only; the native <details> keeps its open/closed
                // state, so the tree no longer collapses on every selection.
                syncPowerBITreeStates();
                renderPowerBIFilterLabels();
            });
        });
        renderPowerBIFilterLabels();
    }

    function syncPowerBITreeStates() {
        document.querySelectorAll("input[data-powerbi-tree-node]").forEach((input) => {
            const node = powerbiNodeMap.get(input.dataset.powerbiTreeNode);
            if (!node) return;
            const selectedCount = node.keys.filter((key) => powerbiSelectedPathKeys.has(key)).length;
            input.checked = node.keys.length > 0 && selectedCount === node.keys.length;
            input.indeterminate = selectedCount > 0 && selectedCount < node.keys.length;
        });
    }

    async function loadPowerBIHierarchy() {
        const button = $("#btn-powerbi-refresh-hierarchy");
        setButtonBusy(button, true);
        button.disabled = true;
        button.title = "Refreshing Management Unit…";
        button.setAttribute("aria-label", "Refreshing Management Unit…");
        setPowerBIMessage("Loading the independent Management Unit hierarchy…");
        try {
            const result = await api().get_powerbi_management_hierarchy();
            if (!result.success) throw new Error(result.error || "Could not load Management Unit.");
            powerbiHierarchyPaths = Array.isArray(result.paths) ? result.paths : [];
            powerbiExpandedNodeKeys.clear();
            $("#powerbi-hierarchy-count").innerText = `${powerbiHierarchyPaths.length} paths`;
            updatePowerBIHierarchyUpdatedAt(result.updated_at);
            renderPowerBIHierarchy();
            setPowerBIMessage("Management Unit hierarchy loaded.", "powerbi-status-valid");
        } catch (error) {
            setPowerBIMessage(error.message || "Could not load Management Unit.", "powerbi-status-invalid");
        } finally {
            button.disabled = false;
            setButtonBusy(button, false);
            updatePowerBIHierarchyUpdatedAt(powerbiHierarchyUpdatedAt);
        }
    }

    const powerBIGrirStatusLabels = {
        no_invoice: "No invoice",
        goods_received_gt_invoice: "GR > Invoice",
        invoice_received_gt_goods: "Invoice > GR",
        balanced: "Balanced",
    };

    function formatPowerBIEur(value, compact = false) {
        const number = Number(value) || 0;
        return new Intl.NumberFormat("en-GB", compact
            ? { style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 1 }
            : { style: "currency", currency: "EUR", maximumFractionDigits: 2 }).format(number);
    }

    function formatPowerBIRate(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number.toFixed(6) : "—";
    }

    function finitePowerBINumber(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
    }

    function sumPowerBIFinite(rows, key) {
        return rows.reduce((total, row) => {
            const value = finitePowerBINumber(row[key]);
            return value === null ? total : total + value;
        }, 0);
    }

    function selectedPowerBIPOs() {
        return [...new Set(powerbiPreviewRows.map((row) => String(row.po_number || "").trim()).filter(Boolean))]
            .filter((po) => !powerbiExcludedPOs.has(po));
    }

    function powerBIColumn(key) {
        return powerbiPoColumns.find((column) => column.key === key) || null;
    }

    function powerBISelectedColumnSpecs() {
        const specs = powerbiSelectedColumns.size
            ? [...powerbiSelectedColumns].map(powerBIColumn).filter(Boolean)
            : powerbiPoColumns.filter((column) => column.default || column.required);
        return specs.length ? specs : powerbiPoColumns.filter((column) => column.required);
    }

    function powerBISnapshotColumnSpecs() {
        const specs = [...powerBISelectedColumnSpecs()];
        const selected = new Set(specs.map((column) => column.key));
        ["crg", "year"].forEach((key) => {
            const column = powerBIColumn(key);
            if (column && !selected.has(key)) specs.push(column);
        });
        return specs;
    }

    function powerBIInputHeader(spec, reserved) {
        const label = String(spec?.label || spec?.key || "Power BI field").trim();
        let normalized = label.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toUpperCase() || "POWERBI_FIELD";
        if (reserved.has(normalized)) normalized = "POWERBI_" + normalized;
        return normalized;
    }

    function readPersistedPowerBIColumns() {
        try {
            if (typeof localStorage === "undefined") return new Set();
            const parsed = JSON.parse(localStorage.getItem(POWERBI_SELECTED_COLUMNS_STORAGE_KEY) || "[]");
            return Array.isArray(parsed) ? new Set(parsed.map(String).filter(Boolean)) : new Set();
        } catch (_) {
            return new Set();
        }
    }

    async function persistPowerBIColumns() {
        try {
            if (typeof localStorage !== "undefined") {
                localStorage.setItem(POWERBI_SELECTED_COLUMNS_STORAGE_KEY, JSON.stringify([...powerbiSelectedColumns]));
            }
        } catch (_) {
            // Local persistence is a convenience; preview and validation must
            // continue to work when the embedded browser blocks storage.
        }
        if (!hasApi("save_powerbi_po_column_selection")) return;
        try {
            await api().save_powerbi_po_column_selection([...powerbiSelectedColumns]);
        } catch (_) {
            // SQLite persistence is best effort; localStorage remains the
            // fallback for older desktop bridges and browser previews.
        }
    }

    function updatePowerBIColumnSummary() {
        const count = powerBISelectedColumnSpecs().length;
        const summary = `${count} field${count === 1 ? "" : "s"}`;
        const title = `${count} field${count === 1 ? "" : "s"} selected — click to choose`;
        document.querySelectorAll("#powerbi-column-summary").forEach((target) => { target.innerText = summary; target.title = title; });
        const countTarget = $("#powerbi-columns-count");
        if (countTarget) countTarget.innerText = summary;
    }

    function updatePowerBIColumnCacheUpdatedAt(value) {
        powerbiPoColumnsUpdatedAt = value || null;
        const label = $("#powerbi-columns-updated");
        const button = $("#btn-refresh-powerbi-columns");
        if (!label || !button) return;
        if (powerbiPoColumnsWarning) {
            label.innerText = powerbiPoColumnsWarning;
            button.title = powerbiPoColumnsWarning;
            return;
        }
        if (!powerbiPoColumnsUpdatedAt) {
            label.innerText = "Catalog has not been refreshed yet.";
            button.title = "Refresh the PO dataset field catalog.";
            return;
        }
        const parsed = new Date(powerbiPoColumnsUpdatedAt);
        const formatted = Number.isNaN(parsed.getTime()) ? powerbiPoColumnsUpdatedAt : parsed.toLocaleString();
        label.innerText = `Last updated: ${formatted}`;
        button.title = `Last updated: ${formatted}. Click to refresh.`;
    }

    function renderPowerBIColumnOptions() {
        const container = $("#powerbi-column-options");
        if (!container) return;
        if (!powerbiPoColumns.length) {
            container.innerHTML = '<div class="empty-state">The PO dataset field catalog is unavailable.</div>';
            return;
        }
        let lastGroup = "";
        container.innerHTML = powerbiPoColumns.map((column) => {
            const group = column.semantic_group || column.group || "Other";
            const groupHeading = group === lastGroup ? "" : `<div class="powerbi-column-group">${escapeHtml(group)}</div>`;
            lastGroup = group;
            const checked = powerbiColumnDraft.has(column.key);
            const required = Boolean(column.required);
            const origin = [column.table_label || column.table, column.source, column.data_type || column.type]
                .filter(Boolean)
                .join(" · ");
            const flags = [required ? "required" : "", column.hidden ? "hidden" : ""].filter(Boolean).join(" · ");
            return `${groupHeading}<label class="powerbi-column-option"><input type="checkbox" data-powerbi-column="${escapeHtml(column.key)}" ${checked ? "checked" : ""} ${required ? "disabled" : ""}><span><strong>${escapeHtml(column.label)}</strong><small>${escapeHtml(origin)}${flags ? ` · ${flags}` : ""}</small></span></label>`;
        }).join("");
        container.querySelectorAll("input[data-powerbi-column]").forEach((input) => input.addEventListener("change", () => {
            const key = input.dataset.powerbiColumn || "";
            if (input.checked) powerbiColumnDraft.add(key);
            else powerbiColumnDraft.delete(key);
            updatePowerBIColumnSummary();
        }));
        updatePowerBIColumnSummary();
    }

    async function loadPowerBIColumns(forceRefresh = false) {
        if (!forceRefresh && powerbiPoColumns.length) return true;
        const method = forceRefresh ? "refresh_powerbi_po_columns" : "get_powerbi_po_columns";
        if (!hasApi(method)) return false;
        const previousSelected = powerbiSelectedColumns.size ? new Set(powerbiSelectedColumns) : readPersistedPowerBIColumns();
        const result = await api()[method]();
        if (!result.success) throw new Error(result.error || "Could not load the PO dataset field catalog.");
        powerbiPoColumns = Array.isArray(result.columns) ? result.columns : [];
        powerbiPoColumnsWarning = result.warning || "";
        updatePowerBIColumnCacheUpdatedAt(result.updated_at);
        const availableKeys = new Set(powerbiPoColumns.map((column) => column.key));
        let persistedSelection = previousSelected;
        if (!powerbiColumnSelectionLoaded) {
            powerbiColumnSelectionLoaded = true;
            if (hasApi("get_powerbi_po_column_selection")) {
                try {
                    const selection = await api().get_powerbi_po_column_selection();
                    if (selection?.success && Array.isArray(selection.columns) && selection.columns.length) {
                        persistedSelection = new Set(selection.columns.map(String));
                    }
                } catch (_) {
                    // Continue with the browser fallback when the DB bridge is unavailable.
                }
            }
        }
        const preserved = [...persistedSelection].filter((key) => availableKeys.has(key));
        const defaults = powerbiPoColumns.filter((column) => column.default || column.required).map((column) => column.key);
        powerbiSelectedColumns = new Set(preserved.length ? preserved : defaults);
        await persistPowerBIColumns();
        updatePowerBIColumnSummary();
        return Boolean(powerbiPoColumns.length);
    }

    async function refreshPowerBIColumns() {
        const button = $("#btn-refresh-powerbi-columns");
        if (!hasApi("refresh_powerbi_po_columns") || button?.dataset.busy === "1") return;
        setButtonBusy(button, true);
        button.disabled = true;
        try {
            const loaded = await loadPowerBIColumns(true);
            if (!loaded) throw new Error("The PO dataset field catalog is unavailable.");
            powerbiColumnDraft = new Set(powerbiSelectedColumns);
            renderPowerBIColumnOptions();
            setPowerBIMessage(powerbiPoColumnsWarning || "PO dataset field catalog refreshed.", powerbiPoColumnsWarning ? "powerbi-status-invalid" : "powerbi-status-valid");
        } catch (error) {
            setPowerBIMessage(error.message || "Could not refresh the PO dataset field catalog.", "powerbi-status-invalid");
        } finally {
            setButtonBusy(button, false);
            button.disabled = false;
        }
    }

    async function openPowerBIColumnModal() {
        const modal = $("#powerbi-columns-modal");
        if (!modal) return;
        modal.hidden = false;
        powerbiColumnDraft = new Set(powerbiSelectedColumns);
        const options = $("#powerbi-column-options");
        if (options) options.innerHTML = '<div class="empty-state">Loading PO dataset fields…</div>';
        try {
            await loadPowerBIColumns();
            powerbiColumnDraft = new Set(powerbiSelectedColumns);
            renderPowerBIColumnOptions();
            $("#btn-apply-powerbi-columns")?.focus();
        } catch (error) {
            if (options) options.innerHTML = `<div class="empty-state">${escapeHtml(error.message || "Could not load PO dataset fields.")}</div>`;
        }
    }

    function closePowerBIColumnModal() {
        const modal = $("#powerbi-columns-modal");
        if (modal) modal.hidden = true;
    }

    async function applyPowerBIColumns() {
        const checked = [...document.querySelectorAll("input[data-powerbi-column]:checked")].map((input) => input.dataset.powerbiColumn).filter(Boolean);
        const required = powerbiPoColumns.filter((column) => column.required).map((column) => column.key);
        powerbiSelectedColumns = new Set([...required, ...checked]);
        await persistPowerBIColumns();
        closePowerBIColumnModal();
        updatePowerBIColumnSummary();
        renderPowerBIPreview();
        if (powerbiPreviewRows.length && hasApi("preview_powerbi_pos")) await previewPowerBIPOs();
    }

    function groupedPowerBIPreviewRows() {
        const groups = new Map();
        powerbiPreviewRows.forEach((row) => {
            const po = String(row.po_number || "").trim();
            if (!po) return;
            if (!groups.has(po)) groups.set(po, { po_number: po, rows: [], l3: new Set() });
            const group = groups.get(po);
            group.rows.push(row);
            if (row.management_unit_l3) group.l3.add(row.management_unit_l3);
        });
        return [...groups.values()];
    }

    function groupedPowerBIColumnValue(group, column) {
        if (column.key === "po_number") return group.po_number;
        const values = group.rows.map((row) => row[column.key]).filter((value) => value !== null && value !== undefined && String(value).trim() !== "");
        if (!values.length) return "—";
        if (column.type === "currency") {
            const total = values.reduce((sum, value) => sum + (finitePowerBINumber(value) || 0), 0);
            return formatPowerBIEur(total);
        }
        if (column.key === "supplier_uu") {
            return [...new Set(values.map(String))].sort((left, right) => left.length - right.length || left.localeCompare(right))[0];
        }
        return [...new Set(values.map(String))].join(" · ");
    }

    function renderPowerBIPreviewTable(bodyId, headId) {
        const body = $(bodyId);
        const head = $(headId);
        if (!body || !head) return;
        const columns = powerBISelectedColumnSpecs();
        head.innerHTML = `<th><input type="checkbox" data-powerbi-select-all aria-label="Select all POs"></th>${columns.map((column) => `<th title="${escapeHtml(column.source || "")}">${escapeHtml(column.label)}</th>`).join("")}`;
        const grouped = groupedPowerBIPreviewRows();
        const colspan = columns.length + 1;
        if (!grouped.length) {
            body.innerHTML = `<tr><td colspan="${colspan}" class="empty-state">${bodyId.includes("new-run") ? "Open PO Source & Selection to load a Power BI preview." : "No POs matched the selected filters."}</td></tr>`;
            return;
        }
        body.innerHTML = grouped.map((group) => {
            const excluded = powerbiExcludedPOs.has(group.po_number);
            const cells = columns.map((column) => `<td>${escapeHtml(groupedPowerBIColumnValue(group, column))}${column.key === "po_number" && group.l3.size > 1 ? '<small class="powerbi-multiple-l3">Multiple L3</small>' : ""}</td>`).join("");
            return `<tr class="${excluded ? "powerbi-po-excluded" : ""}"><td><input type="checkbox" data-powerbi-po="${escapeHtml(group.po_number)}" ${excluded ? "" : "checked"} aria-label="Include ${escapeHtml(group.po_number)}"></td>${cells}</tr>`;
        }).join("");
        body.querySelectorAll("input[data-powerbi-po]").forEach((input) => input.addEventListener("change", () => {
            const po = input.dataset.powerbiPo || "";
            if (input.checked) powerbiExcludedPOs.delete(po);
            else powerbiExcludedPOs.add(po);
            renderPowerBIPreview();
        }));
        const selectAll = head.querySelector("input[data-powerbi-select-all]");
        if (selectAll) {
            const included = grouped.filter((group) => !powerbiExcludedPOs.has(group.po_number)).length;
            selectAll.checked = grouped.length > 0 && included === grouped.length;
            selectAll.indeterminate = included > 0 && included < grouped.length;
            selectAll.addEventListener("change", () => {
                grouped.forEach((group) => {
                    if (selectAll.checked) powerbiExcludedPOs.delete(group.po_number);
                    else powerbiExcludedPOs.add(group.po_number);
                });
                renderPowerBIPreview();
            });
        }
        initializeSortableTables();
    }

    function renderPowerBIGrir() {
        const empty = $("#powerbi-grir-empty");
        const dashboard = $("#powerbi-grir-dashboard");
        if (!empty || !dashboard) return;
        if (!powerbiGrirLoaded) {
            empty.hidden = false;
            empty.innerText = "Fetch Data to load the GRIR comparison.";
            dashboard.hidden = true;
            return;
        }
        const selected = new Set(selectedPowerBIPOs());
        const rows = powerbiGrirRows.filter((row) => selected.has(String(row.po_number || "")));
        if (!rows.length) {
            empty.hidden = false;
            empty.innerText = "Select at least one PO to display the GRIR comparison.";
            dashboard.hidden = true;
            return;
        }
        empty.hidden = true;
        dashboard.hidden = false;
        const summary = rows.reduce((result, row) => {
            const goods = Number(row.goods_received_eur) || 0;
            const invoices = Number(row.invoice_received_eur) || 0;
            result.goods += goods;
            result.invoices += invoices;
            result.variance += Number(row.variance_eur) || goods - invoices;
            result.statuses[row.status] = (result.statuses[row.status] || 0) + 1;
            return result;
        }, { goods: 0, invoices: 0, variance: 0, statuses: {} });
        $("#powerbi-grir-pos").innerText = String(rows.length);
        $("#powerbi-grir-goods").innerText = formatPowerBIEur(summary.goods, true);
        $("#powerbi-grir-invoices").innerText = formatPowerBIEur(summary.invoices, true);
        $("#powerbi-grir-variance").innerText = formatPowerBIEur(summary.variance, true);
        $("#powerbi-grir-no-invoice").innerText = String(summary.statuses.no_invoice || 0);

        const valueBars = [
            ["Goods Received", summary.goods, "goods"],
            ["Invoice Received", summary.invoices, "invoice"],
            ["Variance (absolute)", Math.abs(summary.variance), "variance"],
        ];
        const valueMax = Math.max(...valueBars.map((item) => item[1]), 1);
        $("#powerbi-grir-value-bars").innerHTML = valueBars.map(([label, value, kind]) => `<div class="powerbi-grir-bar-row"><span>${label}</span><div class="powerbi-grir-bar-track"><div class="powerbi-grir-bar-fill ${kind}" style="width:${Math.min(100, Math.max(0, value / valueMax * 100))}%"></div></div><strong class="powerbi-grir-bar-value">${formatPowerBIEur(value, true)}</strong></div>`).join("");

        const statusBars = [
            ["No invoice", "no_invoice"],
            ["GR > Invoice", "goods_received_gt_invoice"],
            ["Invoice > GR", "invoice_received_gt_goods"],
            ["Balanced", "balanced"],
        ];
        const statusMax = Math.max(...statusBars.map(([, status]) => summary.statuses[status] || 0), 1);
        $("#powerbi-grir-status-bars").innerHTML = statusBars.map(([label, status]) => {
            const count = summary.statuses[status] || 0;
            return `<div class="powerbi-grir-bar-row"><span>${label}</span><div class="powerbi-grir-bar-track"><div class="powerbi-grir-bar-fill ${status}" style="width:${count / statusMax * 100}%"></div></div><strong class="powerbi-grir-bar-value">${count}</strong></div>`;
        }).join("");

        const body = $("#powerbi-grir-rows");
        body.innerHTML = rows.slice().sort((left, right) => Math.abs(Number(right.variance_eur) || 0) - Math.abs(Number(left.variance_eur) || 0)).map((row) => {
            const status = row.status || "balanced";
            return `<tr><td><strong>${escapeHtml(row.po_number)}</strong></td><td>${formatPowerBIEur(row.goods_received_eur)}</td><td>${formatPowerBIEur(row.invoice_received_eur)}</td><td>${formatPowerBIEur(row.variance_eur)}</td><td>${escapeHtml(row.invoice_count || 0)}</td><td><span class="powerbi-grir-status ${status}">${powerBIGrirStatusLabels[status] || status}</span></td></tr>`;
        }).join("");
    }

    const powerBIFxStatusLabels = {
        fx_aligned: "FX aligned",
        fx_variance: "FX variance",
        no_invoice_fx: "Invoice FX unavailable",
        po_fx_unavailable: "PO FX unavailable",
        no_fx: "FX unavailable",
    };

    function renderPowerBIFx() {
        const empty = $("#powerbi-fx-empty");
        const dashboard = $("#powerbi-fx-dashboard");
        if (!empty || !dashboard) return;
        if (!powerbiGrirFxLoaded) {
            empty.hidden = false;
            empty.innerText = "Fetch Data to load the FX comparison.";
            dashboard.hidden = true;
            return;
        }
        const selected = new Set(selectedPowerBIPOs());
        const rows = powerbiGrirFxRows.filter((row) => selected.has(String(row.po_number || "")));
        if (!rows.length) {
            empty.hidden = false;
            empty.innerText = "Select at least one PO to display the FX comparison.";
            dashboard.hidden = true;
            return;
        }
        empty.hidden = true;
        dashboard.hidden = false;
        const invoices = rows.flatMap((row) => Array.isArray(row.invoices) ? row.invoices : []);
        const fxInvoices = invoices.filter((row) => finitePowerBINumber(row.fx_impact_eur) !== null);
        const grirTotal = sumPowerBIFinite(rows, "grir_total_eur");
        const fxImpact = sumPowerBIFinite(fxInvoices, "fx_impact_eur");
        const grirExFxValues = rows.filter((row) => finitePowerBINumber(row.grir_ex_fx_eur) !== null);
        const grirExFx = sumPowerBIFinite(grirExFxValues, "grir_ex_fx_eur");
        const statusCounts = invoices.reduce((counts, row) => {
            const status = row.status || "no_fx";
            counts[status] = (counts[status] || 0) + 1;
            return counts;
        }, {});
        $("#powerbi-fx-invoices").innerText = String(invoices.length);
        $("#powerbi-fx-grir").innerText = formatPowerBIEur(grirTotal, true);
        $("#powerbi-fx-impact").innerText = fxInvoices.length ? formatPowerBIEur(fxImpact, true) : "—";
        $("#powerbi-fx-ex-grir").innerText = grirExFxValues.length ? formatPowerBIEur(grirExFx, true) : "—";
        $("#powerbi-fx-variance-count").innerText = String(statusCounts.fx_variance || 0);
        $("#powerbi-fx-sow").innerText = "Unavailable";

        const valueBars = [
            ["GRIR total", Math.abs(grirTotal), "grir"],
            ["FX impact", Math.abs(fxImpact), "fx"],
            ["GRIR excluding FX", Math.abs(grirExFx), "ex-grir"],
        ];
        const valueMax = Math.max(...valueBars.map((item) => item[1]), 1);
        $("#powerbi-fx-value-bars").innerHTML = valueBars.map(([label, value, kind]) => (
            "<div class=\"powerbi-fx-bar-row\"><span>" + label + "</span><div class=\"powerbi-fx-bar-track\"><div class=\"powerbi-fx-bar-fill " + kind + "\" style=\"width:" + Math.min(100, Math.max(0, value / valueMax * 100)) + "%\"></div></div><strong class=\"powerbi-fx-bar-value\">" + formatPowerBIEur(value, true) + "</strong></div>"
        )).join("");

        const statusBars = [
            ["FX aligned", "fx_aligned", "aligned"],
            ["FX variance", "fx_variance", "variance"],
            ["FX unavailable", "no_fx", "unavailable"],
        ];
        const statusMax = Math.max(...statusBars.map(([, status]) => statusCounts[status] || 0), 1);
        $("#powerbi-fx-status-bars").innerHTML = statusBars.map(([label, status, kind]) => {
            const count = status === "no_fx"
                ? (statusCounts.no_fx || 0) + (statusCounts.no_invoice_fx || 0) + (statusCounts.po_fx_unavailable || 0)
                : statusCounts[status] || 0;
            return "<div class=\"powerbi-fx-bar-row\"><span>" + label + "</span><div class=\"powerbi-fx-bar-track\"><div class=\"powerbi-fx-bar-fill " + kind + "\" style=\"width:" + count / statusMax * 100 + "%\"></div></div><strong class=\"powerbi-fx-bar-value\">" + count + "</strong></div>";
        }).join("");

        const body = $("#powerbi-fx-rows");
        body.innerHTML = rows.slice().sort((left, right) => Math.abs(Number(right.grir_total_eur) || 0) - Math.abs(Number(left.grir_total_eur) || 0)).map((row) => {
            const po = String(row.po_number || "");
            const expanded = powerbiGrirFxExpanded.has(po);
            const poAvailable = row.po_fx_rate !== null && row.po_fx_rate !== undefined;
            const poStatus = poAvailable ? "fx_aligned" : "po_fx_unavailable";
            const poLabel = poAvailable ? "PO FX available" : "PO FX unavailable";
            const invoiceRows = (row.invoices || []).map((invoice) => {
                const status = invoice.status || "no_fx";
                const detail = [invoice.invoice_number || "Invoice", invoice.accounting_document_number ? "Doc " + invoice.accounting_document_number : ""].filter(Boolean).join(" · ");
                return "<tr class=\"powerbi-fx-invoice-row\" data-powerbi-fx-detail=\"" + escapeHtml(po) + "\"" + (expanded ? "" : " hidden") + "><td></td><td><span class=\"powerbi-fx-indent\">" + escapeHtml(detail) + "</span></td><td>" + formatPowerBIEur(invoice.reporting_eur) + "</td><td>" + (invoice.fx_impact_eur === null || invoice.fx_impact_eur === undefined ? "—" : formatPowerBIEur(invoice.fx_impact_eur)) + "</td><td>—</td><td class=\"powerbi-fx-rate\">" + formatPowerBIRate(invoice.invoice_fx_rate) + "</td><td><span class=\"powerbi-fx-status " + status.replaceAll("_", "-") + "\">" + (powerBIFxStatusLabels[status] || status) + "</span></td></tr>";
            }).join("");
            return "<tr class=\"powerbi-fx-po-row\"><td><button class=\"powerbi-fx-toggle\" type=\"button\" data-powerbi-fx-toggle=\"" + escapeHtml(po) + "\" aria-expanded=\"" + (expanded ? "true" : "false") + "\" aria-label=\"" + (expanded ? "Collapse " : "Expand ") + escapeHtml(po) + "\">" + (expanded ? "−" : "+") + "</button></td><td><strong>" + escapeHtml(po) + "</strong></td><td>" + formatPowerBIEur(row.grir_total_eur) + "</td><td>" + (row.fx_impact_eur === null || row.fx_impact_eur === undefined ? "—" : formatPowerBIEur(row.fx_impact_eur)) + "</td><td class=\"powerbi-fx-rate\">" + formatPowerBIRate(row.po_fx_rate) + "</td><td class=\"powerbi-fx-rate\">" + formatPowerBIRate(row.goods_received_fx_rate) + "</td><td><span class=\"powerbi-fx-status " + poStatus.replaceAll("_", "-") + "\">" + poLabel + "</span></td></tr>" + invoiceRows;
        }).join("");
        body.querySelectorAll("button[data-powerbi-fx-toggle]").forEach((button) => button.addEventListener("click", () => {
            const po = button.dataset.powerbiFxToggle || "";
            if (powerbiGrirFxExpanded.has(po)) powerbiGrirFxExpanded.delete(po);
            else powerbiGrirFxExpanded.add(po);
            renderPowerBIFx();
        }));
    }

    async function loadPowerBIFx() {
        const button = $("#btn-powerbi-fx");
        const poNumbers = selectedPowerBIPOs();
        if (!poNumbers.length || !hasApi("analyze_powerbi_grir_fx") || button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        button.disabled = true;
        setPowerBIMessage("Loading FX analysis…");
        try {
            const result = await api().analyze_powerbi_grir_fx(poNumbers);
            if (!result.success) throw new Error(result.error || "Could not load FX analysis.");
            powerbiGrirFxRows = Array.isArray(result.rows) ? result.rows : [];
            powerbiGrirFxExpanded.clear();
            powerbiGrirFxLoaded = true;
            renderPowerBIFx();
            setPowerBIMessage("FX analysis loaded for " + powerbiGrirFxRows.length + " PO(s).", "powerbi-status-valid");
        } catch (error) {
            powerbiGrirFxLoaded = false;
            renderPowerBIFx();
            setPowerBIMessage(error.message || "Could not load FX analysis.", "powerbi-status-invalid");
        } finally {
            button.disabled = !powerbiPreviewRows.length;
            setButtonBusy(button, false);
        }
    }

    async function loadPowerBIGrir() {
        const button = $("#btn-powerbi-grir");
        const poNumbers = selectedPowerBIPOs();
        if (!poNumbers.length || !hasApi("analyze_powerbi_grir") || button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        button.disabled = true;
        setPowerBIMessage("Loading GRIR analysis…");
        try {
            const result = await api().analyze_powerbi_grir(poNumbers);
            if (!result.success) throw new Error(result.error || "Could not load GRIR analysis.");
            powerbiGrirRows = Array.isArray(result.rows) ? result.rows : [];
            powerbiGrirLoaded = true;
            renderPowerBIGrir();
            setPowerBIMessage(`GRIR analysis loaded for ${powerbiGrirRows.length} PO(s).`, "powerbi-status-valid");
        } catch (error) {
            powerbiGrirLoaded = false;
            renderPowerBIGrir();
            setPowerBIMessage(error.message || "Could not load GRIR analysis.", "powerbi-status-invalid");
        } finally {
            button.disabled = !powerbiPreviewRows.length;
            setButtonBusy(button, false);
        }
    }

    function renderPowerBIPreview() {
        const grouped = groupedPowerBIPreviewRows();
        $("#powerbi-unique-pos").innerText = String(grouped.length);
        $("#powerbi-record-count").innerText = String(powerbiPreviewRows.length);
        $("#powerbi-multi-l3-count").innerText = String(grouped.filter((group) => group.l3.size > 1).length);
        updatePowerBIColumnSummary();
        renderPowerBIPreviewTable("#powerbi-po-preview", "#powerbi-po-preview-head");
        updateInputMethodUI();
        if (!grouped.length) {
            $("#btn-powerbi-grir").disabled = true;
            $("#btn-powerbi-fx").disabled = true;
            powerbiGrirRows = [];
            powerbiGrirLoaded = false;
            powerbiGrirFxRows = [];
            powerbiGrirFxLoaded = false;
            powerbiGrirFxExpanded.clear();
            renderPowerBIGrir();
            renderPowerBIFx();
            return;
        }
        $("#btn-powerbi-grir").disabled = false;
        $("#btn-powerbi-fx").disabled = false;
        renderPowerBIGrir();
        renderPowerBIFx();
    }

    async function previewPowerBIPOs() {
        const codes = [...powerbiSelectedSuppliers.keys()];
        if (!codes.length) {
            setPowerBIMessage("Add at least one supplier before previewing POs.", "powerbi-status-invalid");
            return;
        }
        const selectedPeriods = [...powerbiSelectedDatePeriods].sort();
        const button = $("#btn-powerbi-preview");
        const cancelButton = $("#btn-powerbi-cancel");
        const progress = $("#powerbi-query-progress");
        const paths = [...powerbiSelectedPathKeys].map((key) => powerbiPathByKey.get(key)).filter(Boolean);
        const queryDiagnostics = startPowerBIQueryDiagnostics(codes, paths, selectedPeriods, [...powerbiSelectedFamilies]);
        powerbiQueryCancelled = false;
        powerbiQueryDiagnostics = queryDiagnostics;
        renderPowerBIQueryDiagnostics();
        setButtonBusy(button, true);
        button.disabled = true;
        if (cancelButton) {
            cancelButton.hidden = false;
            cancelButton.disabled = false;
            cancelButton.innerText = "Cancel";
        }
        const rowsByIdentity = new Map();
        // Remove the previous result immediately. A new filter query must not
        // leave an old PO list visible while the API is running or after it
        // fails.
        powerbiPreviewRows = [];
        powerbiExcludedPOs.clear();
        powerbiGrirRows = [];
        powerbiGrirLoaded = false;
        powerbiGrirFxRows = [];
        powerbiGrirFxLoaded = false;
        powerbiGrirFxExpanded.clear();
        renderPowerBIPreview();
        setPowerBIMessage("Fetching PO data…");
        try {
            const chunksByQuarter = new Map();
            selectedPeriods.forEach((period) => {
                const year = period.slice(0, 4);
                const month = Number(period.slice(5, 7));
                const quarter = Math.floor((month - 1) / 3) + 1;
                const quarterKey = `${year}-Q${quarter}`;
                if (!chunksByQuarter.has(quarterKey)) chunksByQuarter.set(quarterKey, []);
                chunksByQuarter.get(quarterKey).push(period);
            });
            const chunks = selectedPeriods.length ? [...chunksByQuarter.values()] : [[]];
            if (progress) {
                progress.hidden = chunks.length <= 1;
                progress.max = chunks.length;
                progress.value = 0;
            }
            let firstResult = null;
            logToConsole("System", `Power BI PO preview: ${codes.length} supplier code(s), ${paths.length} MU path(s), ${selectedPeriods.length ? `${selectedPeriods.length} month(s)` : "all PO Creation Dates"} in ${chunks.length} chunk(s)`);
            for (let index = 0; index < chunks.length; index += 1) {
                if (powerbiQueryCancelled) break;
                const result = await api().preview_powerbi_pos("", codes, paths, [...powerbiSelectedColumns], chunks[index], [...powerbiSelectedFamilies]);
                mergePowerBIQueryDiagnostics(queryDiagnostics, result.query_diagnostics);
                powerbiQueryDiagnostics = queryDiagnostics;
                renderPowerBIQueryDiagnostics();
                if (!result.success) {
                    if (powerbiQueryCancelled) break;
                    throw new Error(result.error || "Could not preview POs.");
                }
                firstResult = firstResult || result;
                (result.rows || []).forEach((row) => rowsByIdentity.set(JSON.stringify(row), row));
                if (progress) progress.value = index + 1;
                setPowerBIMessage(`Fetching PO data… ${index + 1}/${chunks.length} chunk(s) — ${firstResult?.unique_pos || 0} PO(s) so far`);
            }
            if (powerbiQueryCancelled && !rowsByIdentity.size) {
                powerbiPreviewRows = [];
                powerbiExcludedPOs.clear();
                powerbiGrirRows = [];
                powerbiGrirLoaded = false;
                powerbiGrirFxRows = [];
                powerbiGrirFxLoaded = false;
                powerbiGrirFxExpanded.clear();
                renderPowerBIPreview();
                setPowerBIMessage("Query cancelled. No PO data was fetched.", "powerbi-status-invalid");
                return;
            }
            if (Array.isArray(firstResult?.columns) && firstResult.columns.length) powerbiSelectedColumns = new Set(firstResult.columns);
            powerbiPreviewRows = [...rowsByIdentity.values()];
            powerbiQueryDiagnostics = queryDiagnostics;
            renderPowerBIQueryDiagnostics();
            powerbiExcludedPOs.clear();
            powerbiGrirRows = [];
            powerbiGrirLoaded = false;
            powerbiGrirFxRows = [];
            powerbiGrirFxLoaded = false;
            powerbiGrirFxExpanded.clear();
            renderPowerBIPreview();
            powerbiSourceMetadata = {
                source: "Power BI PO Mass Download Dataset",
                filters: {
                    supplier_uu: codes,
                    management_unit_paths: paths,
                    date_periods: selectedPeriods,
                    family_names: [...powerbiSelectedFamilies],
                    date_range: { min_date: powerbiDateRange.min_date, max_date: powerbiDateRange.max_date },
                    chunk_count: chunks.length,
                },
                found_pos: new Set(powerbiPreviewRows.map((row) => String(row.po_number || "").trim()).filter(Boolean)).size,
            };
            if (powerbiQueryCancelled) {
                setPowerBIMessage(`Query cancelled — ${groupedPowerBIPreviewRows().length} PO(s) from the completed chunk(s).`, "powerbi-status-valid");
            } else {
                setPowerBIMessage(`${groupedPowerBIPreviewRows().length} unique PO(s) found in ${powerbiPreviewRows.length} record(s).`, "powerbi-status-valid");
                await loadPowerBIGrir();
                await loadPowerBIFx();
            }
        } catch (error) {
            powerbiQueryDiagnostics = queryDiagnostics;
            renderPowerBIQueryDiagnostics();
            if (!powerbiQueryCancelled) {
                logToConsole("Error", `Power BI PO preview failed: ${error.message || error}`);
                setPowerBIMessage(error.message || "Could not preview POs.", "powerbi-status-invalid");
            }
        } finally {
            if (progress) progress.hidden = true;
            if (cancelButton) {
                cancelButton.hidden = true;
                cancelButton.disabled = false;
                cancelButton.innerText = "Cancel";
            }
            button.disabled = false;
            setButtonBusy(button, false);
        }
    }

    async function preparePowerBIInputForNewRun() {
        const rows = powerbiPreviewRows.filter((row) => !powerbiExcludedPOs.has(String(row.po_number || "")));
        if (!rows.length) {
            setPowerBIMessage("Select at least one PO before continuing.", "powerbi-status-invalid");
            return false;
        }
        if (!hasApi("prepare_powerbi_input")) {
            setPowerBIMessage("The Power BI input is available in the desktop app.", "powerbi-status-invalid");
            return false;
        }
        try {
            const filters = powerbiSourceMetadata?.filters || {};
            const result = await api().prepare_powerbi_input(rows, filters, [...powerbiSelectedColumns]);
            if (!result.success) throw new Error(result.error || "Could not prepare the Power BI input.");
            setFile(result.path, String(result.path).split(/[\\/]/).pop(), undefined, "powerbi");
            preparePowerBIHierarchySuggestions(rows);
            powerbiSourceMetadata = result.source_metadata || { source: "Power BI PO Mass Download Dataset", filters };
            $("#selected-filesize").innerText = "Generated from Power BI · internal snapshot";
            $("#file-state-text").innerText = "Power BI snapshot ready to validate";
            setPowerBIMessage(`${result.unique_pos} selected PO(s) are ready for the New run.`, "powerbi-status-valid");
            logToConsole("Success", `Power BI snapshot prepared with ${result.unique_pos} selected PO(s).`);
            return true;
        } catch (error) {
            setPowerBIMessage(error.message || "Could not prepare the Power BI input.", "powerbi-status-invalid");
            return false;
        }
    }

    function formatTimesheetNumber(value, digits = 2) {
        const number = Number(value || 0);
        return number.toLocaleString("en-US", { maximumFractionDigits: digits });
    }

    function timesheetStatusLabel(status) {
        return {
            tm: "T&M",
            fixed_price: "Not applicable · Fixed Price",
            classification_pending: "Classification pending",
        }[status] || status || "Unknown";
    }

    function renderTimesheet(analysis) {
        const status = $("#timesheet-source-status");
        const source = analysis?.source || {};
        if (!analysis) {
            status.innerHTML = '<span class="status-dot unauthenticated"></span><span>No timesheet snapshot loaded</span>';
            $("#timesheet-rows").innerHTML = '<tr><td colspan="8" class="empty-state">No timesheet snapshot loaded.</td></tr>';
            return;
        }
        status.innerHTML = `<span class="status-dot authenticated"></span><span>${escapeHtml(source.name || "Timesheet snapshot loaded")}</span>`;
        $("#timesheet-source-path").value = source.path || timesheetSelectedPath || "";
        $("#timesheet-source-name").innerText = source.name || "Timesheet workbook";
        $("#timesheet-sheet-name").innerText = `Sheet: ${source.sheet || "—"}`;
        $("#timesheet-last-updated").innerText = `Last updated: ${source.cache_updated_at || source.updated_at || "—"}`;
        const suppliers = Array.isArray(analysis.available_suppliers)
            ? analysis.available_suppliers
            : (analysis.summary?.suppliers || []);
        const supplierSelect = $("#timesheet-supplier-filter");
        const selectedSupplier = analysis.filters?.supplier || supplierSelect.value || "";
        supplierSelect.innerHTML = '<option value="">All suppliers</option>' + suppliers.map((supplier) => `<option value="${escapeHtml(supplier)}">${escapeHtml(supplier)}</option>`).join("");
        supplierSelect.value = suppliers.includes(selectedSupplier) ? selectedSupplier : "";

        const summary = analysis.summary || {};
        const exceptions = analysis.exception_summary || {};
        $("#timesheet-tm-pwo").innerText = formatTimesheetNumber(summary.tm_pwo_count, 0);
        $("#timesheet-fixed-pwo").innerText = formatTimesheetNumber(exceptions.fixed_price_pwo_count ?? summary.fixed_price_pwo_count, 0);
        $("#timesheet-pending-classification").innerText = formatTimesheetNumber(exceptions.classification_pending_pwo_count ?? summary.classification_pending_pwo_count, 0);
        $("#timesheet-unmapped").innerText = formatTimesheetNumber(exceptions.unmapped_pwo_rows ?? summary.unmapped_pwo_rows, 0);
        $("#timesheet-days").innerText = formatTimesheetNumber(summary.tm_days, 2);
        $("#timesheet-fees").innerText = formatTimesheetNumber(summary.tm_fees, 2);
        $("#timesheet-resources").innerText = formatTimesheetNumber(summary.resource_assignments, 0);
        $("#timesheet-suppliers").innerText = formatTimesheetNumber(summary.supplier_count, 0);
        const fixed = Number(exceptions.fixed_price_pwo_count || 0);
        const pending = Number(exceptions.classification_pending_pwo_count || 0);
        const unmapped = Number(exceptions.unmapped_pwo_rows || 0);
        $("#timesheet-exception-summary").innerText = `${fixed} Fixed Price PWO(s) marked Not applicable · ${pending} PWO(s) need billing classification · ${unmapped} row(s) have no PWO key.`;

        const rows = Array.isArray(analysis.rows) ? analysis.rows : [];
        const body = $("#timesheet-rows");
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="8" class="empty-state">No rows match the current supplier and scope filters.</td></tr>';
        } else {
            body.innerHTML = rows.map((row) => `<tr><td>${escapeHtml(row.supplier)}</td><td><strong>${escapeHtml(row.pwo)}</strong></td><td>${escapeHtml(row.billing_type || "—")}</td><td><span class="timesheet-status ${escapeHtml(String(row.classification || "unknown").replaceAll("_", "-"))}">${escapeHtml(timesheetStatusLabel(row.classification))}</span></td><td>${escapeHtml(row.period_start || "—")} → ${escapeHtml(row.period_end || "—")}</td><td>${formatTimesheetNumber(row.resource_count, 0)}</td><td>${formatTimesheetNumber(row.days, 2)}</td><td>${formatTimesheetNumber(row.fees, 2)}</td></tr>`).join("");
        }
    }

    async function loadTimesheetScreen() {
        if (timesheetScreenLoaded || !hasApi("get_timesheet_analysis_cache")) return;
        timesheetScreenLoaded = true;
        try {
            const result = await api().get_timesheet_analysis_cache();
            if (!result.success) throw new Error(result.error || "Could not load timesheet cache.");
            timesheetAnalysis = result.analysis || null;
            if (timesheetAnalysis?.source?.path) timesheetSelectedPath = timesheetAnalysis.source.path;
            renderTimesheet(timesheetAnalysis);
        } catch (error) {
            $("#timesheet-source-status").innerHTML = `<span class="status-dot unauthenticated"></span><span>${escapeHtml(error.message || "Could not load timesheet cache.")}</span>`;
        }
    }

    async function selectTimesheetFile() {
        if (!hasApi("select_timesheet_file")) return;
        const result = await api().select_timesheet_file();
        if (!result.success || !result.path) return;
        timesheetSelectedPath = result.path;
        $("#timesheet-source-path").value = result.path;
        $("#btn-timesheet-load").disabled = false;
        $("#timesheet-source-status").innerHTML = '<span class="status-dot authenticating"></span><span>Workbook selected; load to update the snapshot</span>';
    }

    async function loadTimesheetFile() {
        if (!timesheetSelectedPath || !hasApi("load_timesheet_file")) return;
        const button = $("#btn-timesheet-load");
        setButtonBusy(button, true);
        button.disabled = true;
        button.innerText = "Loading…";
        try {
            const result = await api().load_timesheet_file(timesheetSelectedPath);
            if (!result.success) throw new Error(result.error || "Could not load the timesheet workbook.");
            timesheetAnalysis = result.analysis;
            renderTimesheet(timesheetAnalysis);
        } catch (error) {
            $("#timesheet-source-status").innerHTML = `<span class="status-dot unauthenticated"></span><span>${escapeHtml(error.message || String(error))}</span>`;
        } finally {
            button.innerText = "Load workbook";
            button.disabled = false;
            setButtonBusy(button, false);
        }
    }

    async function filterTimesheet() {
        if (!timesheetAnalysis || !hasApi("filter_timesheet_analysis")) return;
        const supplier = $("#timesheet-supplier-filter").value;
        const scope = $("#timesheet-scope").value;
        const result = await api().filter_timesheet_analysis(supplier, scope);
        if (result.success) {
            timesheetAnalysis = result.analysis;
            renderTimesheet(timesheetAnalysis);
        }
    }

    function labRelationshipStatus(kind, item) {
        if (kind === "sow") return item.key === "SOW:__unlinked__" ? "Needs SOW key" : "SOW candidate";
        if (kind === "po") {
            if (item.sow_count > 1) return "Multiple SOWs";
            if (item.sow_count === 1) return "One SOW";
            return "SOW missing";
        }
        return item.kind === "invoice" ? "Power BI invoice" : "Captured";
    }

    function labRelationshipStatusClass(status) {
        if (/multiple|missing|needs/i.test(status)) return "warning";
        if (/candidate/i.test(status)) return "candidate";
        return "valid";
    }

    function labRelationshipChildren(po) {
        return [
            ...(Array.isArray(po.documents) ? po.documents : []),
            ...(Array.isArray(po.invoices) ? po.invoices : []),
        ];
    }

    function labRelationshipDetails(item, kind) {
        const details = [];
        if (kind === "sow" && item.commitment_total_eur !== undefined) {
            details.push(`Commitment total ${formatPowerBIEur(item.commitment_total_eur, true)}`);
        }
        if (kind === "po" && item.commitment_value_eur !== undefined) {
            details.push(`Commitment ${formatPowerBIEur(item.commitment_value_eur, true)}`);
        }
        if (kind === "invoice") {
            if (item.reporting_eur !== undefined) details.push(`Reporting ${formatPowerBIEur(item.reporting_eur, true)}`);
            if (item.document_date) details.push(String(item.document_date));
            if (item.accounting_document_number && item.accounting_document_number !== item.invoice_number) {
                details.push(`Accounting ${item.accounting_document_number}`);
            }
        }
        return details.join(" · ");
    }

    function relationshipTreeRow(item, kind, level, childCount, evidence, rowNumber) {
        const expanded = labRelationshipExpanded.has(item.key);
        const status = labRelationshipStatus(kind, item);
        const statusClass = labRelationshipStatusClass(status);
        const toggle = childCount
            ? `<button class="lab-relationship-toggle" type="button" data-lab-rel-toggle="${escapeHtml(item.key)}" aria-expanded="${expanded ? "true" : "false"}" aria-label="${expanded ? "Collapse" : "Expand"} ${escapeHtml(item.label)}">${expanded ? "−" : "+"}</button>`
            : `<span class="lab-relationship-toggle-placeholder" aria-hidden="true"></span>`;
        const typeLabel = kind === "sow" ? "SOW" : kind === "po" ? "PO" : item.kind === "invoice" ? "Invoice" : "Document";
        const details = labRelationshipDetails(item, kind);
        const secondary = [item.company_code, details].filter(Boolean).join(" · ");
        return `<tr class="lab-relationship-row lab-relationship-level-${level} ${kind === "sow" ? "lab-relationship-sow-row" : ""}"><td class="lab-relationship-row-number">${rowNumber}</td><td><div class="lab-relationship-name">${toggle}<span><strong>${escapeHtml(item.label || "Unnamed")}</strong>${secondary ? `<small>${escapeHtml(secondary)}</small>` : ""}</span></div></td><td><span class="lab-relationship-type ${typeLabel.toLowerCase()}">${typeLabel}</span></td><td><span class="lab-relationship-badge ${statusClass}">${escapeHtml(status)}</span></td><td>${childCount ? String(childCount) : "—"}</td><td><small>${escapeHtml(evidence || "—")}</small></td></tr>`;
    }

    function renderLabRelationshipRows() {
        const body = $("#lab-relationship-rows");
        if (!body) return;
        const tree = Array.isArray(labRelationshipData?.tree) ? labRelationshipData.tree : [];
        if (!tree.length) {
            body.innerHTML = '<tr><td colspan="6" class="empty-state">No PO or document records are available for this run.</td></tr>';
            return;
        }
        const rows = [];
        let rowNumber = 1;
        tree.forEach((sow) => {
            const pos = Array.isArray(sow.pos) ? sow.pos : [];
            rows.push(relationshipTreeRow(sow, "sow", 0, pos.length, sow.evidence, rowNumber++));
            if (!labRelationshipExpanded.has(sow.key)) return;
            pos.forEach((po) => {
                const children = labRelationshipChildren(po);
                rows.push(relationshipTreeRow(po, "po", 1, children.length, po.sow_count === 1 ? "one SOW candidate" : "contract key needs review", rowNumber++));
                if (!labRelationshipExpanded.has(po.key)) return;
                children.forEach((child) => rows.push(relationshipTreeRow(child, child.kind === "invoice" ? "invoice" : "document", 2, 0, child.evidence, rowNumber++)));
            });
        });
        body.innerHTML = rows.join("");
        body.querySelectorAll("[data-lab-rel-toggle]").forEach((button) => button.addEventListener("click", () => {
            const key = button.dataset.labRelToggle || "";
            if (labRelationshipExpanded.has(key)) labRelationshipExpanded.delete(key);
            else labRelationshipExpanded.add(key);
            renderLabRelationshipRows();
        }));
    }

    function renderLabRelationshipFindings() {
        const body = $("#lab-relationship-findings");
        if (!body) return;
        const findings = Array.isArray(labRelationshipData?.validation) ? labRelationshipData.validation : [];
        body.innerHTML = findings.length
            ? findings.map((item) => `<div class="lab-relationship-finding ${item.severity === "error" ? "error" : "warning"}"><span class="lab-relationship-finding-severity">${item.severity === "error" ? "Error" : "Warning"}</span><span>${escapeHtml(item.message || "Relationship finding")}</span></div>`).join("")
            : '<div class="empty-state">No relationship findings for this run.</div>';
    }

    function renderLabRelationshipView() {
        const summary = labRelationshipData?.summary || {};
        [
            ["#lab-rel-sows", summary.sows],
            ["#lab-rel-pos", summary.pos],
            ["#lab-rel-invoices", summary.invoices],
            ["#lab-rel-warnings", summary.warnings],
        ].forEach(([selector, value]) => { const target = $(selector); if (target) target.innerText = String(value ?? "—"); });
        renderLabRelationshipRows();
        renderLabRelationshipFindings();
    }

    function setLabRelationshipStatus(message, state = "authenticating") {
        const target = $("#lab-relationship-status");
        if (!target) return;
        target.innerHTML = `<span class="status-dot ${state}"></span><span>${escapeHtml(message)}</span>`;
    }

    async function loadLabRelationships(sessionId = null) {
        if (!hasApi("get_lab_relationships") || labRelationshipLoading) return;
        labRelationshipLoading = true;
        const button = $("#btn-lab-relationship-refresh");
        setButtonBusy(button, true);
        setLabRelationshipStatus("Loading relationship inventory…");
        try {
            const result = await api().get_lab_relationships(sessionId);
            if (!result.success) throw new Error(result.error || "Could not load relationship inventory.");
            labRelationshipData = result;
            labRelationshipExpanded.clear();
            const select = $("#lab-relationship-session-select");
            const sessions = Array.isArray(result.sessions) ? result.sessions : [];
            if (select) {
                select.innerHTML = sessions.map((item) => `<option value="${escapeHtml(item.id)}">Run #${escapeHtml(item.id)} · ${escapeHtml(item.input_file || "input unavailable")} · ${escapeHtml(item.total_pos || 0)} PO(s)</option>`).join("") || '<option value="">No runs available</option>';
                if (result.session?.id) select.value = String(result.session.id);
            }
            renderLabRelationshipView();
            const warnings = Number(result.summary?.warnings || 0);
            setLabRelationshipStatus(warnings ? `${warnings} relationship finding(s) need review.` : "Relationship inventory loaded.", warnings ? "unauthenticated" : "authenticated");
        } catch (error) {
            labRelationshipData = null;
            renderLabRelationshipView();
            setLabRelationshipStatus(error.message || "Could not load relationship inventory.", "unauthenticated");
        } finally {
            labRelationshipLoading = false;
            setButtonBusy(button, false);
        }
    }

    function showLabSubtab(subtab) {
        const target = ["overview", "source", "relationships", "grir", "fx", "timesheet"].includes(subtab) ? subtab : "overview";
        labActiveSubtab = target;
        document.querySelectorAll("[data-lab-subtab]").forEach((button) => {
            const active = button.dataset.labSubtab === target;
            button.classList.toggle("active", active);
            button.setAttribute("aria-selected", active ? "true" : "false");
        });
        document.querySelectorAll("[data-lab-panel]").forEach((panel) => {
            panel.hidden = panel.dataset.labPanel !== target;
        });
        if (target === "source") {
            mountPowerBISourceWorkspace(labPowerBISourceHost);
            loadPowerBIScreen();
        }
        if (target === "relationships") loadLabRelationships();
        if (target === "timesheet") loadTimesheetScreen();
    }

    function showSettingsTab(tab) {
        const target = document.querySelector(`[data-settings-panel="${tab}"]`) ? tab : "general";
        document.querySelectorAll("[data-settings-tab]").forEach((button) => {
            const active = button.dataset.settingsTab === target;
            button.classList.toggle("active", active);
            button.setAttribute("aria-selected", active ? "true" : "false");
        });
        document.querySelectorAll("[data-settings-panel]").forEach((panel) => {
            panel.hidden = panel.dataset.settingsPanel !== target;
        });
    }

    const visitedScreens = new Set(["new"]);

    function showScreen(screenKey) {
        // While a download is running the New Run journey must stay locked:
        // the user can only watch Active run or browse history/settings.
        if (screenKey === "new" && runInProgress) {
            logToConsole("Warning", appSettings.language === "pt-BR" ? "A Nova Execução fica bloqueada enquanto uma baixa está ativa." : "New Run stays locked while a download is running.");
            screenKey = "progress";
        }
        const firstVisit = !visitedScreens.has(screenKey);
        visitedScreens.add(screenKey);
        if (screenKey === "new") mountPowerBISourceWorkspace(newRunPowerBIArea);
        Object.entries(screens).forEach(([key, screen]) => {
            const active = key === screenKey;
            screen.classList.toggle("active", active);
            screen.hidden = !active;
            navButtons[key].classList.toggle("active", active);
        });
        const titles = { new: t("prepare"), lab: "LAB", progress: t("activeRun"), history: t("history"), learn: t("learn"), settings: t("settings") };
        if ($("#page-title")) $("#page-title").innerText = titles[screenKey] || titles.new;
        navButtons.new.disabled = runInProgress;
        navButtons.new.title = runInProgress ? (appSettings.language === "pt-BR" ? "Bloqueado durante a execução" : "Locked while a run is active") : "";
        $("#active-run-banner").hidden = !(screenKey === "new" && runInProgress);
        if (screenKey === "new" && runInProgress) $("#btn-start-run").disabled = true;
        if (screenKey === "new" && !runInProgress && journeyStep === 3) syncStepThreeAction();
        syncStartOverAction();
        syncUpdateButton();
        if (screenKey === "history") loadHistory();
        if (screenKey === "settings") {
            loadSettings();
            loadSettingsNgsi();
        }
        if (screenKey === "lab") showLabSubtab(labActiveSubtab);
        if (firstVisit) {
            const main = $(".main-content");
            if (main) window.requestAnimationFrame(() => { main.scrollTop = 0; });
        }
    }

    Object.entries(navButtons).forEach(([key, button]) => button.addEventListener("click", () => showScreen(key)));
    document.querySelectorAll("[data-lab-subtab]").forEach((button) => button.addEventListener("click", () => showLabSubtab(button.dataset.labSubtab)));
    $("#btn-lab-relationship-refresh")?.addEventListener("click", () => loadLabRelationships($("#lab-relationship-session-select")?.value || null));
    $("#btn-lab-relationship-expand")?.addEventListener("click", () => {
        const tree = Array.isArray(labRelationshipData?.tree) ? labRelationshipData.tree : [];
        tree.forEach((sow) => {
            labRelationshipExpanded.add(sow.key);
            (sow.pos || []).forEach((po) => labRelationshipExpanded.add(po.key));
        });
        renderLabRelationshipRows();
    });
    $("#btn-lab-relationship-collapse")?.addEventListener("click", () => { labRelationshipExpanded.clear(); renderLabRelationshipRows(); });
    $("#lab-relationship-session-select")?.addEventListener("change", (event) => loadLabRelationships(event.target.value || null));
    document.querySelectorAll("[data-settings-tab]").forEach((button) => button.addEventListener("click", () => showSettingsTab(button.dataset.settingsTab)));
    $("#btn-open-ngsi-settings")?.addEventListener("click", () => { showScreen("settings"); showSettingsTab("data"); });
    $("#btn-settings-ngsi-search")?.addEventListener("click", searchSettingsNgsi);
    $("#settings-ngsi-search")?.addEventListener("keydown", (event) => { if (event.key === "Enter") searchSettingsNgsi(); });
    $("#btn-settings-ngsi-add")?.addEventListener("click", addSettingsNgsi);
    $("#btn-settings-ngsi-validate")?.addEventListener("click", validateSettingsNgsi);
    showSettingsTab("general");

    // Close Power BI filter dropdowns when clicking outside
    document.addEventListener("click", (event) => {
        document.querySelectorAll("details.powerbi-filter-dropdown[open]").forEach((details) => {
            if (!details.contains(event.target)) details.open = false;
        });
    });
    // Prevent dropdown toggle when interacting with inputs inside the panel
    document.querySelectorAll(".powerbi-filter-dropdown summary").forEach((summary) => {
        summary.addEventListener("click", (event) => {
            const details = summary.parentElement;
            if (details.open && event.target.closest("input, button, label")) {
                event.preventDefault();
            }
        });
    });
    $("#powerbi-connection-status").addEventListener("click", async () => {
        const button = $("#powerbi-connection-status");
        if (button.disabled) return;
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        try {
            const result = await api().start_powerbi_login();
            setPowerBIMessage(result.success ? result.message : (result.error || "Could not start Power BI sign-in."), result.success ? "" : "powerbi-status-invalid");
            await refreshPowerBIConnectionStatus();
        } finally {
            setButtonBusy(button, false);
        }
    });
    $("#btn-powerbi-validate").addEventListener("click", validatePowerBISuppliers);
    $("#btn-powerbi-add-suppliers")?.addEventListener("click", addPowerBISuppliers);
    $("#btn-powerbi-refresh-hierarchy").addEventListener("click", loadPowerBIHierarchy);
    $("#btn-powerbi-search")?.addEventListener("click", searchPowerBISuppliers);
    $("#powerbi-supplier-search")?.addEventListener("input", (event) => {
        if (!event.target.value.trim()) showPowerBICacheResults();
    });
    $("#powerbi-supplier-search")?.addEventListener("keydown", (event) => { if (event.key === "Enter") searchPowerBISuppliers(); });
    $("#btn-powerbi-columns")?.addEventListener("click", openPowerBIColumnModal);
    // Column summary is the primary, discreet affordance near the table
    $("#powerbi-column-summary")?.addEventListener("click", openPowerBIColumnModal);
    document.querySelectorAll("[data-input-method]").forEach((choice) => choice.addEventListener("click", () => selectInputMethod(choice.dataset.inputMethod)));
    $("#btn-powerbi-refresh-families")?.addEventListener("click", async () => {
        const loaded = await loadPowerBIPurchaseFamilies(true);
        setPowerBIMessage(loaded ? "Purchase families refreshed." : "Could not refresh purchase families.", loaded ? "powerbi-status-valid" : "powerbi-status-invalid");
    });
    $("#powerbi-family-search")?.addEventListener("input", () => renderPowerBIFamilyResults());
    $("#btn-powerbi-copy-query-details")?.addEventListener("click", async () => {
        if (!powerbiQueryDiagnostics) return;
        const button = $("#btn-powerbi-copy-query-details");
        const text = JSON.stringify(powerbiQueryDiagnostics, null, 2);
        let copied = false;
        try {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(text);
                copied = true;
            }
        } catch (_) {
            copied = false;
        }
        if (!copied) {
            const area = document.createElement("textarea");
            area.value = text;
            area.style.position = "fixed";
            area.style.opacity = "0";
            document.body.appendChild(area);
            area.select();
            try { copied = document.execCommand("copy"); } catch (_) { copied = false; }
            area.remove();
        }
        if (button) {
            const original = button.innerText;
            button.innerText = copied ? "Copied" : "Copy failed";
            setTimeout(() => { button.innerText = original; }, 1600);
        }
    });
    $("#btn-powerbi-refresh-date-range").addEventListener("click", async () => {
        const button = $("#btn-powerbi-refresh-date-range");
        if (button?.dataset.busy === "1") return;
        setButtonBusy(button, true);
        try {
            await loadPowerBIDateRange(true);
            setPowerBIMessage("PO Creation Date range refreshed.", "powerbi-status-valid");
        } catch (error) {
            setPowerBIMessage(error.message || "Could not refresh PO Creation Date.", "powerbi-status-invalid");
        } finally {
            setButtonBusy(button, false);
        }
    });
    $("#btn-powerbi-preview").addEventListener("click", previewPowerBIPOs);
    $("#btn-powerbi-cancel")?.addEventListener("click", () => {
        powerbiQueryCancelled = true;
        const cancelButton = $("#btn-powerbi-cancel");
        if (cancelButton) {
            cancelButton.disabled = true;
            cancelButton.innerText = "Cancelling…";
        }
        if (hasApi("cancel_powerbi_query")) api().cancel_powerbi_query();
    });
    $("#btn-powerbi-grir").addEventListener("click", loadPowerBIGrir);
    $("#btn-powerbi-fx").addEventListener("click", loadPowerBIFx);
    $("#btn-powerbi-fx-expand").addEventListener("click", () => {
        powerbiGrirFxRows.forEach((row) => powerbiGrirFxExpanded.add(String(row.po_number || "")));
        renderPowerBIFx();
    });
    $("#btn-powerbi-fx-collapse").addEventListener("click", () => {
        powerbiGrirFxExpanded.clear();
        renderPowerBIFx();
    });
    $("#btn-close-powerbi-columns")?.addEventListener("click", closePowerBIColumnModal);
    $("#btn-cancel-powerbi-columns")?.addEventListener("click", closePowerBIColumnModal);
    $("#btn-apply-powerbi-columns")?.addEventListener("click", applyPowerBIColumns);
    $("#btn-refresh-powerbi-columns")?.addEventListener("click", refreshPowerBIColumns);
    $("#btn-select-all-powerbi-columns")?.addEventListener("click", () => {
        powerbiColumnDraft = new Set(powerbiPoColumns.map((column) => column.key));
        renderPowerBIColumnOptions();
    });
    $("#btn-clear-powerbi-columns")?.addEventListener("click", () => {
        powerbiColumnDraft = new Set(powerbiPoColumns.filter((column) => column.required).map((column) => column.key));
        renderPowerBIColumnOptions();
    });
    $("#powerbi-columns-accordion")?.addEventListener("toggle", async (event) => {
        if (!event.target.open) return;
        try {
            await loadPowerBIColumns();
            powerbiColumnDraft = new Set(powerbiSelectedColumns);
            renderPowerBIColumnOptions();
        } catch (error) {
            const options = $("#powerbi-column-options");
            if (options) options.innerHTML = `<div class="empty-state">${escapeHtml(error.message || "Could not load PO dataset fields.")}</div>`;
        }
    });
    $("#btn-timesheet-select").addEventListener("click", selectTimesheetFile);
    $("#btn-timesheet-load").addEventListener("click", loadTimesheetFile);
    $("#timesheet-supplier-filter").addEventListener("change", filterTimesheet);
    $("#timesheet-scope").addEventListener("change", filterTimesheet);
    $("#btn-back-new").addEventListener("click", () => showScreen("new"));
    $("#btn-go-active-run").addEventListener("click", () => showScreen("progress"));
    $("#btn-refresh-history").addEventListener("click", async () => {
        const button = $("#btn-refresh-history");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        try {
            await loadHistory();
        } finally {
            setButtonBusy(button, false);
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        const columnsModal = $("#powerbi-columns-modal");
        const detailsModal = $("#details-modal");
        const retryEditModalEl = $("#retry-edit-modal");
        if (columnsModal && !columnsModal.hidden) {
            closePowerBIColumnModal();
        } else if (retryEditModalEl && !retryEditModalEl.hidden) {
            closeRetryEditModal();
        } else if (detailsModal && !detailsModal.hidden) {
            detailsModal.hidden = true;
        }
    });

    function logToConsole(type, message) {
        const consoleLog = $("#console-log");
        if (!consoleLog || !String(message || "").trim()) return;
        const cleaned = String(message)
            .replace(/\s*\[diagnostic_log=.*?\]/gi, "")
            .replace(/Task error:\s*/i, "")
            .replace(/\\Users\\[^\s]+/gi, "the local diagnostic file")
            .replace(/\/Users\/[^\s]+/gi, "the local diagnostic file")
            .replace(/\s+/g, " ")
            .trim();
        const previous = consoleLog.lastElementChild;
        if (previous && previous.dataset.message === cleaned) return;
        const line = document.createElement("div");
        line.className = `log-line ${String(type || "system").toLowerCase()}`;
        line.dataset.message = cleaned;
        const timestamp = document.createElement("span");
        timestamp.className = "log-time";
        timestamp.innerText = new Date().toLocaleTimeString();
        const copy = document.createElement("span");
        copy.className = "log-message";
        const urlMatch = cleaned.match(/https:\/\/[^\s'\"]+\/order_headers\/[^\s'\"]+/i);
        if (urlMatch) {
            const url = urlMatch[0].replace(/[.,)]$/, "");
            const before = cleaned.slice(0, urlMatch.index);
            const after = cleaned.slice((urlMatch.index || 0) + urlMatch[0].length);
            copy.append(document.createTextNode(before));
            const link = document.createElement("button");
            link.type = "button";
            link.className = "log-link";
            link.innerText = "Open PO in Coupa";
            link.title = url;
            link.addEventListener("click", async () => {
                try {
                    const result = hasApi("open_external_url")
                        ? await api().open_external_url(url)
                        : hasApi("open_coupa_po")
                            ? await api().open_coupa_po((url.match(/order_headers\/([^/?#]+)/i) || ["", ""])[1])
                            : { success: false, error: "Browser integration is unavailable in this build." };
                    if (!result.success) logToConsole("Error", result.error || "Could not open the Coupa link.");
                } catch (error) {
                    logToConsole("Error", `Could not open the Coupa link: ${error.message || error}`);
                }
            });
            copy.append(link, document.createTextNode(after));
        } else {
            copy.innerText = cleaned;
        }
        line.append(timestamp, copy);
        consoleLog.appendChild(line);
        while (consoleLog.children.length > 100) consoleLog.firstElementChild.remove();
        consoleLog.scrollTop = consoleLog.scrollHeight;
        // Keep browser probes and diagnostics observable without exposing internals in the UI.
        if (typeof console !== "undefined" && console.info) console.info(message);
    }

    function updateReadyState(state, title, detail) {
        const indicator = $("#ready-indicator");
        if (!indicator) return;
        indicator.className = `status-dot ${state}`;
        $("#ready-title").innerText = title;
        $("#ready-detail").innerText = detail;
    }

    function updateAuthUI(state, detail) {
        const indicator = $("#auth-indicator");
        const text = $("#auth-status-text");
        const detailEl = $("#auth-detail");
        const context = $("#auth-context");
        const topLabel = $("#topbar-auth-label");
        const visualState = state.startsWith("auth_") ? "authenticating" : state;
        indicator.className = `status-dot ${visualState}`;
        const pt = appSettings.language === "pt-BR";
        const message = String(detail || "").trim();
        if (state === "authenticated") {
            text.innerText = pt ? "Autenticado" : "Authenticated";
            detailEl.innerText = message || (pt ? "Sessão Coupa pronta" : "Coupa session ready");
            topLabel.innerText = pt ? "Sessão Coupa pronta" : "Coupa session ready";
        } else if (state === "auth_starting") {
            text.innerText = pt ? "Preparando login…" : "Preparing sign-in…";
            detailEl.innerText = message || (pt ? "Preparando a captura do perfil corporativo existente do Edge" : "Preparing capture of the existing Edge work profile");
            topLabel.innerText = pt ? "Abrindo o Coupa" : "Opening Coupa";
        } else if (state === "auth_browser_ready") {
            text.innerText = pt ? "Verificando o Coupa…" : "Checking Coupa…";
            detailEl.innerText = message || (pt ? "A página foi carregada; verificando a sessão" : "Page loaded; checking the session");
            topLabel.innerText = pt ? "Verificando sessão" : "Checking session";
        } else if (state === "auth_user_action_required") {
            text.innerText = pt ? "Ação necessária" : "Action required";
            detailEl.innerText = message || (pt ? "Feche todas as janelas do Microsoft Edge quando solicitado" : "Close all Microsoft Edge windows when asked");
            topLabel.innerText = pt ? "Aguardando sua ação" : "Waiting for your action";
        } else if (state === "auth_action_required") {
            text.innerText = pt ? "Corrija o perfil e tente novamente" : "Fix the profile and try again";
            detailEl.innerText = message || (pt ? "É necessário um único perfil corporativo com @unilever.com" : "One corporate Edge profile containing @unilever.com is required");
            topLabel.innerText = pt ? "Ação necessária" : "Action required";
        } else if (state === "auth_checking") {
            text.innerText = pt ? "Verificando sessão…" : "Checking session…";
            detailEl.innerText = message || (pt ? "O Coupa está sendo consultado" : "Coupa is being checked");
            topLabel.innerText = pt ? "Verificando acesso" : "Checking access";
        } else if (state === "auth_validating") {
            text.innerText = pt ? "Validando login…" : "Validating sign-in…";
            detailEl.innerText = message || (pt ? "Login detectado; confirmando acesso ao Coupa" : "Sign-in detected; confirming Coupa access");
            topLabel.innerText = pt ? "Validando sessão" : "Validating session";
        } else if (state === "authenticating") {
            text.innerText = pt ? "Entrando…" : "Signing in…";
            detailEl.innerText = message || (pt ? "Preparando a autenticação" : "Preparing authentication");
            topLabel.innerText = pt ? "Preparando login" : "Preparing sign-in";
        } else if (state === "expired") {
            text.innerText = pt ? "Login necessário" : "Login required";
            detailEl.innerText = message || (pt ? "A sessão em cache expirou" : "Cached session expired");
            topLabel.innerText = pt ? "Login necessário" : "Login required";
        } else if (state === "unavailable") {
            text.innerText = pt ? "Verificação indisponível" : "Session check unavailable";
            detailEl.innerText = message || (pt ? "Não foi possível verificar a sessão agora" : "The cached session could not be verified right now");
            topLabel.innerText = pt ? "Verificação de sessão indisponível" : "Session check unavailable";
        } else {
            text.innerText = pt ? "Login necessário" : "Login required";
            detailEl.innerText = message || (pt ? "Clique para autenticar" : "Click to authenticate");
            topLabel.innerText = pt ? "Login necessário" : "Login required";
        }
        const authButton = $("#btn-authenticate");
        const cachedSessionUnavailable = state === "unavailable" && /cached coupa session found/i.test(message);
        const checking = state.startsWith("auth_") || state === "authenticating";
        const recheckOnly = state === "authenticated" || state === "unavailable";
        authButton.dataset.authState = state;
        authButton.classList.toggle("is-authenticated", state === "authenticated" || cachedSessionUnavailable);
        if (context) {
            const source = cachedSessionUnavailable ? (pt ? "EM CACHE" : "CACHED") : (pt ? "AO VIVO" : "LIVE");
            context.innerText = `${pt ? "ACESSO COUPA" : "COUPA ACCESS"} · ${source}`;
        }
        const action = $("#btn-authenticate .auth-action");
        if (action) {
            action.innerText = checking ? (pt ? "Aguarde…" : "Checking…") : recheckOnly ? (pt ? "Verificar" : "Recheck") : (pt ? "Entrar" : "Sign in");
        }
        authButton.disabled = checking;
    }

    const authStateLabels = {
        starting: "auth_starting",
        browser_ready: "auth_browser_ready",
        user_action_required: "auth_user_action_required",
        checking: "auth_checking",
        validating: "auth_validating",
        edge_must_be_closed: "auth_user_action_required",
        profile_detected: "auth_checking",
        capturing_session: "auth_checking",
        session_ready: "auth_validating",
        auth_required: "expired",
        action_required: "auth_action_required",
        success: "authenticated",
        error: "expired",
    };

    function normalizeAuthState(state) {
        return authStateLabels[state] || state || "authenticating";
    }

    function applyAuthCheckResult(result) {
        const state = result.authenticated || result.state === "cached"
            ? "authenticated"
            : ["login_required", "expired"].includes(result.state) ? "expired" : "unavailable";
        updateAuthUI(state, result.message);
        return result;
    }

    async function recheckAuthentication() {
        if (!hasApi("check_auth")) return applyAuthCheckResult({ authenticated: true, state: "browser_preview", message: "Browser preview" });
        try {
            return applyAuthCheckResult(await api().check_auth());
        } catch (error) {
            return applyAuthCheckResult({ authenticated: false, state: "unavailable", message: error.message || String(error) });
        }
    }

    async function authenticateWithProgressOnce() {
        if (!hasApi("authenticate")) return { success: false, error: "Authentication API unavailable." };
        updateAuthUI("auth_starting");
        logToConsole("System", appSettings.language === "pt-BR" ? "Preparando o login do Coupa…" : "Preparing Coupa sign-in…");
        const started = await api().authenticate();
        if (!started || !started.success) return started || { success: false, error: "Authentication failed." };
        if (!hasApi("get_authentication_status")) return started;

        let lastMessage = "";
        while (true) {
            const status = await api().get_authentication_status();
            const uiState = normalizeAuthState(status.state);
            updateAuthUI(uiState, status.message);
            if (status.message && status.message !== lastMessage) {
                logToConsole(uiState === "auth_user_action_required" ? "Warning" : "System", status.message);
                lastMessage = status.message;
            }
            if (status.state === "success") return { success: true };
            if (status.state === "error") return { success: false, error: status.message || "Authentication failed." };
            if (status.state === "action_required") return { success: false, error: status.message || "Action required before authentication can continue." };
            await new Promise((resolve) => setTimeout(resolve, 250));
        }
    }

    async function authenticateWithProgress() {
        if (authInFlight) return authInFlight;
        const attempt = authenticateWithProgressOnce();
        authInFlight = attempt;
        try {
            return await attempt;
        } finally {
            if (authInFlight === attempt) authInFlight = null;
        }
    }

    function destroyHierarchySorter() {
        if (hierarchySorter) hierarchySorter.destroy();
        hierarchySorter = null;
    }

    function syncHierarchyLevels(sortableList) {
        sortableList.querySelectorAll(":scope > li[data-column]").forEach((item, index) => {
            item.dataset.level = String(index + 2);
            item.style.setProperty("--hierarchy-level", String(index + 1));
            const level = item.querySelector(".hierarchy-level");
            if (level) level.innerText = `${appSettings.language === "pt-BR" ? "Nível" : "Level"} ${index + 2}`;
        });
    }

    function applyHierarchyOrder(order, source) {
        hierarchyOrder = [...new Set((order || []).map(String).filter(Boolean))];
        invalidateFolderApproval();
        const sortableList = $("#hierarchy-sortable");
        if (sortableList) syncHierarchyLevels(sortableList);
        renderDestinationPreview();
        const status = $("#hierarchy-reorder-status");
        if (status) {
            const orderText = hierarchyOrder.join(" / ");
            status.innerText = appSettings.language === "pt-BR"
                ? `Hierarquia reordenada por ${source === "drag" ? "arraste" : "botão"}: ${orderText}.`
                : `Hierarchy reordered by ${source}: ${orderText}.`;
        }
    }

    function renderHierarchy() {
        const container = $("#folder-hierarchy");
        const levelLabel = appSettings.language === "pt-BR" ? "Nível" : "Level";
        const poLabel = appSettings.language === "pt-BR" ? "PO (sempre último)" : "PO (always last)";
        const disableLabel = appSettings.language === "pt-BR" ? "Desativar" : "Disable";
        const enableLabel = appSettings.language === "pt-BR" ? "Ativar" : "Enable";
        const dragLabel = appSettings.language === "pt-BR" ? "Arrastar para reordenar" : "Drag to reorder";
        const moveUpLabel = appSettings.language === "pt-BR" ? "Mover para cima" : "Move up";
        const moveDownLabel = appSettings.language === "pt-BR" ? "Mover para baixo" : "Move down";
        const noLevelsLabel = appSettings.language === "pt-BR" ? "Nenhum nível opcional está ativo." : "No optional folder levels are enabled.";
        const disabledBox = $("#hierarchy-disabled");
        const disabledList = $("#hierarchy-disabled-list");

        destroyHierarchySorter();
        if (!hierarchyColumnsLoaded) {
            container.innerHTML = `<div class="hierarchy-empty">${appSettings.language === "pt-BR" ? "Valide o input para carregar os níveis de pasta." : "Validate the input to load its folder levels."}</div>`;
            disabledBox.hidden = true;
            disabledList.innerHTML = "";
            return;
        }

        const sortableItems = hierarchyOrder.length
            ? hierarchyOrder.map((column, index) => `<li class="hierarchy-row hierarchy-item" data-column="${escapeHtml(column)}" data-level="${index + 2}" style="--hierarchy-level:${index + 1}"><span class="hierarchy-branch" aria-hidden="true">└</span><span class="hierarchy-level">${levelLabel} ${index + 2}</span><span class="hierarchy-column-name">${escapeHtml(column)}</span><div class="hierarchy-actions"><button class="drag-handle" type="button" title="${dragLabel}" aria-label="${dragLabel}: ${escapeHtml(column)}">☷</button><button class="hierarchy-move" data-move-direction="up" type="button" title="${moveUpLabel}" aria-label="${moveUpLabel}: ${escapeHtml(column)}">↑</button><button class="hierarchy-move" data-move-direction="down" type="button" title="${moveDownLabel}" aria-label="${moveDownLabel}: ${escapeHtml(column)}">↓</button><button class="hierarchy-toggle" data-toggle-column="${escapeHtml(column)}" title="${disableLabel}" aria-label="${disableLabel}: ${escapeHtml(column)}" type="button">×</button></div></li>`).join("")
            : `<li class="hierarchy-empty hierarchy-sortable-empty">${noLevelsLabel}</li>`;

        container.innerHTML = [
            `<ol class="hierarchy-sortable" id="hierarchy-sortable" aria-label="${appSettings.language === "pt-BR" ? "Níveis de pasta reordenáveis" : "Reorderable folder levels"}">${sortableItems}</ol>`,
            `<div class="hierarchy-row hierarchy-fixed" data-fixed="po" style="--hierarchy-level:${hierarchyOrder.length + 1}"><span class="hierarchy-branch" aria-hidden="true">└</span><span class="hierarchy-level">${levelLabel} ${hierarchyOrder.length + 1}</span><span class="hierarchy-lock" aria-hidden="true">🔒</span><strong>${poLabel}</strong></div>`,
        ].join("");

        container.querySelectorAll(".hierarchy-toggle[data-toggle-column]").forEach((button) => {
            button.addEventListener("click", () => {
                const column = button.dataset.toggleColumn;
                hierarchyOrder = hierarchyOrder.filter((value) => value !== column);
                disabledHierarchyColumns.push(column);
                invalidateFolderApproval();
                renderHierarchy();
                renderDestinationPreview();
            });
        });

        disabledBox.hidden = disabledHierarchyColumns.length === 0;
        disabledList.innerHTML = disabledHierarchyColumns.map((column) => `<li><span>${escapeHtml(column)}</span><button class="hierarchy-toggle" data-reenable-column="${escapeHtml(column)}" title="${enableLabel}" type="button">+</button></li>`).join("");
        disabledList.querySelectorAll(".hierarchy-toggle[data-reenable-column]").forEach((button) => {
            button.addEventListener("click", () => {
                const column = button.dataset.reenableColumn;
                disabledHierarchyColumns = disabledHierarchyColumns.filter((value) => value !== column);
                hierarchyOrder.push(column);
                invalidateFolderApproval();
                renderHierarchy();
                renderDestinationPreview();
            });
        });

        const sortableList = $("#hierarchy-sortable");
        if (window.HierarchySorter) {
            hierarchySorter = new window.HierarchySorter(sortableList, {
                disabled: journeyStep !== 3 || journeyStep > journeyMaxStep,
                onChange: applyHierarchyOrder,
            });
        } else {
            logToConsole("Error", "The folder reordering component could not be loaded.");
        }
    }

    function renderDestinationPreview() {
        const preview = $("#destination-preview");
        if (!preview) return;
        const directory = $("#download-dir").value || "Downloads/CoupaAttachments";
        const parts = hierarchyOrder.length ? hierarchyOrder : ["Supplier"];
        const lines = [`${directory}/`, "└── {Supplier}"];
        lines.length = 1;
        parts.forEach((part, index) => { lines.push(`${"    ".repeat(index)}└── {${escapeHtml(part)}}`); });
        lines.push(`${"    ".repeat(parts.length)}└── {PO}/`);
        preview.innerText = lines.join("\n");
    }

    function syncStepThreeAction() {
        const button = $("#btn-start-run");
        if (!button) return;
        button.disabled = !hierarchyColumnsLoaded || !$("#download-dir").value.trim() || !$("#folder-approval")?.checked;
        if (journeyStep === 3) syncJourneyNavAction(3, false);
    }

    function invalidateFolderApproval() {
        const approval = $("#folder-approval");
        if (approval) approval.checked = false;
        syncStepThreeAction();
    }

    function renderHierarchyWarnings(emptyColumns) {
        const box = $("#hierarchy-warnings");
        const columns = Array.isArray(emptyColumns) ? emptyColumns : [];
        if (!columns.length) { box.hidden = true; box.innerHTML = ""; return; }
        box.hidden = false;
        box.innerHTML = columns.map((column) => `<div class="validation-warning">${appSettings.language === "pt-BR"
            ? `A coluna “${escapeHtml(column)}” está 100% vazia no input e não será usada para criar pastas.`
            : `The column “${escapeHtml(column)}” is completely empty in the input and will not be used to create folders.`}</div>`).join("");
    }

    async function checkHierarchyPathSafety() {
        const box = $("#hierarchy-path-safety");
        if (!box || !selectedFilePath || !hasApi("estimate_hierarchy_path") || !hierarchyColumnsLoaded) return true;
        try {
            const estimate = await api().estimate_hierarchy_path(selectedFilePath, hierarchyOrder, $("#download-dir").value || undefined);
            if (!estimate?.success) return true;
            const pt = appSettings.language === "pt-BR";
            box.hidden = false;
            box.className = `hierarchy-path-safety ${estimate.safe ? "safe" : "blocked"}`;
            box.innerText = estimate.safe
                ? (pt ? `Caminho máximo estimado: ${estimate.max_path_length} de ${estimate.limit} caracteres.` : `Estimated longest path: ${estimate.max_path_length} of ${estimate.limit} characters.`)
                : (pt ? `Caminho máximo estimado: ${estimate.max_path_length} caracteres. Remova: ${(estimate.recommended_remove || []).join(", ")} antes de continuar.` : `Estimated longest path: ${estimate.max_path_length} characters. Remove: ${(estimate.recommended_remove || []).join(", ")} before continuing.`);
            return Boolean(estimate.safe);
        } catch (_) {
            return true;
        }
    }

    function setHierarchyColumns(columns, emptyColumns = []) {
        invalidateFolderApproval();
        const empty = new Set((emptyColumns || []).map(String));
        const available = [...new Set((columns || []).map(String).filter((column) => !empty.has(column)))];
        hierarchyColumnsLoaded = true;
        disabledHierarchyColumns = [...new Set(disabledHierarchyColumns.filter((column) => available.includes(column)))];
        const disabled = new Set(disabledHierarchyColumns);
        const kept = [...new Set(hierarchyOrder)].filter((column) => available.includes(column) && !disabled.has(column));
        hierarchyOrder = kept.concat(available.filter((column) => !disabled.has(column) && !kept.includes(column)));
        renderHierarchy();
        renderDestinationPreview();
        checkHierarchyPathSafety();
    }

    function preparePowerBIHierarchySuggestions(rows, availableColumns = null, emptyColumns = []) {
        const records = Array.isArray(rows) ? rows : [];
        if (!records.length) return;
        const available = availableColumns ? new Set(availableColumns.map(String)) : null;
        const empty = new Set((emptyColumns || []).map(String));
        const reserved = new Set(["PO_NUMBER", "SUPPLIER", "COMPANY_CODE", "LEGAL_ENTITY_CODE", "LEGAL_ENTITY_NAME", "PO_CREATION_DATE", "COMMITMENT_VALUE_EUR", "GOODS_RECEIVED_VALUE_EUR", "POWERBI_SOURCE", "<|>", "MANAGEMENT_UNIT"]);
        const excluded = /po(number|id)?|commitment|amount|value|euro|currency|cost|price|total|date|time|month|quarter/i;
        const mapped = powerBISnapshotColumnSpecs().flatMap((column) => {
            const key = String(column.key || "");
            if (!key || key === "po_number" || key === "supplier_uu" || key === "management_unit_l3") return [];
            const header = powerBIInputHeader(column, reserved);
            reserved.add(header);
            return [{ key, header, values: records.map((row) => String(row?.[key] ?? "").trim()).filter(Boolean) }];
        });
        const seenHeaders = new Set();
        const candidates = mapped.filter((item) => {
            if (available && !available.has(item.header)) return false;
            if (item.key.startsWith("supplier_") || empty.has(item.header)) return false;
            if (excluded.test(item.key) && !["crg", "year"].includes(item.key)) return false;
            if (seenHeaders.has(item.header)) return false;
            seenHeaders.add(item.header);
            return item.values.length > 0;
        }).map((item) => ({
            key: item.header,
            distinct: new Set(item.values).size,
        })).sort((left, right) => left.distinct - right.distinct || left.key.localeCompare(right.key));
        invalidateFolderApproval();
        hierarchyColumnsLoaded = true;
        hierarchyOrder = ["SUPPLIER"];
        disabledHierarchyColumns = [...new Set(candidates.map((item) => item.key).filter((key) => key !== "SUPPLIER"))];
        renderHierarchy();
        renderDestinationPreview();
        checkHierarchyPathSafety();
    }

    function setFile(filePath, fileName, fileSize, inputSource = "file") {
        if (generatedTemplatePath && String(filePath || "") !== String(generatedTemplatePath)) generatedTemplatePath = null;
        selectedInputSource = inputSource;
        selectedInputMethod = inputSource === "powerbi" ? "powerbi" : "excel";
        if (inputSource !== "powerbi") powerbiSourceMetadata = null;
        selectedFilePath = filePath || null;
        selectedFileValidated = false;
        validatedFingerprint = null;
        mappingDetected = null;
        mappingSuggestions = { po: [], supplier: [] };
        hierarchyOrder = [];
        disabledHierarchyColumns = [];
        hierarchyColumnsLoaded = false;
        invalidateFolderApproval();
        hideMappingNotice();
        $("#validation-feedback").hidden = true;
        $("#destination-feedback").hidden = true;
        renderHierarchy();
        if (!selectedFilePath) {
            updateReadyState("unauthenticated", "Choose an input file", "Use the native picker so the full path is available.");
            updateInputMethodUI();
            return;
        }
        $("#selected-filename").innerText = fileName || String(filePath).split(/[\\/]/).pop();
        $("#validation-filename").innerText = fileName || String(filePath).split(/[\\/]/).pop();
        $("#selected-filesize").innerText = fileSize ? `${(fileSize / 1024).toFixed(1)} KB` : "Path selected";
        const extension = String(fileName || filePath).split(".").pop().toUpperCase();
        $(".file-type").innerText = extension || "FILE";
        $("#dropzone").hidden = true;
        $("#file-details").hidden = false;
        $("#file-state").hidden = false;
        $("#btn-validate-file").disabled = false;
        $("#btn-next-input").disabled = Boolean(hasApi("inspect_input_file"));
        updateReadyState("unauthenticated", "File selected", "Validate the file before starting.");
        startFileMonitor();
        // Detect non-standard files immediately so the user can map the
        // columns without waiting for the validation step.
        probeColumnsForMapping();
        updateInputMethodUI();
    }

    function showMappingNotice() {
        const notice = $("#mapping-notice");
        if (notice) notice.hidden = false;
    }

    function hideMappingNotice() {
        const notice = $("#mapping-notice");
        if (notice) notice.hidden = true;
    }

    async function probeColumnsForMapping() {
        if (!selectedFilePath || !hasApi("get_input_columns")) return;
        const requestedPath = selectedFilePath;
        const probeToken = ++mappingProbeToken;
        try {
            const info = await api().get_input_columns(requestedPath);
            if (requestedPath !== selectedFilePath || probeToken !== mappingProbeToken || !info || !info.success) return;
            mappingColumns = info.columns || [];
            mappingDetected = info.detected || {};
            mappingSuggestions = info.suggestions || { po: [], supplier: [] };
            const missingPo = !mappingDetected.po;
            const missingSupplier = !mappingDetected.supplier;
            if (missingPo || missingSupplier) {
                $("#mapping-notice-title").innerText = appSettings.language === "pt-BR"
                    ? (missingPo && missingSupplier
                        ? "Este arquivo não tem as colunas padrão."
                        : missingPo
                            ? "A coluna de PO não foi encontrada."
                            : "A coluna de fornecedor não foi encontrada.")
                    : (missingPo && missingSupplier
                        ? "This file does not have the standard columns."
                        : missingPo
                            ? "The PO column was not found."
                            : "The supplier column was not found.");
                $("#mapping-notice-text").innerText = appSettings.language === "pt-BR"
                    ? "Mapeie as colunas de PO e fornecedor para continuar."
                    : "Map the PO and supplier columns to continue.";
                showMappingNotice();
            } else {
                hideMappingNotice();
            }
        } catch (_) { /* best effort */ }
    }

    $("#btn-map-columns").addEventListener("click", async () => {
        if (!selectedFilePath) return;
        // Refresh the column list, then open the mapping card in step 2.
        if (hasApi("get_input_columns")) {
            const info = await api().get_input_columns(selectedFilePath);
            if (info && info.success) {
                mappingColumns = info.columns || [];
                mappingDetected = info.detected || {};
                mappingSuggestions = info.suggestions || { po: [], supplier: [] };
            }
        }
        completeJourneyStep(2);
        renderMappingCard(mappingColumns, mappingDetected, mappingSuggestions);
    });

    function resetPowerBIRunState() {
        powerbiSelectedSuppliers.clear();
        powerbiCheckedCandidates.clear();
        powerbiSelectedPathKeys.clear();
        powerbiSelectedDatePeriods.clear();
        powerbiSelectedFamilies.clear();
        powerbiPreviewRows = [];
        powerbiExcludedPOs.clear();
        powerbiQueryDiagnostics = null;
        powerbiSourceMetadata = null;
        powerbiGrirRows = [];
        powerbiGrirLoaded = false;
        powerbiGrirFxRows = [];
        powerbiGrirFxLoaded = false;
        powerbiGrirFxExpanded.clear();
        if ($("#powerbi-supplier-search")) $("#powerbi-supplier-search").value = "";
        if ($("#powerbi-family-search")) $("#powerbi-family-search").value = "";
        showPowerBICacheResults();
        renderPowerBISelectedSuppliers();
        renderPowerBIHierarchy();
        renderPowerBIDateHierarchy();
        renderPowerBIFamilyResults();
        renderPowerBIQueryDiagnostics();
        renderPowerBIPreview();
    }

    function clearFile() {
        selectedFilePath = null;
        selectedInputMethod = null;
        selectedInputSource = "file";
        resetPowerBIRunState();
        selectedFileValidated = false;
        validatedFingerprint = null;
        mappingDetected = null;
        mappingSuggestions = { po: [], supplier: [] };
        mappingColumns = [];
        hierarchyOrder = [];
        disabledHierarchyColumns = [];
        hierarchyColumnsLoaded = false;
        invalidateFolderApproval();
        mappingProbeToken += 1;
        hideMappingNotice();
        if (fileMonitorInterval) clearInterval(fileMonitorInterval);
        $("#file-input").value = "";
        $("#dropzone").hidden = false;
        $("#file-details").hidden = true;
        $("#validation-feedback").hidden = true;
        $("#destination-feedback").hidden = true;
        $("#file-state").hidden = true;
        $("#btn-next-input").disabled = true;
        $("#btn-next-hierarchy").disabled = true;
        journeyMaxStep = 1;
        showJourneyStep(1);
        updateReadyState("unauthenticated", "Choose an input file", "Validation is required before starting.");
        updateInputMethodUI();
        syncStartOverAction();
    }

    async function chooseInputFile() {
        if (hasApi("select_file")) {
            const result = await api().select_file();
            if (result && result.success) setFile(result.path, result.path.split(/[\\/]/).pop());
            else if (result && result.error) logToConsole("Error", result.error);
            return;
        }
        $("#file-input").click();
    }

    $("#btn-browse").addEventListener("click", chooseInputFile);
    $("#btn-open-selected-input").addEventListener("click", async () => {
        if (!selectedFilePath) return;
        const button = $("#btn-open-selected-input");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        if (!hasApi("open_input_path")) {
            logToConsole("Warning", "Opening the selected input is available in the desktop app.");
            setButtonBusy(button, false);
            return;
        }
        try {
            const result = await api().open_input_path(selectedFilePath);
            if (!result.success) logToConsole("Error", result.error || "Could not open the input file.");
        } finally {
            setButtonBusy(button, false);
        }
    });
    function readDroppedFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result || ""));
            reader.onerror = () => reject(new Error("The dropped file could not be read."));
            reader.readAsDataURL(file);
        });
    }

    async function selectDroppedFile(file) {
        if (!file) return;
        const directPath = String(file.path || "").trim();
        if (directPath || !hasApi("stage_dropped_file")) {
            setFile(directPath || file.name, file.name, file.size);
            return;
        }
        try {
            const staged = await api().stage_dropped_file(file.name, await readDroppedFile(file));
            if (!staged?.success) throw new Error(staged?.error || "Could not stage the dropped file.");
            setFile(staged.path, staged.name || file.name, staged.size || file.size);
        } catch (error) {
            logToConsole("Error", error.message || "Could not read the dropped file.");
        }
    }

    $("#file-input").addEventListener("change", (event) => {
        const file = event.target.files && event.target.files[0];
        if (file) selectDroppedFile(file);
    });
    $("#dropzone").addEventListener("dragover", (event) => { event.preventDefault(); $("#dropzone").classList.add("dragover"); });
    $("#dropzone").addEventListener("dragleave", () => $("#dropzone").classList.remove("dragover"));
    $("#dropzone").addEventListener("drop", (event) => {
        event.preventDefault();
        $("#dropzone").classList.remove("dragover");
        const file = event.dataTransfer.files && event.dataTransfer.files[0];
        if (file) selectDroppedFile(file);
    });
    $("#btn-clear-file").addEventListener("click", clearFile);

    async function startOver() {
        const pt = appSettings.language === "pt-BR";
        if (runInProgress) return;
        const hasJourneyState = Boolean(selectedFilePath || generatedTemplatePath || journeyMaxStep > 1);
        const confirmed = confirm(pt
            ? (hasJourneyState ? "Começar de novo? O estado desta preparação será apagado e uma nova execução será iniciada do zero. O histórico e os resultados de execuções concluídas serão preservados. Um template criado pelo aplicativo será excluído; arquivos de input escolhidos por você serão preservados." : "Começar de novo? As seleções atuais serão limpas e o fluxo voltará ao início.")
            : (hasJourneyState ? "Start over? This preparation state will be cleared and a new run will begin from scratch. History and results of completed runs are preserved. A template created by the app will be deleted; input files you chose are preserved." : "Start over? The current selections will be cleared and the journey will return to the beginning."));
        if (!confirmed) return;
        if (hasApi("reset_new_run")) {
            const result = await api().reset_new_run(generatedTemplatePath || selectedFilePath || "");
            if (!result.success) {
                logToConsole("Error", result.error || "Could not reset the new-run journey.");
                return;
            }
        }
        generatedTemplatePath = null;
        hierarchyOrder = [];
        disabledHierarchyColumns = [];
        clearFile();
        selectInputMethod("excel");
        $("#download-dir").value = "";
        await ensureDefaultDestination();
        syncStartOverAction();
        logToConsole("System", pt ? "Nova jornada iniciada do zero." : "New journey started from zero.");
    }

    $("#btn-start-over").addEventListener("click", startOver);

    function showDestinationFeedback(message) {
        const box = $("#destination-feedback");
        if (!box) return;
        box.innerText = message || "";
        box.hidden = !message;
    }

    async function validateDestinationPath() {
        const value = $("#download-dir").value.trim();
        if (!value) {
            showDestinationFeedback(appSettings.language === "pt-BR" ? "Escolha uma pasta de destino." : "Choose a download folder.");
            return false;
        }
        if (!hasApi("validate_download_directory")) return true;
        try {
            const result = await api().validate_download_directory(value);
            if (!result || !result.success) {
                showDestinationFeedback(result?.error || (appSettings.language === "pt-BR" ? "A pasta de destino não está disponível." : "The download destination is not available."));
                return false;
            }
            showDestinationFeedback("");
            if (result.path) $("#download-dir").value = result.path;
            return true;
        } catch (error) {
            showDestinationFeedback(error?.message || String(error));
            return false;
        }
    }

    async function ensureDefaultDestination() {
        if ($("#download-dir").value) {
            syncStepThreeAction();
            return;
        }
        if (hasApi("get_default_download_directory")) {
            const path = await api().get_default_download_directory();
            if (path) $("#download-dir").value = path;
        } else {
            const stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 15);
            $("#download-dir").value = `Downloads/CoupaAttachments/run_${stamp}`;
        }
        renderDestinationPreview();
        syncStepThreeAction();
    }

    $("#btn-choose-dir").addEventListener("click", async () => {
        const button = $("#btn-choose-dir");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        try {
            if (hasApi("select_directory")) {
                const path = await api().select_directory();
                if (path) {
                    $("#download-dir").value = path;
                    showDestinationFeedback("");
                    invalidateFolderApproval();
                }
            } else {
                $("#download-dir").value = "Downloads/CoupaAttachments";
                showDestinationFeedback("");
                invalidateFolderApproval();
            }
            renderDestinationPreview();
            syncStepThreeAction();
        } finally {
            setButtonBusy(button, false);
        }
    });
    $("#download-dir").addEventListener("input", () => {
        showDestinationFeedback("");
        invalidateFolderApproval();
        renderDestinationPreview();
        syncStepThreeAction();
        checkHierarchyPathSafety();
    });
    $("#download-dir").addEventListener("change", async () => {
        if (hasApi("set_default_download_directory") && $("#download-dir").value.trim()) {
            await api().set_default_download_directory($("#download-dir").value.trim());
        }
    });
    $("#folder-approval").addEventListener("change", syncStepThreeAction);

    $("#btn-download-template").addEventListener("click", async () => {
        const button = $("#btn-download-template");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        if (!hasApi("generate_input_template")) {
            logToConsole("Warning", "Template creation is available in the desktop app.");
            setButtonBusy(button, false);
            return;
        }
        try {
            const result = await api().generate_input_template();
            if (result.success) {
                setFile(result.path, result.path.split(/[\\/]/).pop());
                generatedTemplatePath = result.path;
                // The generated template already defines these levels, even before
                // the user adds the first PO row and validates the workbook.
                setHierarchyColumns(["Company", "Year", "Quarter", "Business Unit"]);
                logToConsole("Success", "Input template created and selected automatically.");
                alert(`Template opened at:\n${result.path}\n\nFill it in, save it, and close it. The application will keep monitoring this file automatically.`);
            } else {
                logToConsole("Error", result.message || "Could not create the template.");
            }
        } finally {
            setButtonBusy(button, false);
        }
    });

    function updateFileState(state) {
        const panel = $("#file-state");
        const dot = $("#file-state-dot");
        const label = $("#file-state-text");
        const pt = appSettings.language === "pt-BR";
        panel.hidden = false;
        panel.classList.remove("ready", "blocked");
        if (state.open_detected) {
            panel.classList.add("blocked");
            dot.className = "status-dot unauthenticated";
            label.innerText = pt ? "O Excel parece estar aberto — salve e feche o arquivo" : "Excel appears to be open — save and close it";
            selectedFileValidated = false;
            $("#btn-next-input").disabled = true;
        } else if (state.ready) {
            panel.classList.add("ready");
            dot.className = "status-dot authenticated";
            label.innerText = pt ? "Arquivo salvo e pronto para validar" : "File saved and ready to validate";
            $("#btn-next-input").disabled = false;
        } else {
            dot.className = "status-dot authenticating";
            label.innerText = pt ? "Aguardando o arquivo terminar de salvar…" : "Waiting for the file to finish saving…";
            $("#btn-next-input").disabled = true;
        }
        if (journeyStep === 1) syncJourneyNavAction(1, false);
    }

    async function pollFileState() {
        if (!selectedFilePath || !hasApi("inspect_input_file")) return;
        try {
            const state = await api().inspect_input_file(selectedFilePath);
            updateFileState(state);
            const fingerprint = state.mtime_ns && state.size ? `${state.mtime_ns}:${state.size}` : null;
            if (validatedFingerprint && fingerprint && fingerprint !== validatedFingerprint) {
                selectedFileValidated = false;
                $("#validation-feedback").hidden = true;
                $("#btn-next-hierarchy").disabled = true;
                if (journeyStep === 2) syncJourneyNavAction(2, false);
                updateReadyState("unauthenticated", "File changed", "Validate the updated file again before starting.");
            }
        } catch (error) {
            updateFileState({ ready: false, open_detected: true });
        }
    }

    function startFileMonitor() {
        if (fileMonitorInterval) clearInterval(fileMonitorInterval);
        pollFileState();
        fileMonitorInterval = setInterval(pollFileState, 800);
    }

    function renderMappingCard(columns, detected, suggestions = mappingSuggestions) {
        const card = $("#column-mapping-card");
        if (!card) return;
        if (!Array.isArray(columns) || !columns.length) { card.hidden = true; return; }
        const poSelect = $("#mapping-po-select");
        const supplierSelect = $("#mapping-supplier-select");
        if (!poSelect || !supplierSelect) return;
        const options = (placeholder) => `<option value="">${placeholder}</option>` + columns.map((column) => `<option value="${escapeHtml(column)}">${escapeHtml(column)}</option>`).join("");
        poSelect.innerHTML = options(appSettings.language === "pt-BR" ? "— selecione a coluna de PO —" : "— select the PO column —");
        supplierSelect.innerHTML = options(appSettings.language === "pt-BR" ? "— selecione a coluna de fornecedor —" : "— select the supplier column —");
        const best = (role) => (suggestions?.[role] || [])[0];
        if (detected && detected.po) poSelect.value = detected.po;
        else if (best("po")) poSelect.value = best("po").column;
        if (detected && detected.supplier) supplierSelect.value = detected.supplier;
        else if (best("supplier")) supplierSelect.value = best("supplier").column;
        const hint = (role) => {
            const item = best(role);
            if (!item) return "";
            const examples = (item.examples || []).slice(0, 3).join(", ");
            return `${item.confidence}% confidence${examples ? ` · e.g. ${examples}` : ""}`;
        };
        $("#mapping-po-hint").innerText = hint("po");
        $("#mapping-supplier-hint").innerText = hint("supplier");
        mappingColumns = columns;
        card.hidden = false;
    }

    function hideMappingCard() {
        const card = $("#column-mapping-card");
        if (card) card.hidden = true;
    }

    async function applyColumnMapping() {
        if (!selectedFilePath || !hasApi("map_input_columns")) return;
        const button = $("#btn-apply-mapping");
        if (button.dataset.busy === "1") return;
        const mapping = {
            po: $("#mapping-po-select").value,
            supplier: $("#mapping-supplier-select").value,
        };
        if (!mapping.po || !mapping.supplier) {
            logToConsole("Error", appSettings.language === "pt-BR" ? "Selecione as colunas de PO e fornecedor." : "Select the PO and supplier columns first.");
            return;
        }
        if (mapping.po === mapping.supplier) {
            const message = appSettings.language === "pt-BR" ? "PO e fornecedor precisam estar em colunas diferentes." : "PO Number and Supplier must use different columns.";
            logToConsole("Error", message);
            $("#validation-feedback").innerHTML = `<div class="validation-error">${escapeHtml(message)}</div>`;
            $("#validation-feedback").hidden = false;
            return;
        }
        setButtonBusy(button, true);
        button.disabled = true;
        try {
            const result = await api().map_input_columns(selectedFilePath, mapping);
            if (!result || !result.success) throw new Error(result?.error || (appSettings.language === "pt-BR" ? "Não foi possível aplicar o mapeamento." : "Could not apply the column mapping."));
            logToConsole("Success", appSettings.language === "pt-BR" ? `Mapeamento aplicado: PO → ${result.mapping.po}, Fornecedor → ${result.mapping.supplier}.` : `Mapping applied: PO → ${result.mapping.po}, Supplier → ${result.mapping.supplier}.`);
            await renderValidation(result);
        } catch (error) {
            const message = error?.message || String(error);
            logToConsole("Error", message);
            const feedback = $("#validation-feedback");
            feedback.innerHTML = `<div class="validation-error">${escapeHtml(message)}</div>`;
            feedback.hidden = false;
        } finally {
            button.disabled = false;
            setButtonBusy(button, false);
        }
    }

    function renderAffectedValues(group, pt) {
        const details = Array.isArray(group.row_details) ? group.row_details : [];
        const isRows = ["blank_rows", "partial_rows", "excel_cell_errors", "required_value_whitespace", "placeholder_supplier", "multiple_pos_in_cell", "ambiguous_po_value", "folder_value_safety"].includes(group.id) || group.rows_are_excel_rows;
        const rowPrefix = pt ? "Linha" : "Row";
        const values = details.length
            ? details.map((detail) => `${rowPrefix} ${detail.row}: ${(detail.parts || []).join(" · ")}`)
            : (Array.isArray(group.rows) ? group.rows.map(String) : []);
        if (!values.length) return "";
        const maxVisible = 200;
        const visible = values.slice(0, maxVisible).map((value) => escapeHtml(value)).join("\n");
        const remaining = values.length - Math.min(values.length, maxVisible);
        const label = isRows ? (pt ? "linhas afetadas" : "affected rows") : "POs";
        const copyLabel = isRows ? (pt ? "Copiar detalhes" : "Copy details") : (pt ? "Copiar POs" : "Copy POs");
        const more = remaining > 0
            ? (pt ? ` · mais ${remaining} não exibidos` : ` · ${remaining} more not shown`)
            : "";
        const copyId = `validation-values-${++validationCopyId}`;
        validationCopyValues.set(copyId, values.join("\n"));
        return `<details class="validation-affected"><summary>${pt ? "Ver" : "View"} ${values.length} ${label}${more}</summary><div class="validation-affected-values"><div class="validation-affected-toolbar"><button class="btn btn-quiet btn-copy-affected" data-copy-id="${copyId}" type="button">${copyLabel}</button></div><code>${visible}</code></div></details>`;
    }

    function validationGroupCopy(group, pt) {
        const copy = {
            blank_rows: ["Blank rows", "Row(s) completely empty.", "Linhas vazias", "Há linhas completamente vazias."],
            partial_rows: ["Rows with missing PO or Supplier", "Rows without PO Number or Supplier.", "Linhas sem PO ou fornecedor", "Há linhas sem PO ou fornecedor."],
            required_value_whitespace: ["Whitespace around PO or Supplier values", "Leading and trailing whitespace is ignored, but can be removed from the source file.", "Espaços em PO ou fornecedor", "Espaços no início e no fim são ignorados, mas podem ser removidos do arquivo."],
            multiple_pos_in_cell: ["Multiple POs in one cell", "Each row must contain one PO. Review the proposed split before applying it.", "Múltiplas POs na mesma célula", "Cada linha deve conter uma PO. Revise a divisão proposta antes de aplicar."],
            ambiguous_po_value: ["Ambiguous PO value", "The value contains a separator but cannot be split safely.", "PO ambígua", "O valor contém um separador, mas não pode ser dividido com segurança."],
            duplicate_pos: ["Duplicate PO numbers", "PO(s) repeated with the same Supplier.", "POs duplicadas", "Há POs repetidas com o mesmo fornecedor."],
            po_supplier_conflict: ["POs linked to multiple Suppliers", "Review these POs manually; automatic deduplication could discard a supplier relationship.", "POs ligadas a vários fornecedores", "Revise manualmente; a correção automática pode descartar um fornecedor."],
            invalid_chars: ["PO numbers with unusual characters", "PO values contain unsupported characters.", "POs com caracteres inválidos", "Há caracteres não permitidos nos valores de PO."],
            unusual_format: ["PO numbers with an invalid format", "PO values must start with PO/PM and contain digits only after the prefix.", "POs com formato inválido", "As POs devem começar com PO/PM e conter apenas números depois do prefixo."],
            unusual_po_length: ["PO numbers with an unusual length", "Most PO numbers contain 8 digits after PO or PM. Confirm values with another length.", "POs com quantidade de dígitos incomum", "A maioria das POs contém 8 dígitos depois de PO ou PM. Confirme valores com outro tamanho."],
            placeholder_pos: ["Placeholder PO values", "Replace placeholders such as UNK, N/A or TBD with real PO numbers.", "POs de preenchimento", "Substitua valores como UNK, N/A ou TBD por POs reais."],
            placeholder_supplier: ["Placeholder Supplier values", "Replace placeholder Supplier values such as Unknown, N/A or TBD.", "Fornecedor de preenchimento", "Substitua valores de fornecedor como Unknown, N/A ou TBD."],
            excel_cell_errors: ["Excel error values", "Replace formula errors such as #REF!, #VALUE! or #N/A.", "Erros nas células do Excel", "Substitua erros de fórmula como #REF!, #VALUE! ou #N/A."],
            excel_numeric_coercion: ["PO values may have been converted by Excel", "Format the PO column as text and restore lost leading zeros.", "POs convertidas pelo Excel", "Formate a coluna como texto e restaure zeros à esquerda perdidos."],
            empty_headers: ["Empty or unnamed headers", "Rename empty or unnamed columns before continuing.", "Cabeçalhos vazios ou sem nome", "Renomeie as colunas vazias ou sem nome."],
            duplicate_required_headers: ["Duplicate required headers", "The PO or Supplier column appears more than once.", "Cabeçalhos obrigatórios duplicados", "A coluna de PO ou fornecedor aparece mais de uma vez."],
            duplicate_headers: ["Similar column headers", "Review columns with the same base name before choosing folder levels.", "Cabeçalhos semelhantes", "Revise colunas com o mesmo nome-base antes de escolher as pastas."],
            folder_value_safety: ["Folder names will be sanitized", "Warning only: the download can continue. Unsafe characters such as '/' or backslash become '_' in folder names; reserved names, long values and collisions are also normalized.", "Nomes de pasta serão normalizados", "Aviso apenas: o download pode continuar. Caracteres inseguros como '/' ou barra invertida viram '_' nos nomes de pasta; nomes reservados, valores longos e colisões também são normalizados."],
            empty_hierarchy_columns: ["Empty hierarchy columns", "These columns contain no values and will not create folder levels.", "Colunas de hierarquia vazias", "Estas colunas não têm valores e não criarão níveis de pasta."],
            missing_po_column: ["Missing PO Number column", "Map the column that contains the PO Number.", "Coluna de PO ausente", "Mapeie a coluna que contém o número da PO."],
            missing_supplier_column: ["Missing Supplier/Company column", "Map the column that contains the Supplier.", "Coluna de fornecedor ausente", "Mapeie a coluna que contém o fornecedor."],
            mapping_same_column: ["PO and Supplier use the same column", "Choose two different columns for PO Number and Supplier.", "PO e fornecedor usam a mesma coluna", "Escolha colunas diferentes para PO e fornecedor."],
        }[group.id];
        if (!copy) return { title: group.title || group.id, message: group.message || "" };
        return { title: pt ? copy[2] : copy[0], message: pt ? copy[3] : copy[1] };
    }

    async function copyValidationValues(button, pt) {
        const values = validationCopyValues.get(button.dataset.copyId);
        if (!values) return;
        let copied = false;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            try {
                await navigator.clipboard.writeText(values);
                copied = true;
            } catch (_) { copied = false; }
        }
        if (!copied) {
            const area = document.createElement("textarea");
            area.value = values;
            area.setAttribute("readonly", "true");
            area.style.position = "fixed";
            area.style.opacity = "0";
            document.body.appendChild(area);
            area.select();
            copied = document.execCommand("copy");
            area.remove();
        }
        const original = button.innerText;
        button.innerText = copied ? (pt ? "Copiado" : "Copied") : (pt ? "Falhou" : "Copy failed");
        setTimeout(() => { button.innerText = original; }, 1800);
    }

    async function renderValidation(result) {
        const feedback = $("#validation-feedback");
        const errors = Array.isArray(result.errors) ? result.errors : [];
        const warnings = Array.isArray(result.warnings) ? result.warnings : [];
        const fixes = Array.isArray(result.fixes) ? result.fixes : [];
        const groups = Array.isArray(result.groups) ? result.groups : [];
        const mapping = result.mapping || {};
        validationCopyValues.clear();
        mappingDetected = mapping.po || mapping.supplier ? mapping : (mappingDetected || {});
        mappingSuggestions = result.mapping_suggestions || mappingSuggestions;
        const pt = appSettings.language === "pt-BR";
        let html = "";
        const supplierColumn = result.mapping?.supplier || "Supplier";
        if (selectedInputSource === "powerbi" && powerbiPreviewRows.length) preparePowerBIHierarchySuggestions(powerbiPreviewRows, result.hierarchy_columns || [], result.empty_hierarchy_columns || []);
        else setHierarchyColumns([supplierColumn, ...(result.hierarchy_columns || [])], result.empty_hierarchy_columns || []);
        renderHierarchyWarnings(result.empty_hierarchy_columns || []);
        const needsMapping = groups.some((group) => group.mapping);
        if (needsMapping) {
            renderMappingCard(mappingColumns.length ? mappingColumns : (await getInputColumnsForMapping()));
        } else {
            hideMappingCard();
        }
        const issueCount = groups.length || errors.length || warnings.length;
        if (result.valid) html += `<div class="validation-success">${pt ? `Arquivo válido — ${result.valid_po_count || 0} PO(s) prontos.` : `File is valid — ${result.valid_po_count || 0} PO(s) ready.`}</div>`;
        else html += `<div class="validation-error-header">${pt ? `O arquivo precisa de correção (${issueCount} grupo(s) de problema)` : `File needs correction (${issueCount} issue group(s))`}</div>`;
        if ((groups.length || (result.empty_hierarchy_columns || []).length) && hasApi("open_filtered_input_view")) {
            const csvInput = /\.csv$/i.test(String(selectedFilePath || ""));
            const actionLabel = csvInput
                ? (pt ? "Converter e abrir no Excel" : "Convert and open in Excel")
                : (pt ? "Abrir input filtrado no Excel" : "Open filtered input in Excel");
            const actionNote = csvInput
                ? (pt ? "O CSV original será preservado; uma cópia XLSX anotada será criada para edição." : "The original CSV stays unchanged; an annotated XLSX working copy will be created for editing.")
                : (pt ? "O arquivo original será anotado; um backup será criado antes." : "The original input will be annotated; a backup is created first.");
            html += `<div class="validation-excel-actions"><button class="btn btn-primary btn-small btn-open-filtered-view" type="button">${actionLabel}</button><small>${actionNote}</small></div>`;
        }
        if (groups.length) {
            html += `<div class="validation-dashboard">`;
            groups.forEach((group) => {
                const severityClass = group.severity === "warning" ? "validation-warning" : "validation-error";
                const groupCopy = validationGroupCopy(group, pt);
                html += `<div class="validation-group"><div class="validation-group-head ${severityClass}"><strong>${escapeHtml(groupCopy.title)}</strong><span>${group.count || 0}</span></div><p>${escapeHtml(groupCopy.message)}</p>${renderAffectedValues(group, pt)}`;
                if (group.fixable && hasApi("repair_input_file")) {
                    html += `<button class="btn btn-secondary btn-small btn-fix-group" data-fix="${escapeHtml(group.fix_action)}" type="button">${pt ? "Corrigir" : "Fix"}</button>`;
                } else if (group.fixable === false && group.id !== "missing_po_column" && group.id !== "missing_supplier_column") {
                    html += `<button class="btn btn-secondary btn-small btn-open-fix" type="button">${pt ? "Abrir arquivo para corrigir" : "Open file to fix"}</button>`;
                }
                html += `</div>`;
            });
            html += `</div>`;
        }
        const standaloneErrors = groups.length ? errors.filter((error) => String(error).toLowerCase().includes("no valid po")) : errors;
        const standaloneWarnings = groups.length ? [] : warnings;
        standaloneErrors.forEach((error) => { html += `<div class="validation-error">${escapeHtml(error)}</div>`; });
        standaloneWarnings.forEach((warning) => { html += `<div class="validation-warning">${escapeHtml(warning)}</div>`; });
        fixes.forEach((fix) => { html += `<div class="validation-info">${pt ? "Correção sugerida:" : "Suggested fix:"} ${escapeHtml(fix.description || fix.action)}</div>`; });
        feedback.innerHTML = html;
        feedback.querySelectorAll(".btn-copy-affected").forEach((button) => {
            button.addEventListener("click", () => copyValidationValues(button, pt));
        });
        const filteredViewButton = feedback.querySelector(".btn-open-filtered-view");
        if (filteredViewButton) {
            filteredViewButton.addEventListener("click", async () => {
                filteredViewButton.disabled = true;
                filteredViewButton.innerText = pt ? "Preparando input…" : "Preparing input…";
                try {
                    const opened = await api().open_filtered_input_view(selectedFilePath);
                    if (!opened || !opened.success) throw new Error(opened?.error || (pt ? "Não foi possível preparar o input para correção." : "Could not prepare the input for correction."));
                    if (opened.path && opened.path !== selectedFilePath) {
                        selectedFilePath = opened.path;
                        selectedFileValidated = false;
                        validatedFingerprint = null;
                        const workingName = String(opened.path).split(/[\\/]/).pop();
                        $("#selected-filename").innerText = workingName;
                        $("#validation-filename").innerText = workingName;
                        $("#selected-filesize").innerText = pt ? "Cópia de trabalho XLSX" : "XLSX working copy";
                        $(".file-type").innerText = "XLSX";
                        $("#btn-next-hierarchy").disabled = true;
                        startFileMonitor();
                        probeColumnsForMapping();
                        updateReadyState("unauthenticated", pt ? "Cópia XLSX criada" : "XLSX working copy created", pt ? "Edite o arquivo no Excel, salve, feche e valide novamente." : "Edit the Excel file, save, close it, and validate again.");
                    }
                    logToConsole("Success", `${opened.message} ${opened.filtered_rows || 0} row(s) filtered.`);
                    filteredViewButton.innerText = pt ? "Input aberto" : "Input opened";
                } catch (error) {
                    const message = error?.message || String(error);
                    logToConsole("Error", message);
                    filteredViewButton.innerText = pt ? "Falha ao abrir" : "Open failed";
                    filteredViewButton.disabled = false;
                }
            });
        }
        feedback.querySelectorAll(".btn-fix-group").forEach((button) => {
            button.addEventListener("click", async () => {
                const action = button.dataset.fix || button.getAttribute("data-fix");
                if (!action || !selectedFilePath || !hasApi("repair_input_file")) {
                    const message = pt ? "Não foi possível identificar esta correção." : "This repair action could not be identified.";
                    logToConsole("Error", message);
                    feedback.insertAdjacentHTML("afterbegin", `<div class="validation-error">${escapeHtml(message)}</div>`);
                    return;
                }
                button.disabled = true;
                button.innerText = pt ? "Corrigindo…" : "Applying…";
                try {
                    const preview = hasApi("preview_repair_input_file")
                        ? await api().preview_repair_input_file(selectedFilePath, action)
                        : { success: true, changes: [], total_changes: 0 };
                    if (!preview || !preview.success) {
                        throw new Error(preview?.error || (pt ? "Não foi possível preparar a correção." : "Could not prepare the repair preview."));
                    }
                    const changes = Array.isArray(preview.changes) ? preview.changes : [];
                    const previewLines = changes.slice(0, 30).map((change) => `Row ${change.row} · ${change.column}: ${JSON.stringify(change.old)} → ${JSON.stringify(change.new)}`).join("\n");
                    const more = Number(preview.total_changes || changes.length) > changes.length ? `\n… and ${Number(preview.total_changes) - changes.length} more` : "";
                    const confirmation = pt
                        ? `Alterações propostas:\n${previewLines || "Nenhuma alteração de valor."}${more}\n\nSalvar estas alterações no input?`
                        : `Proposed changes:\n${previewLines || "No value changes."}${more}\n\nSave these changes to the input?`;
                    if (!window.confirm(confirmation)) {
                        button.disabled = false;
                        button.innerText = pt ? "Corrigir" : "Fix";
                        return;
                    }
                    const repaired = await api().repair_input_file(selectedFilePath, [action], preview.expected_fingerprint);
                    if (!repaired || !repaired.success) {
                        throw new Error(repaired?.error || (pt ? "Não foi possível corrigir o arquivo." : "Could not repair the file."));
                    }
                    selectedFileValidated = false;
                    validatedFingerprint = null;
                    logToConsole("Success", `${repaired.message} Backup: ${repaired.backup_path}`);
                    feedback.innerHTML = `<div class="validation-success">${escapeHtml(repaired.message)} ${pt ? "Revalidando…" : "Revalidating…"}</div>`;
                    await validateCurrentFile();
                } catch (error) {
                    const message = error?.message || String(error);
                    logToConsole("Error", message);
                    feedback.insertAdjacentHTML("afterbegin", `<div class="validation-error">${escapeHtml(message)}</div>`);
                    button.disabled = false;
                    button.innerText = pt ? "Corrigir" : "Fix";
                }
            });
        });
        feedback.querySelectorAll(".btn-open-fix").forEach((button) => {
            button.addEventListener("click", async () => {
                if (hasApi("open_input_path")) {
                    const opened = await api().open_input_path(selectedFilePath);
                    if (!opened.success) logToConsole("Error", opened.error || "Could not open the input file.");
                }
            });
        });
        feedback.hidden = false;
        selectedFileValidated = Boolean(result.valid);
        const state = result.file_state || {};
        validatedFingerprint = state.mtime_ns && state.size ? `${state.mtime_ns}:${state.size}` : null;
        $("#btn-next-hierarchy").disabled = !selectedFileValidated;
        if (journeyStep === 2) syncJourneyNavAction(2, false);
        updateReadyState(result.valid ? "authenticated" : "unauthenticated", result.valid ? (pt ? "Input validado" : "Input validated") : (pt ? "Input precisa de correção" : "Input needs correction"), result.valid ? (pt ? "Pronto para configurar o download." : "Ready to configure the download.") : (pt ? "Corrija o arquivo e valide novamente." : "Edit the same file and validate again."));
        return result;
    }

    async function getInputColumnsForMapping() {
        if (!selectedFilePath || !hasApi("get_input_columns")) return [];
        try {
            const info = await api().get_input_columns(selectedFilePath);
            if (info && info.success) {
                mappingColumns = info.columns || [];
                mappingSuggestions = info.suggestions || { po: [], supplier: [] };
                renderMappingCard(mappingColumns, info.detected, mappingSuggestions);
                return mappingColumns;
            }
        } catch (_) { /* best effort */ }
        return [];
    }

    async function validateCurrentFile() {
        if (!selectedFilePath) return { valid: false, errors: ["Please select an input file first."], warnings: [] };
        const button = $("#btn-validate-file");
        setButtonBusy(button, true);
        button.disabled = true;
        button.innerText = "Validating…";
        try {
            let result;
            if (hasApi("validate_input_file")) result = await api().validate_input_file(selectedFilePath);
            else result = { valid: true, errors: [], warnings: [], valid_po_count: 15, total_rows: 15 };
            if (result.file_state) updateFileState(result.file_state);
            return renderValidation(result);
        } catch (error) {
            const result = { valid: false, errors: [error.message || String(error)], warnings: [] };
            return renderValidation(result);
        } finally {
            button.disabled = false;
            button.innerText = t("validate");
            setButtonBusy(button, false);
        }
    }

    $("#btn-validate-file").addEventListener("click", validateCurrentFile);
    $("#btn-apply-mapping").addEventListener("click", applyColumnMapping);
    $("#btn-next-input").addEventListener("click", async () => {
        const button = $("#btn-next-input");
        if (button.dataset.busy === "1") return;
        if (selectedInputMethod === "powerbi") {
            if (!groupedPowerBIPreviewRows().length) {
                showJourneyPendingDialog(1);
                return;
            }
            setButtonBusy(button, true);
            button.disabled = true;
            const prepared = await preparePowerBIInputForNewRun();
            setButtonBusy(button, false);
            if (!prepared) {
                updateInputMethodUI();
                return;
            }
            completeJourneyStep(2);
            validateCurrentFile();
            return;
        }
        if (!selectedFilePath || button.disabled) {
            showJourneyPendingDialog(1);
            return;
        }
        completeJourneyStep(2);
        validateCurrentFile();
    });
    $("#btn-next-hierarchy").addEventListener("click", () => completeJourneyStep(3));
    document.querySelectorAll("[data-journey-back]").forEach((button) => button.addEventListener("click", () => showJourneyStep(Math.min(Number(button.dataset.journeyBack), journeyMaxStep))));
    document.querySelectorAll("[data-journey-step]").forEach((button) => button.addEventListener("click", () => showJourneyStep(button.dataset.journeyStep)));
    showJourneyStep(1);
    updateInputMethodUI();
    ensureDefaultDestination();

    async function startRunFlow() {
        const approval = $("#folder-approval");
        if (!approval?.checked) {
            showJourneyPendingDialog(3);
            approval?.focus();
            return;
        }
        if (!selectedFilePath) {
            logToConsole("Error", "Please select an input file before starting.");
            showJourneyStep(1);
            return;
        }

        // Active run is the execution workspace. Show it before validation,
        // authentication and import so the user can see progress immediately.
        importedSessionId = null;
        runInProgress = true;
        showScreen("progress");

        const validation = selectedFileValidated
            ? { valid: true }
            : await validateCurrentFile();
        if (!validation.valid) {
            logToConsole("Error", "Fix the validation errors and validate the file again.");
            runInProgress = false;
            showScreen("new");
            showJourneyStep(2);
            return;
        }
        if (!(await validateDestinationPath())) {
            logToConsole("Error", appSettings.language === "pt-BR" ? "Corrija a pasta de destino antes de iniciar." : "Fix the download destination before starting.");
            runInProgress = false;
            showScreen("new");
            showJourneyStep(3);
            return;
        }
        if (!(await checkHierarchyPathSafety())) {
            logToConsole("Error", appSettings.language === "pt-BR" ? "Reduza a hierarquia antes de iniciar o download." : "Reduce the folder hierarchy before starting the download.");
            runInProgress = false;
            showScreen("new");
            showJourneyStep(3);
            return;
        }

        if (!hasApi("import_file")) {
            importedSessionId = 777;
            showScreen("progress");
            startTelemetryPolling(importedSessionId);
            return;
        }

        $("#btn-start-run").disabled = true;
        logToConsole("System", "Checking Coupa session…");
        let authCheck = { authenticated: true };
        if (hasApi("check_auth")) authCheck = await api().check_auth();
        if (!authCheck.authenticated && authCheck.state === "unavailable" && !authCheck.has_cached_session) {
            updateAuthUI("unavailable", authCheck.message);
            logToConsole("Warning", "Coupa could not be reached to verify the session. Check connectivity and try again.");
            runInProgress = false;
            showScreen("new");
            showJourneyStep(3);
            $("#btn-start-run").disabled = false;
            return;
        }
        if (!authCheck.authenticated && authCheck.state === "unavailable") {
            updateAuthUI("unavailable", authCheck.message);
            logToConsole("Warning", "Session verification is unavailable; the CLI will try the cached Coupa session.");
        } else if (!authCheck.authenticated) {
            const authResult = await authenticateWithProgress();
            if (!authResult.success) {
                updateAuthUI("expired", authResult.error);
                logToConsole("Error", authResult.error || "Authentication failed.");
                runInProgress = false;
                showScreen("new");
                showJourneyStep(3);
                $("#btn-start-run").disabled = false;
                return;
            }
            updateAuthUI("authenticated");
        } else {
            updateAuthUI("authenticated", authCheck.message);
        }

        logToConsole("System", `${selectedInputSource === "powerbi" ? "Preparing Power BI dataset snapshot" : "Importing"} ${$("#selected-filename").innerText}…`);
        // Import only stages the input. The canonical backend applies the
        // selected hierarchy when start_download receives hierarchyOrder.
        // Keeping this call to one argument also works with older desktop
        // bridge builds that have not been restarted yet.
        const imported = await api().import_file(selectedFilePath);
        if (!imported.success) {
            logToConsole("Error", imported.error || "Import failed.");
            runInProgress = false;
            showScreen("new");
            showJourneyStep(3);
            $("#btn-start-run").disabled = false;
            return;
        }
        importedSessionId = imported.session_id;
        const directory = $("#download-dir").value;
        const started = await api().start_download(importedSessionId, directory, Number(appSettings.concurrency || 4), hierarchyOrder, Number(appSettings.retry_attempts || 1), null, selectedInputSource === "powerbi" ? powerbiSourceMetadata : null);
        if (!started.success) {
            logToConsole("Error", started.error || "Could not start the run.");
            runInProgress = false;
            showScreen("new");
            showJourneyStep(3);
            $("#btn-start-run").disabled = false;
            return;
        }
        logToConsole("Success", `Run ${importedSessionId} started with ${imported.total_pos} PO(s).`);
        showScreen("progress");
        startTelemetryPolling(importedSessionId);
    }

    $("#btn-start-run").addEventListener("click", async () => {
        if (startRequestActive || runInProgress) return;
        startRequestActive = true;
        setButtonBusy($("#btn-start-run"), true);
        $("#btn-start-run").disabled = true;
        try {
            await startRunFlow();
        } catch (error) {
            logToConsole("Error", error?.message || String(error));
            if (runInProgress && importedSessionId === null) {
                runInProgress = false;
                showScreen("new");
                showJourneyStep(3);
            }
        } finally {
            startRequestActive = false;
            setButtonBusy($("#btn-start-run"), false);
            if (!runInProgress) {
                syncStepThreeAction();
            }
        }
    });

    let lastStatus = "PENDING";
    function resetRunCompletion() {
        completionSessionId = null;
        completionAlertKey = "";
        completionStats = null;
        const card = $("#run-complete-card");
        if (card) {
            card.hidden = true;
            card.className = "run-complete-card";
        }
    }

    async function openRunArtifact(kind, sessionId) {
        const numericId = Number(sessionId || completionSessionId || importedSessionId || 0);
        const method = kind === "report" ? "open_run_report" : "open_run_folder";
        if (!numericId || !hasApi(method)) {
            logToConsole("Warning", "Opening run files is available in the desktop app.");
            return;
        }
        try {
            const result = await api()[method](numericId);
            if (!result.success) {
                logToConsole("Error", result.error || "Could not open the run file.");
                return;
            }
            logToConsole("Success", `${kind === "report" ? "Excel report" : "Download folder"} opened for run #${numericId}.`);
        } catch (error) {
            logToConsole("Error", error?.message || String(error));
        }
    }

    function showRunCompletion(stats) {
        const status = String(stats.status || "").toUpperCase();
        const sessionId = Number(stats.session_id || importedSessionId || 0);
        if (!sessionId || !["SUCCESS", "FAILED", "PARTIAL", "ERROR", "STOPPED", "RUN_PAUSED", "CANCELLED"].includes(status)) return;
        const pt = appSettings.language === "pt-BR";
        const copy = {
            SUCCESS: pt ? ["Execução concluída", `A execução #${sessionId} terminou sem erros.`] : ["Run completed", `Run #${sessionId} finished without errors.`],
            PARTIAL: pt ? ["Execução concluída com alertas", `A execução #${sessionId} terminou com ${Number(stats.errors || 0)} PO(s) com erro.`] : ["Run completed with warnings", `Run #${sessionId} finished with ${Number(stats.errors || 0)} PO(s) in error.`],
            FAILED: pt ? ["Execução concluída com erro", `A execução #${sessionId} terminou sem downloads bem-sucedidos.`] : ["Run completed with errors", `Run #${sessionId} finished without successful downloads.`],
            ERROR: pt ? ["Execução concluída com erro", `A execução #${sessionId} terminou com erro.`] : ["Run completed with errors", `Run #${sessionId} finished with an error.`],
            STOPPED: pt ? ["Execução pausada", `A execução #${sessionId} foi parada com segurança e pode ser retomada.`] : ["Run paused", `Run #${sessionId} was stopped safely and can be resumed.`],
            RUN_PAUSED: pt ? ["Login necessário para continuar", `A execução #${sessionId} foi pausada porque a sessão Coupa expirou. Feche o Edge quando solicitado, autentique e retome.`] : ["Authentication required to continue", `Run #${sessionId} paused because the Coupa session expired. Close Edge when asked, authenticate, and resume.`],
            CANCELLED: pt ? ["Execução cancelada", `A execução #${sessionId} foi cancelada.`] : ["Run cancelled", `Run #${sessionId} was cancelled.`],
        }[status];
        const variant = status === "SUCCESS" ? "success" : ["PARTIAL", "STOPPED", "RUN_PAUSED"].includes(status) ? "warning" : "failed";
        const card = $("#run-complete-card");
        completionSessionId = sessionId;
        completionStats = stats;
        card.className = `run-complete-card ${variant}`;
        card.hidden = false;
        $("#run-complete-icon").innerText = status === "SUCCESS" ? "✓" : "!";
        $("#run-complete-title").innerText = copy[0];
        $("#run-complete-message").innerText = copy[1];
        $("#btn-open-complete-report").dataset.session = String(sessionId);
        $("#btn-open-complete-folder").dataset.session = String(sessionId);
        const alertKey = `${sessionId}:${status}`;
        if (completionAlertKey !== alertKey) {
            completionAlertKey = alertKey;
            logToConsole(status === "SUCCESS" ? "Success" : status === "PARTIAL" || status === "STOPPED" || status === "RUN_PAUSED" ? "Warning" : "Error", copy[1]);
            window.setTimeout(() => window.alert(copy[1]), 0);
        }
    }

    function startTelemetryPolling(sessionId) {
        runInProgress = true;
        syncUpdateButton();
        resetRunCompletion();
        lastStatus = "PENDING";
        importedSessionId = sessionId;
        $("#active-session-title").innerText = sessionId ? `Run #${sessionId}` : "Starting CLI run…";
        $("#progress-subtitle").innerText = "Downloading attachments from Coupa.";
        $("#btn-pause-resume").disabled = false;
        $("#btn-stop-session").disabled = false;
        $("#btn-pause-resume").innerText = "Pause";
        $("#btn-pause-resume").dataset.state = "running";
        if (activePollInterval) clearInterval(activePollInterval);
        const poll = async () => {
            if (!hasApi("get_active_session_status")) return;
            try {
                const stats = await api().get_active_session_status(sessionId);
                updateProgressUI(stats);
                if (stats.session_id && stats.session_id !== importedSessionId) {
                    importedSessionId = stats.session_id;
                    $("#active-session-title").innerText = `Run #${stats.session_id}`;
                }
                if (["SUCCESS", "FAILED", "PARTIAL", "ERROR", "STOPPED", "RUN_PAUSED", "CANCELLED"].includes(stats.status)) {
                    showRunCompletion(stats);
                    runInProgress = false;
                    syncUpdateButton();
                    clearInterval(activePollInterval);
                    $("#btn-stop-session").disabled = true;
                    if (stats.status === "STOPPED" || stats.status === "RUN_PAUSED") {
                        $("#btn-pause-resume").disabled = false;
                        $("#btn-pause-resume").dataset.state = "paused";
                        $("#btn-pause-resume").innerText = stats.status === "RUN_PAUSED" ? "Authenticate and resume" : "Resume with reconciliation";
                    } else {
                        $("#btn-pause-resume").disabled = true;
                    }
                }
            } catch (error) { logToConsole("Error", `Telemetry failed: ${error.message || error}`); }
        };
        poll();
        activePollInterval = setInterval(poll, 1000);
    }

    function updateProgressUI(stats) {
        const total = Number(stats.total || 0);
        const processed = Number(stats.processed || 0);
        const percent = total ? Math.min(100, Math.round((processed / total) * 100)) : 0;
        $("#progress-bar").style.width = `${percent}%`;
        $("#progress-text").innerText = `${percent}% (${processed}/${total})`;
        const speed = Number(stats.speed || 0);
        const stalledSeconds = Number(stats.stalled_seconds || 0);
        $("#speed-val").innerHTML = `${speed.toFixed(1)} <small>PO/min</small>`;
        $("#eta-val").innerText = stats.eta || "--:--";
        const pt = appSettings.language === "pt-BR";
        if (processed >= total && total > 0) {
            $("#speed-note").innerText = pt ? "Execução concluída" : "Run complete";
            $("#eta-note").innerText = pt ? "Sem trabalho restante" : "No work remaining";
        } else if (stalledSeconds >= 45) {
            $("#speed-note").innerText = pt ? `Nenhuma PO concluída há ${stalledSeconds}s` : `No PO completed for ${stalledSeconds}s`;
            $("#eta-note").innerText = pt ? "Aguardando novo progresso" : "Waiting for new progress";
        } else {
            $("#speed-note").innerText = pt ? "Taxa de conclusão dos últimos 60s" : "Completion rate over the last 60s";
            $("#eta-note").innerText = speed > 0 ? (pt ? "Estimado pela velocidade recente" : "Estimated from recent speed") : (pt ? "Coletando progresso recente" : "Collecting recent progress");
        }
        $("#errors-val").innerText = String(stats.errors || 0);
        renderCompanyErrorBreakdown(stats.company_stats || []);
        $("#run-state").innerText = String(stats.status || "RUNNING");
        if (stats.status !== lastStatus) { lastStatus = stats.status; logToConsole("System", `Run status: ${stats.status}`); }
        (stats.latest_logs || []).forEach((entry) => logToConsole(entry.type, entry.message));
    }

    function renderCompanyErrorBreakdown(companyStats) {
        const target = $("#error-breakdown");
        if (!target) return;
        const rows = (Array.isArray(companyStats) ? companyStats : []).filter((item) => Number(item.processed || 0) > 0);
        if (!rows.length) {
            target.innerHTML = `<span>${appSettings.language === "pt-BR" ? "A distribuição por company code aparecerá durante o processamento." : "The company-code distribution will appear during processing."}</span>`;
            target.hidden = false;
            return;
        }
        target.innerHTML = rows.map((item) => {
            const processed = Number(item.processed || 0);
            const success = Number(item.success || 0);
            const errors = Number(item.errors || 0);
            const successPercent = processed ? Math.round(success / processed * 100) : 0;
            const errorPercent = 100 - successPercent;
            return `<div class="error-company-row"><div class="error-company-head"><strong>${escapeHtml(item.company_code || "Unknown")}</strong><span>${successPercent}% success · ${errorPercent}% error</span></div><div class="error-company-bar" title="${successPercent}% success, ${errorPercent}% error"><span class="error-company-success" style="width:${successPercent}%"></span><span class="error-company-error" style="width:${errorPercent}%"></span></div></div>`;
        }).join("");
        target.hidden = false;
    }

    $("#btn-pause-resume").addEventListener("click", async () => {
        if (importedSessionId === null || !hasApi("pause_download")) return;
        const button = $("#btn-pause-resume");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        const paused = $("#btn-pause-resume").dataset.state === "paused";
        if (paused && !hasApi("resume_download")) {
            setButtonBusy(button, false);
            return;
        }
        const result = paused ? await api().resume_download(importedSessionId) : await api().pause_download(importedSessionId);
        setButtonBusy(button, false);
        if (!result.success) { logToConsole("Error", result.error || "Could not update run state."); return; }
        if (paused) {
            const reconciled = result.reconciliation ? result.reconciliation.count : 0;
            logToConsole("System", `Reconciliation complete: ${reconciled} PO(s) reset for verification. Resuming pending and failed POs…`);
            $("#btn-pause-resume").disabled = true;
            startTelemetryPolling(result.session_id || 0);
        } else {
            $("#btn-pause-resume").dataset.state = "paused";
            $("#btn-pause-resume").innerText = "Stopping safely…";
            $("#btn-pause-resume").disabled = true;
            logToConsole("System", "Pause requested. Waiting for the current operation to finish safely…");
        }
    });

    $("#btn-stop-session").addEventListener("click", async () => {
        if (importedSessionId === null || !hasApi("stop_download")) return;
        if (!confirm("Stop this run? Active requests will finish before the queue stops.")) return;
        const button = $("#btn-stop-session");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        const result = await api().stop_download(importedSessionId);
        setButtonBusy(button, false);
        if (!result.success) { logToConsole("Error", result.error || "Could not stop run."); return; }
        logToConsole("System", "Stop requested. Waiting current operation to end...");
    });
    $("#btn-clear-log").addEventListener("click", () => { $("#console-log").innerHTML = ""; });
    $("#btn-open-complete-report").addEventListener("click", () => openRunArtifact("report", $("#btn-open-complete-report").dataset.session));
    $("#btn-open-complete-folder").addEventListener("click", () => openRunArtifact("folder", $("#btn-open-complete-folder").dataset.session));

    async function deleteRun(button) {
        if (!hasApi("delete_session")) {
            alert("Run deletion is available in the desktop app.");
            return;
        }
        const sessionId = button.dataset.id;
        const inputName = button.dataset.input || "this run";
        const confirmed = confirm(`Delete run #${sessionId} (${inputName}) and all files in its run folder?\n\nThis cannot be undone. The original input file outside the run folder will be preserved.`);
        if (!confirmed) return;
        button.disabled = true;
        setButtonBusy(button, true);
        const result = await api().delete_session(Number(sessionId));
        if (!result.success) {
            button.disabled = false;
            setButtonBusy(button, false);
            alert(result.error || "Could not delete the run.");
            return;
        }
        if (currentDetails && String(currentDetails.session?.id) === String(sessionId)) {
            $("#details-modal").hidden = true;
            currentDetails = null;
        }
        logToConsole("Success", `Run #${sessionId} and its run files were deleted.`);
        setButtonBusy(button, false);
        await loadHistory();
    }

    let concurrencyEstimates = {};
    function renderConcurrencyEstimate() {
        const selected = String($("#settings-concurrency").value || "4");
        const estimate = concurrencyEstimates[selected];
        $("#settings-concurrency-estimate").innerText = estimate && estimate.minutes_100
            ? `Estimated time for 100 POs: about ${estimate.minutes_100} minutes (${estimate.samples} completed run${estimate.samples === 1 ? "" : "s"}).`
            : "Estimated time for 100 POs will be calculated after a completed run with this setting.";
    }

    async function loadConcurrencyEstimates() {
        if (!hasApi("get_concurrency_estimates")) {
            renderConcurrencyEstimate();
            return;
        }
        concurrencyEstimates = await api().get_concurrency_estimates();
        renderConcurrencyEstimate();
    }

    function syncAuthBrowserOptions() {
        const option = $("#settings-auth-browser option[value='auto']");
        if (!option) return;
        const defaultName = appSettings.auth_browsers?.system_default_name;
        const pt = appSettings.language === "pt-BR";
        option.innerText = defaultName
            ? (pt ? `Automático — padrão do sistema: ${defaultName}` : `Automatic — system default: ${defaultName}`)
            : (pt ? "Automático — navegador suportado disponível" : "Automatic — available supported browser");
    }

    async function loadSettings() {
        if (!hasApi("get_app_settings")) {
            renderConcurrencyEstimate();
            return;
        }
        const result = await api().get_app_settings();
        if (!result) return;
        appSettings = { ...appSettings, ...result };
        $("#settings-language").value = appSettings.language || "en";
        $("#settings-font-scale").value = String(appSettings.font_scale || 1.1);
        applyFontScale();
        applyLanguage();
        updateSidebarVersion();
        $("#settings-download-root").value = appSettings.download_root || "";
        $("#settings-concurrency").value = String(appSettings.concurrency || 4);
        $("#settings-retry").value = String(appSettings.retry_attempts || 1);
        $("#settings-auth-browser").value = String(appSettings.auth_browser || "auto");
        const availableBrowsers = new Set((appSettings.auth_browsers?.available || []).map((item) => item.id));
        $("#settings-auth-browser").querySelectorAll("option[value='edge'], option[value='chrome']").forEach((option) => {
            option.disabled = availableBrowsers.size > 0 && !availableBrowsers.has(option.value);
        });
        $("#settings-msg-processing").value = String(appSettings.msg_processing || "convert_extract");
        $("#settings-deduplicate").checked = Boolean(appSettings.deduplicate_files);
        $("#settings-auto-updates").checked = Boolean(appSettings.auto_updates);
        $("#settings-retention").value = String(appSettings.retention || "all");
        await loadConcurrencyEstimates();
    }

    async function saveSettings() {
        const button = $("#btn-save-settings");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        const values = {
            download_root: $("#settings-download-root").value.trim(),
            concurrency: Number($("#settings-concurrency").value),
            retry_attempts: Number($("#settings-retry").value),
            auth_browser: $("#settings-auth-browser").value,
            msg_processing: $("#settings-msg-processing").value,
            deduplicate_files: $("#settings-deduplicate").checked,
            auto_updates: $("#settings-auto-updates").checked,
            retention: $("#settings-retention").value,
            language: $("#settings-language").value,
            font_scale: Number($("#settings-font-scale").value),
        };
        if (!values.download_root) {
            $("#settings-status").innerText = "Choose a default download folder first.";
            setButtonBusy(button, false);
            return;
        }
        if (!hasApi("set_app_settings")) {
            appSettings = { ...appSettings, ...values };
            applyFontScale();
            $("#settings-status").innerText = "Settings updated for this session.";
            setButtonBusy(button, false);
            return;
        }
        try {
            const result = await api().set_app_settings(values);
            if (!result.success) {
                $("#settings-status").innerText = result.error || "Could not save settings.";
                return;
            }
            appSettings = { ...appSettings, ...result.settings };
            applyFontScale();
            applyLanguage();
            $("#settings-language").value = appSettings.language;
            $("#settings-status").innerText = appSettings.language === "pt-BR" ? "Configurações salvas neste computador." : "Settings saved on this computer.";
            if (appSettings.auto_updates) checkForUpdates();
        } finally {
            setButtonBusy(button, false);
        }
    }

    $("#settings-concurrency").addEventListener("change", renderConcurrencyEstimate);
    $("#settings-language").addEventListener("change", () => { appSettings.language = $("#settings-language").value; applyLanguage(); });
    $("#settings-font-scale").addEventListener("change", () => applyFontScale($("#settings-font-scale").value));
    $("#btn-save-settings").addEventListener("click", saveSettings);
    $("#btn-check-updates").addEventListener("click", () => checkForUpdates(true));
    $("#btn-reset-auth").addEventListener("click", async () => {
        if (!hasApi("reset_authentication")) return;
        const pt = appSettings.language === "pt-BR";
        const confirmed = confirm(pt
            ? "Zerar o login do Coupa? O armazenamento seguro e qualquer perfil legado do aplicativo serão removidos. Seu perfil pessoal do Edge, downloads, inputs e relatórios serão preservados."
            : "Reset Coupa sign-in? The secure session cache and any legacy app-owned sign-in profile will be removed. Your personal Edge profile, downloads, inputs, and reports will be preserved.");
        if (!confirmed) return;
        const button = $("#btn-reset-auth");
        setButtonBusy(button, true);
        button.disabled = true;
        const result = await api().reset_authentication();
        button.disabled = false;
        setButtonBusy(button, false);
        if (!result.success) {
            $("#settings-status").innerText = result.error || (pt ? "Não foi possível zerar o login." : "Could not reset sign-in state.");
            return;
        }
        updateAuthUI("unauthenticated");
        $("#settings-status").innerText = pt ? "Estado do login zerado. Clique em Sign in para autenticar novamente." : "Sign-in state reset. Click Sign in to authenticate again.";
        logToConsole("System", pt ? "Coupa sign-in state reset." : "Coupa sign-in state reset.");
    });
    $("#btn-reset-settings").addEventListener("click", async () => {
        const button = $("#btn-reset-settings");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        try {
        $("#settings-download-root").value = "";
        $("#settings-concurrency").value = "4";
        $("#settings-retry").value = "1";
        $("#settings-auth-browser").value = "auto";
        $("#settings-font-scale").value = "1.1";
        applyFontScale(1.1);
        $("#settings-msg-processing").value = "convert_extract";
        $("#settings-deduplicate").checked = true;
        $("#settings-auto-updates").checked = !appSettings.python_portable;
        $("#settings-retention").value = "all";
        await ensureDefaultDestination();
        $("#settings-download-root").value = $("#download-dir").value.replace(/[\\/]run_[^\\/]+$/, "");
        await saveSettings();
        } finally {
            setButtonBusy(button, false);
        }
    });
    $("#btn-reset-application").addEventListener("click", async () => {
        if (!hasApi("reset_application_state")) return;
        const pt = appSettings.language === "pt-BR";
        const confirmed = confirm(pt
            ? "Começar limpo? O histórico local, sessões e login serão apagados. Downloads, relatórios e inputs serão preservados. Feche uma janela de login do aplicativo e pare qualquer execução antes de continuar."
            : "Start clean? Local history, sessions, and sign-in state will be cleared. Downloads, reports, and inputs will be preserved. Close an app sign-in window and stop any active run before continuing.");
        if (!confirmed) return;
        const button = $("#btn-reset-application");
        setButtonBusy(button, true);
        button.disabled = true;
        const result = await api().reset_application_state();
        button.disabled = false;
        setButtonBusy(button, false);
        if (!result.success) {
            $("#settings-status").innerText = result.error || (pt ? "Não foi possível zerar o estado local." : "Could not reset local state.");
            return;
        }
        updateAuthUI("unauthenticated");
        pendingUpdate = null;
        syncUpdateButton();
        $("#settings-status").innerText = pt ? "Estado local zerado. Arquivos do usuário foram preservados." : "Local state reset. User files were preserved.";
        logToConsole("System", pt ? "Local application state reset." : "Local application state reset.");
        await loadHistory();
    });
    $("#btn-settings-choose-dir").addEventListener("click", async () => {
        if (!hasApi("select_directory")) return;
        const button = $("#btn-settings-choose-dir");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        try {
            const path = await api().select_directory();
            if (path) $("#settings-download-root").value = path.replace(/[\\/]run_[^\\/]+$/, "");
        } finally {
            setButtonBusy(button, false);
        }
    });

    async function clearAllHistory() {
        if (!hasApi("clear_all_sessions")) {
            alert("History cleanup is available in the desktop app.");
            return;
        }
        const confirmed = confirm("Delete every run, all run folders, reports, attachments, and archived inputs?\n\nThis cannot be undone. Original input files outside run folders will be preserved. Run numbering will restart at #1.");
        if (!confirmed) return;
        const button = $("#btn-clear-history");
        button.disabled = true;
        setButtonBusy(button, true);
        const result = await api().clear_all_sessions();
        button.disabled = false;
        setButtonBusy(button, false);
        if (!result.success) {
            alert(result.error || "Could not clear run history.");
            return;
        }
        $("#details-modal").hidden = true;
        currentDetails = null;
        logToConsole("Success", "All run history and run folders were deleted. The next run will be #1.");
        await loadHistory();
    }

    $("#btn-clear-history").addEventListener("click", clearAllHistory);

    function formatHistoryDate(value) {
        const raw = String(value || "").trim();
        if (!raw) return "—";
        const utcWithoutZone = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2}(?:\.\d+)?)$/.exec(raw);
        const date = new Date(utcWithoutZone ? `${utcWithoutZone[1]}T${utcWithoutZone[2]}Z` : raw);
        if (Number.isNaN(date.getTime())) return raw;
        const datePart = date.toLocaleDateString("en-GB", {
            day: "2-digit",
            month: "short",
            year: "numeric",
            timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        }).replace(/ /g, "/");
        const timePart = date.toLocaleTimeString(undefined, {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
            timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        });
        return `${datePart} ${timePart}`;
    }

    function updateHistoryTimezoneLabel() {
        const label = $("#history-timezone-label");
        if (!label) return;
        const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "local";
        const parts = new Intl.DateTimeFormat(undefined, { timeZone, timeZoneName: "short" }).formatToParts(new Date());
        const shortName = parts.find((part) => part.type === "timeZoneName")?.value || timeZone;
        const pt = appSettings.language === "pt-BR";
        label.innerText = `${pt ? "Fuso" : "TZ"}: ${shortName}`;
        label.title = `${pt ? "Fuso horário local" : "Local timezone"}: ${timeZone}`;
        label.setAttribute("aria-label", label.title);
    }

    async function loadHistory() {
        const body = $("#history-list");
        body.innerHTML = '<tr><td colspan="4" class="empty-state">Loading runs…</td></tr>';
        if (!hasApi("get_session_history")) {
            body.innerHTML = '<tr><td colspan="4" class="empty-state">History is available in the desktop app.</td></tr>';
            return;
        }
        try {
            const history = await api().get_session_history();
            if (!history.length) { body.innerHTML = '<tr><td colspan="4" class="empty-state">No runs yet.</td></tr>'; return; }
            const pt = appSettings.language === "pt-BR";
            body.innerHTML = history.map((session) => {
                const status = String(session.status || "PENDING").toUpperCase();
                const description = String(session.description || "").trim();
                const total = Number(session.total_pos) || 0;
                const success = Number(session.success_count) || 0;
                const errors = Number(session.error_count) || 0;
                const pending = Number(session.pending_count) || 0;
                const resultLabel = `${success}/${total}`;
                const resultNote = `${errors} error${errors === 1 ? "" : "s"}${pending ? ` · ${pending} pending` : ""}`;
                const runTitle = description || (pt ? "Sem descrição" : "No description");
                return `<tr><td><div class="history-run-cell" title="${escapeHtml(runTitle)}"><span>#${session.id}</span></div></td><td>${escapeHtml(formatHistoryDate(session.created_at))}</td><td><div class="history-result-cell"><strong>${resultLabel}</strong><small>${escapeHtml(resultNote)}</small></div></td><td class="history-actions"><button class="btn btn-secondary btn-small btn-view-details" data-id="${session.id}" type="button">${pt ? "Detalhes" : "Details"}</button></td></tr>`;
            }).join("");
            body.querySelectorAll(".btn-view-details").forEach((button) => button.addEventListener("click", () => openDetailsModal(button.dataset.id)));
        } catch (error) { body.innerHTML = `<tr><td colspan="4" class="empty-state">Could not load history: ${escapeHtml(error.message || error)}</td></tr>`; }
    }

    const modal = $("#details-modal");
    const retryEditModal = $("#retry-edit-modal");
    const retryResultModal = $("#retry-result-modal");
    let currentDetails = null;
    let pendingRetryPo = null;
    let retryDecisionResolver = null;
    let summaryCategory = "suppliers";
    let summaryEntity = "";
    $("#btn-close-modal").addEventListener("click", () => { modal.hidden = true; });

    function selectedStatusFilters() {
        return [...document.querySelectorAll("#status-filter input[data-status]:checked")].map((input) => input.dataset.status);
    }

    function syncStatusFilterControls() {
        const options = [...document.querySelectorAll("#status-filter input[data-status]")];
        const selected = options.filter((input) => input.checked).length;
        const all = $("#status-filter input[data-status-all]");
        all.checked = selected === options.length;
        all.indeterminate = selected > 0 && selected < options.length;
    }

    function coupaUrl(po) {
        if (po.coupa_url) return String(po.coupa_url);
        const value = String(po.po_number || "").trim();
        const orderNumber = /^(PO|PM)/i.test(value) ? value.slice(2) : value;
        return `https://unilever.coupahost.com/order_headers/${encodeURIComponent(orderNumber)}`;
    }

    function renderDetailsRows() {
        if (!currentDetails) return;
        const filters = selectedStatusFilters();
        const rows = currentDetails.pos.filter((po) => filters.includes(String(po.status).toUpperCase()));
        $("#modal-pos-tbody").innerHTML = rows.map((po) => {
            const expected = po.expected_company_code || "—";
            const legal = po.expected_legal_entity || "";
            const diagnosis = po.access_diagnosis || "";
            const message = po.remarks || po.error_message || "No error message recorded";
            return `<tr><td><button class="coupa-link po-number-link" data-po="${escapeHtml(po.po_number)}" title="Open ${escapeHtml(po.po_number)} in the default browser" type="button">${escapeHtml(po.po_number)}</button></td><td><strong>${escapeHtml(po.company_code)}</strong><small>Expected: ${escapeHtml(expected)}${legal ? ` · ${escapeHtml(legal)}` : ""}</small></td><td><span class="status-badge status-${String(po.status).toLowerCase()}">${escapeHtml(po.status)}</span></td><td><button class="btn btn-secondary btn-small btn-po-retry" data-po="${escapeHtml(po.po_number)}" type="button">Retry</button></td><td class="message-cell">${diagnosis ? `<strong>${escapeHtml(diagnosis)}</strong><br>` : ""}${escapeHtml(message)}</td></tr>`;
        }).join("") || '<tr><td colspan="5" class="empty-state">No POs match this filter.</td></tr>';
        $("#modal-pos-tbody").querySelectorAll(".btn-po-retry").forEach((button) => {
            button.addEventListener("click", () => retrySinglePo(button));
        });
        syncStatusFilterControls();
    }

    async function openPoInBrowser(button) {
        const poNumber = button.dataset.po || "";
        if (!hasApi("open_coupa_po") && !hasApi("open_external_url")) {
            alert("Browser integration is unavailable in this build.");
            return;
        }
        button.disabled = true;
        button.classList.add("opening");
        try {
            const result = hasApi("open_coupa_po")
                ? await api().open_coupa_po(poNumber)
                : await api().open_external_url(coupaUrl({ po_number: poNumber }));
            if (!result.success) {
                const message = result.error || `Could not open PO ${poNumber} in the browser.`;
                logToConsole("Error", message);
                alert(message);
            }
        } catch (error) {
            const message = `Could not open PO ${poNumber}: ${error.message || error}`;
            logToConsole("Error", message);
            alert(message);
        } finally {
            button.disabled = false;
            button.classList.remove("opening");
        }
    }

    // Delegation survives every table refresh/filter operation and avoids
    // losing click handlers when the PO rows are rebuilt with innerHTML.
    $("#modal-pos-tbody").addEventListener("click", (event) => {
        const button = event.target.closest(".po-number-link");
        if (button) openPoInBrowser(button);
    });

    function openRetryEditModal(poNumber) {
        pendingRetryPo = { sessionId: currentDetails.session.id, original: poNumber };
        $("#retry-po-input").value = poNumber;
        retryEditModal.hidden = false;
        $("#retry-po-input").focus();
        $("#retry-po-input").select();
    }

    function closeRetryEditModal() {
        pendingRetryPo = null;
        retryEditModal.hidden = true;
    }

    async function beginRetryAttempt() {
        if (!pendingRetryPo || !hasApi("retry_po_with_edit")) return;
        const edited = $("#retry-po-input").value.trim();
        if (!edited) {
            alert("Enter a PO number before retrying.");
            return;
        }
        const confirmButton = $("#btn-confirm-retry-edit");
        confirmButton.disabled = true;
        const request = pendingRetryPo;
        const result = await api().retry_po_with_edit(request.sessionId, request.original, edited);
        confirmButton.disabled = false;
        if (!result.success) {
            alert(result.error || "PO retry could not be started.");
            return;
        }
        closeRetryEditModal();
        modal.hidden = true;
        if (result.attempt_id) {
            startProvisionalRetryPolling(result.session_id || request.sessionId, result.attempt_id);
        } else {
            importedSessionId = result.session_id || request.sessionId;
            showScreen("progress");
            startTelemetryPolling(importedSessionId);
        }
    }

    function requestRetryResultDecision(status) {
        $("#retry-result-title").innerText = "Retry succeeded";
        $("#retry-result-message").innerText = `The corrected PO ${status.edited_po} was found and ${status.attachment_count || 0} attachment(s) were downloaded.`;
        retryResultModal.hidden = false;
        return new Promise((resolve) => { retryDecisionResolver = resolve; });
    }

    function resolveRetryResultDecision(decision) {
        retryResultModal.hidden = true;
        if (retryDecisionResolver) {
            const resolve = retryDecisionResolver;
            retryDecisionResolver = null;
            resolve(decision);
        }
    }

    async function finishProvisionalRetry(sessionId, attemptId, status) {
        runInProgress = false;
        syncUpdateButton();
        $("#btn-stop-session").disabled = true;
        $("#btn-pause-resume").disabled = true;
        if (status.status === "SUCCESS") {
            const decision = await requestRetryResultDecision(status);
            const keep = decision === "save";
            const result = keep
                ? await api().save_retry_attempt(attemptId)
                : await api().discard_retry_attempt(attemptId);
            if (!result.success) {
                alert(result.error || "Could not finalize the retry result.");
                return;
            }
            logToConsole(keep ? "Success" : "System", keep ? "PO correction saved to the input and report." : "Successful retry discarded; the run was left unchanged.");
        } else {
            await api().discard_retry_attempt(attemptId);
            alert(status.error_message || `Retry failed for ${status.edited_po}. The original error was preserved.`);
        }
        await openDetailsModal(sessionId);
    }

    function startProvisionalRetryPolling(sessionId, attemptId) {
        runInProgress = true;
        syncUpdateButton();
        importedSessionId = sessionId;
        showScreen("progress");
        $("#active-session-title").innerText = `Run #${sessionId}`;
        $("#progress-subtitle").innerText = "Testing the corrected PO before saving it.";
        $("#btn-pause-resume").disabled = true;
        $("#btn-stop-session").disabled = true;
        if (activePollInterval) clearInterval(activePollInterval);
        const poll = async () => {
            try {
                const status = await api().get_retry_attempt_status(attemptId);
                if (!status.success) throw new Error(status.error || "Retry status unavailable.");
                const finished = ["SUCCESS", "FAILED"].includes(status.status);
                updateProgressUI({
                    status: status.status,
                    total: 1,
                    processed: finished ? 1 : 0,
                    success: status.status === "SUCCESS" ? 1 : 0,
                    errors: status.status === "FAILED" ? 1 : 0,
                    latest_logs: [],
                });
                if (finished) {
                    clearInterval(activePollInterval);
                    await finishProvisionalRetry(sessionId, attemptId, status);
                }
            } catch (error) {
                logToConsole("Error", `Retry status failed: ${error.message || error}`);
            }
        };
        poll();
        activePollInterval = setInterval(poll, 700);
    }

    async function retrySinglePo(button) {
        if (!currentDetails || !hasApi("retry_po_with_edit")) return;
        openRetryEditModal(button.dataset.po || "");
    }

    $("#btn-close-retry-edit").addEventListener("click", closeRetryEditModal);
    $("#btn-cancel-retry-edit").addEventListener("click", closeRetryEditModal);
    $("#btn-confirm-retry-edit").addEventListener("click", beginRetryAttempt);
    $("#btn-save-retry-result").addEventListener("click", () => resolveRetryResultDecision("save"));
    $("#btn-discard-retry-result").addEventListener("click", () => resolveRetryResultDecision("discard"));
    $("#retry-po-input").addEventListener("keydown", (event) => {
        if (event.key === "Enter") beginRetryAttempt();
        if (event.key === "Escape") closeRetryEditModal();
    });

    $("#status-filter").addEventListener("change", (event) => {
        if (event.target.matches("input[data-status-all]")) {
            document.querySelectorAll("#status-filter input[data-status]").forEach((input) => { input.checked = event.target.checked; });
        }
        renderDetailsRows();
    });

    function runSummaryGroups(category) {
        const groups = new Map();
        (currentDetails?.pos || []).forEach((po) => {
            const value = category === "companies"
                ? String(po.company_code || "Unknown company code").trim()
                : String(po.supplier || "Unknown supplier").trim();
            if (!groups.has(value)) groups.set(value, []);
            groups.get(value).push(po);
        });
        return groups;
    }

    function renderSummaryColumn(category, targetId) {
        const target = $(targetId);
        if (!target) return;
        const groups = runSummaryGroups(category);
        const names = [...groups.keys()].sort((left, right) => left.localeCompare(right));
        target.innerHTML = names.length ? names.map((name) => {
            const rows = groups.get(name) || [];
            const success = rows.filter((po) => String(po.status).toUpperCase() === "SUCCESS").length;
            const errors = rows.filter((po) => ["ERROR", "SKIPPED_VERIFICATION_REQUIRED"].includes(String(po.status).toUpperCase())).length;
            const pending = rows.length - success - errors;
            const total = rows.length || 1;
            const retry = category === "suppliers" && errors && hasApi("retry_supplier")
                ? `<button class="secondary-button compact-button" data-retry-supplier="${escapeHtml(name)}">Retry supplier</button>`
                : "";
            return `<div class="run-summary-item"><div class="run-summary-heading"><strong>${escapeHtml(name)}</strong><span>${rows.length} PO${rows.length === 1 ? "" : "s"}</span></div><div class="run-summary-track"><span class="run-summary-success" style="width:${(success / total) * 100}%"></span><span class="run-summary-error" style="width:${(errors / total) * 100}%"></span><span class="run-summary-pending" style="width:${(pending / total) * 100}%"></span></div><div class="run-summary-meta"><span class="run-summary-success-text">${success} success</span><span class="run-summary-error-text">${errors} error${errors === 1 ? "" : "s"}</span>${pending ? `<span>${pending} pending</span>` : ""}</div>${retry}</div>`;
        }).join("") : '<p class="run-summary-empty">No summary data is available.</p>';
        target.querySelectorAll("[data-retry-supplier]").forEach((button) => {
            button.addEventListener("click", async () => {
                const supplier = button.dataset.retrySupplier || "";
                if (!currentDetails?.session?.id || !supplier || button.dataset.busy === "1") return;
                if (!confirm(`Retry failed POs for ${supplier} in the same run folder?`)) return;
                setButtonBusy(button, true);
                try {
                    const result = await api().retry_supplier(currentDetails.session.id, supplier);
                    if (result.success) {
                        modal.hidden = true;
                        importedSessionId = result.session_id || currentDetails.session.id;
                        showScreen("progress");
                        startTelemetryPolling(importedSessionId);
                    } else alert(result.error || "Supplier retry could not be started.");
                } finally {
                    setButtonBusy(button, false);
                }
            });
        });
    }

    function renderRunSummary() {
        renderSummaryColumn("suppliers", "#run-summary-suppliers");
        renderSummaryColumn("companies", "#run-summary-companies");
    }

    async function openDetailsModal(sessionId) {
        if (!hasApi("get_session_details")) return;
        currentDetails = await api().get_session_details(sessionId);
        if (!currentDetails || !currentDetails.session) {
            currentDetails = null;
            alert(`Run #${sessionId} could not be found.`);
            return;
        }
        currentDetails.pos = Array.isArray(currentDetails.pos) ? currentDetails.pos : [];
        modal.hidden = false;
        $("#modal-title").innerText = `Run #${sessionId}`;
        $("#modal-status").innerText = currentDetails.session.status;
        const inputPath = String(currentDetails.session.input_file_path || currentDetails.session.input_file || "").trim();
        const runFolder = String(currentDetails.session.run_dir || "").trim();
        const inputLink = $("#modal-input-link");
        inputLink.innerText = inputPath || "—";
        inputLink.title = inputPath || "No input path is available";
        inputLink.disabled = !inputPath;
        inputLink.onclick = async () => {
            if (!hasApi("open_input_file")) {
                alert("Input file opening is available in the desktop app.");
                return;
            }
            const result = await api().open_input_file(sessionId);
            if (!result.success) alert(result.error || "Could not open the preserved input file.");
        };
        const folderLink = $("#modal-run-folder");
        folderLink.innerText = runFolder || "—";
        folderLink.title = runFolder || "No download folder is available";
        folderLink.disabled = !runFolder;
        folderLink.onclick = async () => {
            if (!hasApi("open_run_folder")) {
                alert("Opening the run folder is available in the desktop app.");
                return;
            }
            const result = await api().open_run_folder(sessionId);
            if (!result.success) alert(result.error || "Could not open the run folder.");
        };
        const reportPath = String(currentDetails.session.report_path || (runFolder ? `${runFolder}/report_session_${sessionId}.xlsx` : "")).trim();
        const reportLink = $("#modal-report-path");
        reportLink.innerText = reportPath || "—";
        reportLink.title = reportPath || "No report path is available";
        reportLink.disabled = !reportPath;
        reportLink.onclick = () => api().open_run_report(sessionId).then((result) => {
            if (!result.success) alert(result.error || "Could not open the run report.");
        });
        const descriptionInput = $("#run-description-input");
        descriptionInput.value = currentDetails.session.description || "";
        const saveDescription = async () => {
            if (!hasApi("set_run_description")) {
                return;
            }
            if (descriptionInput.dataset.saved === descriptionInput.value.trim()) return;
            try {
                const result = await api().set_run_description(sessionId, descriptionInput.value.trim());
                if (!result.success) {
                    logToConsole("Error", result.error || "Could not save the run description.");
                    return;
                }
                currentDetails.session.description = descriptionInput.value.trim();
                descriptionInput.dataset.saved = descriptionInput.value.trim();
                logToConsole("Success", appSettings.language === "pt-BR" ? "Descrição da execução salva." : "Run description saved.");
                loadHistory();
            } catch (error) {
                logToConsole("Error", error.message || String(error));
            }
        };
        descriptionInput.dataset.saved = descriptionInput.value.trim();
        descriptionInput.onblur = saveDescription;
        descriptionInput.onkeydown = (event) => { if (event.key === "Enter") { event.preventDefault(); descriptionInput.blur(); } };
        const retryEvents = currentDetails.retry_events || [];
        $("#retry-history-list").hidden = !retryEvents.length;
        $("#retry-history-items").innerHTML = retryEvents.map((event) => `<li>${escapeHtml(event.po_number || "All errors")} · ${escapeHtml(event.status_before || "—")} → ${escapeHtml(event.status_after || "PENDING")} · ${escapeHtml(event.completed_at || event.requested_at || "")}</li>`).join("");
        document.querySelectorAll("#status-filter input[data-status]").forEach((input) => { input.checked = true; });
        syncStatusFilterControls();
        summaryCategory = "suppliers";
        summaryEntity = "";
        renderRunSummary();
        renderDetailsRows();
        $("#btn-export-modal-report").onclick = async () => {
            const button = $("#btn-export-modal-report");
            if (button.dataset.busy === "1") return;
            setButtonBusy(button, true);
            try {
                const result = await api().export_session_report(sessionId, `report_session_${sessionId}.xlsx`);
                alert(result.success ? `Report exported to ${result.filepath || "the selected location"}.` : `Export failed: ${result.error}`);
            } finally {
                setButtonBusy(button, false);
            }
        };
        $("#btn-retry-errors").onclick = async () => {
            if (!hasApi("retry_errors")) return;
            const errorCount = currentDetails.pos.filter((po) => ["ERROR", "SKIPPED_VERIFICATION_REQUIRED"].includes(po.status)).length;
            if (!errorCount || !confirm(`Retry ${errorCount} failed PO(s) in the same run folder?`)) return;
            const button = $("#btn-retry-errors");
            if (button.dataset.busy === "1") return;
            setButtonBusy(button, true);
            try {
                const result = await api().retry_errors(sessionId);
                if (result.success) {
                    modal.hidden = true;
                    importedSessionId = result.session_id || 0;
                    showScreen("progress");
                    startTelemetryPolling(importedSessionId);
                } else alert(result.error || "Retry could not be started.");
            } finally {
                setButtonBusy(button, false);
            }
        };
        $("#btn-delete-detail").dataset.id = String(sessionId);
        $("#btn-delete-detail").dataset.input = currentDetails.session.input_file || `Run #${sessionId}`;
        $("#btn-delete-detail").onclick = () => deleteRun($("#btn-delete-detail"));
    }

    let diagnosticsReport = "";
    let diagnosticsReady = false;
    const setDiagnosticsActions = (enabled) => {
        diagnosticsReady = enabled;
        $("#btn-save-diagnostics").disabled = !enabled;
        $("#btn-copy-diagnostics").disabled = !enabled;
    };
    $("#btn-diagnostics").addEventListener("click", async () => {
        const button = $("#btn-diagnostics");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        const modal = $("#diagnostics-modal");
        const reportBox = $("#diagnostics-report");
        modal.hidden = false;
        setDiagnosticsActions(false);
        diagnosticsReport = "";
        reportBox.innerText = "Running diagnostics…";
        try {
            if (!hasApi("run_diagnostics")) {
                diagnosticsReport = "Diagnostics are available in the desktop app.";
            } else {
                const result = await api().run_diagnostics(selectedFilePath || "");
                diagnosticsReport = result.success
                    ? result.report
                    : `Diagnostic failed: ${result.error || "Unknown error"}`;
            }
        } catch (error) {
            diagnosticsReport = `Diagnostic failed: ${error.message || "Unknown error"}`;
        } finally {
            reportBox.innerText = diagnosticsReport;
            setDiagnosticsActions(true);
            setButtonBusy(button, false);
        }
    });
    $("#btn-close-diagnostics").addEventListener("click", () => { $("#diagnostics-modal").hidden = true; });
    $("#btn-copy-diagnostics").addEventListener("click", async () => {
        if (!diagnosticsReady) return;
        const button = $("#btn-copy-diagnostics");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        let copied = false;
        if (hasApi("copy_diagnostics_report")) {
            const result = await api().copy_diagnostics_report(diagnosticsReport);
            copied = Boolean(result.success);
        }
        if (!copied && navigator.clipboard) {
            try { await navigator.clipboard.writeText(diagnosticsReport); copied = true; } catch (_) { copied = false; }
        }
        if (!copied) {
            const area = document.createElement("textarea");
            area.value = diagnosticsReport;
            document.body.appendChild(area);
            area.select();
            copied = document.execCommand("copy");
            area.remove();
        }
        button.innerText = copied ? "Copied" : "Copy failed";
        setTimeout(() => { button.innerText = "Copy report"; setButtonBusy(button, false); }, 1800);
    });
    $("#btn-save-diagnostics").addEventListener("click", async () => {
        if (!diagnosticsReady || !hasApi("save_diagnostics_report")) return;
        const button = $("#btn-save-diagnostics");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        try {
            const result = await api().save_diagnostics_report(diagnosticsReport);
            if (result.success) alert(`Report saved to:\n${result.path}`);
        } finally {
            setButtonBusy(button, false);
        }
    });

    $("#btn-authenticate").addEventListener("click", async () => {
        const button = $("#btn-authenticate");
        if (button.dataset.busy === "1") return;
        setButtonBusy(button, true);
        try {
            const state = button.dataset.authState || "expired";
            if (state === "authenticated" || state === "unavailable") {
                const result = await recheckAuthentication();
                if (result.authenticated) {
                    logToConsole("System", appSettings.language === "pt-BR" ? "Sessão do Coupa revalidada." : "Coupa session rechecked.");
                } else if (result.state !== "unavailable") {
                    logToConsole("Warning", appSettings.language === "pt-BR" ? "A sessão do Coupa precisa de autenticação." : "The Coupa session requires sign-in.");
                }
            } else {
                const result = await authenticateWithProgress();
                if (result.success) {
                    updateAuthUI("authenticated");
                    logToConsole("Success", "Coupa authentication successful.");
                } else {
                    updateAuthUI("expired", result.error);
                    logToConsole("Error", result.error || "Authentication failed.");
                }
            }
        } finally {
            setButtonBusy(button, false);
        }
    });

    async function initializeAuth() {
        if (!hasApi("check_auth")) { updateAuthUI("authenticated", "Browser preview"); return; }
        try {
            const result = await recheckAuthentication();
            if (result.authenticated || result.state === "unavailable") {
                return;
            }

            // First launch and an expired Coupa session both require one
            // explicit, visible capture from the existing Edge work profile.
            const authResult = await authenticateWithProgress();
            if (authResult.success) {
                updateAuthUI("authenticated");
                logToConsole("Success", appSettings.language === "pt-BR" ? "Login do Coupa concluído." : "Coupa sign-in completed.");
            } else {
                updateAuthUI("expired", authResult.error);
                logToConsole("Error", authResult.error || "Authentication failed.");
            }
        } catch (error) {
            updateAuthUI("unavailable", error.message);
            logToConsole("Warning", error.message || "Could not check the Coupa session.");
        }
    }

    async function checkForUpdates(manual = false) {
        if ((!manual && !appSettings.auto_updates) || !hasApi("check_updates")) return;
        const manualButton = $("#btn-check-updates");
        if (manual) {
            setButtonBusy(manualButton, true);
            manualButton.disabled = true;
            manualButton.innerText = appSettings.language === "pt-BR" ? "Verificando…" : "Checking…";
            $("#settings-status").innerText = appSettings.language === "pt-BR" ? "Verificando atualizações…" : "Checking for updates…";
        }
        try {
            const result = await api().check_updates();
            if (!result.success || !result.update_available) {
                pendingUpdate = null;
                syncUpdateButton();
                if (manual) {
                    $("#settings-status").innerText = result.success
                        ? (appSettings.language === "pt-BR" ? "Você já está usando a versão mais recente." : "You are already using the latest version.")
                        : (result.error || "Update check failed.");
                }
                return;
            }
            pendingUpdate = result;
            const banner = $("#update-banner");
            banner.hidden = false;
            $("#update-text").innerText = `Version ${result.version} available`;
            syncUpdateButton();
            if (manual) {
                $("#settings-status").innerText = appSettings.language === "pt-BR"
                    ? `Versão ${result.version} disponível. Use o botão de download acima.`
                    : `Version ${result.version} is available. Use the download button above.`;
                $(".main-content").scrollTop = 0;
            }
            $("#btn-download-update").onclick = async () => {
                if (runInProgress || !pendingUpdate) return;
                const button = $("#btn-download-update");
                button.disabled = true;
                button.innerText = "Downloading…";
                const downloaded = await api().download_update(result.download_url, result.asset_name, result.checksum_url);
                if (!downloaded.success) {
                    button.innerText = "Download update";
                    syncUpdateButton();
                    logToConsole("Error", downloaded.error || "Update download failed.");
                    return;
                }
                button.innerText = "Installing…";
                logToConsole("Success", `Update downloaded and verified. Installing version ${result.version}…`);
                if (!hasApi("install_update")) {
                    button.innerText = "Downloaded";
                    logToConsole("Warning", `Automatic installation is unavailable. Package saved at ${downloaded.path}`);
                    syncUpdateButton();
                    return;
                }
                const installed = await api().install_update(downloaded.path);
                if (!installed.success) {
                    button.innerText = "Install update";
                    syncUpdateButton();
                    logToConsole("Error", installed.error || "Update installation failed.");
                    return;
                }
                button.innerText = "Restarting…";
                logToConsole("Success", "The application will restart with the new version.");
            };
        } catch (error) {
            // Update checks are best-effort and never block normal usage.
            console.debug("Update check skipped", error);
            if (manual) $("#settings-status").innerText = error.message || "Update check failed.";
        } finally {
            if (manual) {
                manualButton.disabled = false;
                manualButton.innerText = appSettings.language === "pt-BR" ? "Verificar agora" : "Check now";
                setButtonBusy(manualButton, false);
            }
        }
    }

    let startupChecksDone = false;
    let startupChecksStarted = false;
    async function runStartupChecks() {
        // pywebviewready and the fallback timer can fire close together. Set
        // the guard before awaiting the bridge so startup cannot start two
        // authentication flows and two browser windows.
        if (startupChecksDone || startupChecksStarted) return;
        startupChecksStarted = true;
        // The pywebview bridge may not be exposed yet when the fallback timer
        // fires; retry until the API is actually available so the saved
        // language/font settings are applied on the first render.
        let attempts = 0;
        while (!hasApi("get_app_settings") && attempts < 40) {
            await new Promise((resolve) => setTimeout(resolve, 250));
            attempts += 1;
        }        startupChecksDone = true;
        await loadSettings();
        try { await loadPowerBIScreen(); } catch (_) { /* Power BI status remains visible in the source card. */ }
        await initializeAuth();
        checkForUpdates();
    }
    window.addEventListener("pywebviewready", runStartupChecks);
    setTimeout(runStartupChecks, 150);
});
