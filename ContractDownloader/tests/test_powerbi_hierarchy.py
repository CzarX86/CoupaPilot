import json
import subprocess
from pathlib import Path

import pandas as pd

from process_all_pos import _build_output_subdir, _extract_hierarchy_columns, create_session_from_csv
from src.db.session_db import SessionDB


APP_JS = Path(__file__).parents[1] / "src" / "gui" / "web" / "app.js"
WEB_ROOT = APP_JS.parent


def test_management_unit_group_accepts_actual_digital_ampersand_label():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({json.dumps(str(APP_JS))}, "utf8");
const context = {{ document: {{ addEventListener() {{}} }} }};
vm.createContext(context);
vm.runInContext(source + `
this.__result = [
    isDigitalManagementUnit("Digital & Technology"),
    isDigitalManagementUnit(" digital   &   technology "),
    isDigitalManagementUnit("Finance"),
];`, context);
process.stdout.write(JSON.stringify(context.__result));
"""
    result = subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    )

    assert json.loads(result.stdout) == [True, True, False]


def test_po_column_picker_stays_in_the_powerbi_workspace():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = APP_JS.read_text(encoding="utf-8")

    # The picker remains a discreet, clickable column summary in the Power BI
    # workspace. New Run reuses that workspace after the source is selected.
    assert 'id="powerbi-column-summary"' in html
    assert 'id="new-run-powerbi-column-summary"' not in html
    assert 'id="powerbi-columns-modal"' in html
    assert 'id="btn-powerbi-columns"' in html
    assert 'id="btn-refresh-powerbi-columns"' in html
    assert 'id="powerbi-po-preview-head"' in html
    assert 'id="powerbi-supplier-search"' in html
    assert 'id="btn-powerbi-search"' in html
    assert 'id="btn-powerbi-add-suppliers"' in html
    assert "get_powerbi_po_columns" in javascript
    assert "get_powerbi_po_column_selection" in javascript
    assert "save_powerbi_po_column_selection" in javascript
    assert "refresh_powerbi_po_columns" in javascript
    assert "table_label" in javascript
    assert "powerBISelectedColumnSpecs" in javascript
    assert '"#powerbi-column-summary")?.addEventListener("click", openPowerBIColumnModal)' in javascript
    assert "POWERBI_SELECTED_COLUMNS_STORAGE_KEY" in javascript
    assert "prepare_powerbi_input(rows, filters, [...powerbiSelectedColumns])" in javascript


def test_powerbi_source_is_primary_new_run_input_with_date_and_access_checks():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = APP_JS.read_text(encoding="utf-8")
    provider = (APP_JS.parent.parent.parent / "powerbi_provider.py").read_text(encoding="utf-8")
    pipeline = (APP_JS.parent.parent.parent.parent / "process_all_pos.py").read_text(encoding="utf-8")

    assert html.index("Power BI PO Mass Download Dataset") < html.index("Create template")
    assert 'data-input-method="powerbi"' in html
    assert 'data-input-method="excel"' in html
    assert 'id="new-run-powerbi-source-area"' in html
    assert 'id="powerbi-date-hierarchy"' in html
    assert 'id="btn-powerbi-use-new-run"' not in html
    assert 'id="btn-powerbi-export"' not in html
    assert 'id="btn-next-input"' in html
    assert "preparePowerBIInputForNewRun" in javascript
    assert "PO Creation Date" in provider
    assert "preflight_company_access" in pipeline or "preflight_company_access" in (APP_JS.parent.parent.parent / "engine" / "crawler.py").read_text(encoding="utf-8")


def test_relationship_explorer_renders_powerbi_invoice_children_and_commitments():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = APP_JS.read_text(encoding="utf-8")

    assert "Power BI PO/Invoice" in html
    assert "Array.isArray(po.invoices)" in javascript
    assert "Power BI invoice" in javascript
    assert "commitment_value_eur" in javascript
    assert "reporting_eur" in javascript


def test_new_run_powerbi_filters_use_compact_grouped_dropdowns():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = APP_JS.read_text(encoding="utf-8")

    assert 'class="powerbi-filter-bar"' in html
    assert 'id="powerbi-supplier-filter"' in html
    assert 'id="powerbi-management-unit-filter"' in html
    assert 'id="powerbi-date-filter"' in html
    assert "Other Power BI suppliers" in javascript
    assert "Search any supplier, UU, GU or SAP code" in html
    assert "powerbi-date-branch" in javascript
    assert "powerbiFamilyHierarchy" in javascript
    assert "L1 Procurement Team" in html
    assert "L2 Purchase Family" in html
    assert 'event.stopPropagation()' in javascript
    assert "Where the information comes from" in html


def test_start_over_rebuilds_supplier_dropdown_from_persistent_cache():
    javascript = APP_JS.read_text(encoding="utf-8")
    reset = javascript.split("function resetPowerBIRunState()", 1)[1].split(
        "\n    function clearFile()", 1
    )[0]

    assert "showPowerBICacheResults();" in reset
    assert "powerbiSearchResults = [];" not in reset


def test_new_run_has_three_steps_and_inline_folder_approval():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = APP_JS.read_text(encoding="utf-8")

    assert html.count('data-journey-step="') == 3
    assert html.count('data-journey-panel="') == 3
    assert 'id="folder-approval"' in html
    assert 'id="btn-start-run"' in html
    assert 'id="btn-next-review"' not in html
    assert 'id="folder-approval"' in html.split('data-journey-panel="3"', 1)[1]
    assert 'id="folder-approval"' not in html.split('data-journey-panel="3"', 1)[0]
    assert 'window.confirm("This is the folder structure that will be created.' not in javascript
    assert '3: "btn-start-run"' in javascript


def test_drag_and_drop_stages_files_when_the_webview_hides_their_path():
    javascript = APP_JS.read_text(encoding="utf-8")

    assert "stage_dropped_file" in javascript
    assert "readAsDataURL" in javascript
    assert "selectDroppedFile(file)" in javascript


def test_start_does_not_revalidate_an_already_validated_input():
    javascript = APP_JS.read_text(encoding="utf-8")
    start_flow = javascript.split("async function startRunFlow()", 1)[1].split(
        '\n    $("#btn-start-run").addEventListener', 1
    )[0]

    assert "const validation = selectedFileValidated" in start_flow
    assert "? { valid: true }" in start_flow
    assert ": await validateCurrentFile();" in start_flow


def test_explicit_folder_selection_does_not_reenable_other_powerbi_columns():
    frame = pd.DataFrame([{
        "PO_NUMBER": "PO100",
        "SUPPLIER": "Example Supplier",
        "<|>": "",
        "CRG": "R5600",
        "YEAR": "2026",
        "MANAGEMENT_UNIT": "Technology",
    }])

    hierarchy, has_data = _extract_hierarchy_columns(frame, ["SUPPLIER"])

    assert hierarchy == ["SUPPLIER"]
    assert has_data is True
    assert _build_output_subdir(frame.iloc[0], "Example Supplier", hierarchy, has_data) == "Example_Supplier"


def test_repeated_supplier_values_do_not_create_nested_supplier_folders():
    row = pd.Series({"SUPPLIER_GU_CODE": "EY", "SUPPLIER_S_CODE": "EY"})

    output_subdir = _build_output_subdir(
        row,
        "EY",
        ["SUPPLIER_GU_CODE", "SUPPLIER_S_CODE"],
        True,
    )

    assert output_subdir == "EY"


def test_powerbi_crg_and_year_are_optional_folder_levels():
    frame = pd.DataFrame([{
        "PO_NUMBER": "PO100",
        "SUPPLIER": "Example Supplier",
        "<|>": "",
        "CRG": "R5600",
        "YEAR": "2026",
    }])

    hierarchy, has_data = _extract_hierarchy_columns(frame, ["SUPPLIER", "CRG", "YEAR"])

    assert hierarchy == ["SUPPLIER", "CRG", "YEAR"]
    assert has_data is True
    assert _build_output_subdir(frame.iloc[0], "Example Supplier", hierarchy, has_data) == "Example_Supplier/R5600/2026"


def test_supplier_stays_in_the_explicit_middle_position():
    frame = pd.DataFrame([{
        "PO_NUMBER": "PO100",
        "SUPPLIER": "Example Supplier",
        "<|>": "",
        "CRG": "R5600",
        "YEAR": "2026",
    }])

    hierarchy, has_data = _extract_hierarchy_columns(
        frame,
        ["YEAR", "SUPPLIER", "CRG"],
    )

    assert hierarchy == ["YEAR", "SUPPLIER", "CRG"]
    assert _build_output_subdir(
        frame.iloc[0],
        "Example Supplier",
        hierarchy,
        has_data,
    ) == "2026/Example_Supplier/R5600"


def test_worker_session_persists_the_explicit_supplier_position(tmp_path):
    csv_path = tmp_path / "ordered.csv"
    csv_path.write_text(
        "PO_NUMBER;SUPPLIER;<|>;Year;CRG\n"
        "PO100;Example Supplier;;2026;R5600\n",
        encoding="utf-8",
    )
    db = SessionDB(str(tmp_path / "session.db"))
    try:
        session_id, count = create_session_from_csv(
            db,
            str(csv_path),
            hierarchy_order=["Year", "SUPPLIER", "CRG"],
        )
        row = db.conn.execute(
            "SELECT output_subdir FROM po_downloads WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    finally:
        db.close()

    assert count == 1
    assert row["output_subdir"] == "2026/Example_Supplier/R5600"
