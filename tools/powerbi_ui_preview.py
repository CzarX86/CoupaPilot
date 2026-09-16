#!/usr/bin/env python3
"""Serve the Power BI New run UI with a small browser-only preview bridge.

The desktop application normally supplies ``window.pywebview.api``. This
preview keeps the UI interactive in a regular browser without touching the
production pywebview integration or requiring Power BI credentials.
"""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "ContractDownloader" / "src" / "gui" / "web"


PREVIEW_BRIDGE = r"""
(() => {
  const call = async (method, ...args) => {
    const result = window.__powerbiPreviewApi?.[method];
    if (typeof result !== "function") return { success: false, error: `Preview method unavailable: ${method}` };
    return result(...args);
  };
  const suppliers = [
    { alias: "Accenture", official_name: "ACCENTURE PUBLIC LIMITED COMPANY", uu: "WCSCUU61646", provisional: true, source: "Preview cache" },
    { alias: "Infosys", official_name: "INFOSYS LIMITED", uu: "WCSCUU60776", provisional: true, source: "Preview cache" },
    { alias: "Deloitte", official_name: "DELOITTE TOUCHE TOHMATSU LIMITED", uu: "WCSCUU61655", provisional: true, source: "Preview cache" },
    { alias: "EY", official_name: "ERNST & YOUNG GLOBAL LIMITED", uu: "WCSCUU61677", provisional: true, source: "Preview cache" },
    { alias: "Fractal", official_name: "FRACTAL ANALYTICS INC", uu: "WCSCUU93195", provisional: true, source: "Preview cache" },
    { alias: "TCS", official_name: "TATA CONSULTANCY SERVICES LIMITED", uu: "WCSCUU536885", provisional: true, source: "Preview cache" },
    { alias: "NTT", official_name: "NIPPON TELEGRAPH AND TELEPHONE EAST CORPORATION", uu: "WCSCUU67818", provisional: true, source: "Preview cache" },
    { alias: "Capgemini", official_name: "CAPGEMINI OUTSOURCING SERVICES", uu: "WCSCUU208186", provisional: true, source: "Preview cache" },
    { alias: "Cognizant", official_name: "COGNIZANT TECHNOLOGY SOLUTIONS CORPORATION", uu: "WCSCUU60775", provisional: true, source: "Preview cache" },
    { alias: "LTI Mindtree", official_name: "LARSEN AND TOUBRO LIMITED", uu: "WCSCUU75570", provisional: true, source: "Preview cache" }
  ];
  const hierarchy = [
    { l1: "Digital & Technology", l2: "Engineering", l3: "Platforms", l4: "Applications" },
    { l1: "Digital & Technology", l2: "Engineering", l3: "Data", l4: "Analytics" },
    { l1: "Finance", l2: "Controlling", l3: "Procure to Pay", l4: "Operations" },
    { l1: "Human Resources", l2: "People Services", l3: "Talent", l4: "Recruiting" }
  ];
  const families = ["IT Services", "Marketing", "Facilities", "Professional Services"];
  const columns = [
    { key: "po_number", label: "PO number", source: "PurchaseOrder_Allocated[PO Number]", type: "text", default: true, required: true },
    { key: "po_creation_date", label: "PO Creation Date", source: "PurchaseOrder_Allocated[PO Creation Date]", type: "date", default: true },
    { key: "supplier_uu", label: "Supplier UU code", source: "Supplier - Codes[SupplierHierarchyUU]", type: "text", default: true },
    { key: "management_unit_l3", label: "Management Unit L3", source: "Cost Centre[Management Unit L3 Name]", type: "text", default: true },
    { key: "legal_entity_code", label: "Legal Entity code", source: "Company[L4 Legal Entity Code]", type: "text", default: true },
    { key: "company_code", label: "Company code", source: "Company[L5 Company Code]", type: "text", default: true },
    { key: "commitment_value_eur", label: "Commitment value (EUR)", source: "Measure[Commitment Value EUR]", type: "currency", default: true }
  ];
  const rows = [
    { po_number: "PO-1001", po_creation_date: "2025-01-18", supplier_uu: "WCSCUU61655", management_unit_l3: "Platforms", purchase_family: "IT Services", legal_entity_code: "LE-001", legal_entity_name: "Preview Legal Entity", company_code: "1000", commitment_value_eur: 125000 },
    { po_number: "PO-1002", po_creation_date: "2025-04-07", supplier_uu: "WCSCUU67818", management_unit_l3: "Data", purchase_family: "Professional Services", legal_entity_code: "LE-002", legal_entity_name: "Preview Legal Entity", company_code: "2000", commitment_value_eur: 82000 },
    { po_number: "PO-1003", po_creation_date: "2026-02-22", supplier_uu: "WCSCUU61646", management_unit_l3: "Procure to Pay", purchase_family: "Facilities", legal_entity_code: "LE-003", legal_entity_name: "Preview Legal Entity", company_code: "3000", commitment_value_eur: 64000 },
    { po_number: "PO-1004", po_creation_date: "2025-06-14", supplier_uu: "WCSCUU61646", management_unit_l3: "Procure to Pay", purchase_family: "Facilities", legal_entity_code: "LE-003", legal_entity_name: "Preview Legal Entity", company_code: "3000", commitment_value_eur: 51000 },
    { po_number: "PO-1005", po_creation_date: "2026-03-12", supplier_uu: "WCSCUU61646", management_unit_l3: "Procure to Pay", purchase_family: "Marketing", legal_entity_code: "LE-003", legal_entity_name: "Preview Legal Entity", company_code: "3000", commitment_value_eur: 73000 },
    { po_number: "PO-1006", po_creation_date: "2025-08-03", supplier_uu: "WCSCUU61655", management_unit_l3: "Platforms", purchase_family: "IT Services", legal_entity_code: "LE-001", legal_entity_name: "Preview Legal Entity", company_code: "1000", commitment_value_eur: 44000 }
  ];
  const filterRows = (supplierCodes = [], paths = [], datePeriods = [], familyNames = []) => rows.filter((row) => {
    const suppliersMatch = !supplierCodes.length || supplierCodes.includes(row.supplier_uu);
    const datesMatch = !datePeriods.length || datePeriods.includes(row.po_creation_date.slice(0, 7));
    const pathsMatch = !paths.length || paths.some((path) => String(path.l3 || path.l2 || path.l1 || "") === row.management_unit_l3);
    const familiesMatch = !familyNames.length || familyNames.includes(row.purchase_family);
    return suppliersMatch && datesMatch && pathsMatch && familiesMatch;
  });
  const rowsForPOs = (poNumbers = []) => {
    const selected = new Set(poNumbers.map(String));
    return selected.size ? rows.filter((row) => selected.has(row.po_number)) : [];
  };
  const relationshipPreview = {
    success: true,
    session: { id: 1, input_file: "relationship-preview.csv", status: "SUCCESS" },
    sessions: [{ id: 1, input_file: "relationship-preview.csv", status: "SUCCESS", created_at: "2026-08-12", total_pos: 3 }],
    tree: [
      { key: "SOW:preview-001", label: "PREVIEW-001", kind: "sow", evidence: "explicit filename reference", commitment_total_eur: 207000, pos: [
        { key: "PO:PO-1001", label: "PO-1001", kind: "po", status: "SUCCESS", company_code: "1000", commitment_value_eur: 125000, sow_count: 1, documents: [
          { key: "DOCUMENT:PO-1001:1", label: "SOW-PREVIEW-001.pdf", kind: "sow", evidence: "downloaded attachment" }
        ], invoices: [
          { key: "INVOICE:9001:PO-1001:1", label: "INV-9001", kind: "invoice", invoice_number: "INV-9001", reporting_eur: 42000, document_date: "2025-02-03", evidence: "Power BI Invoice dataset" }
        ]},
        { key: "PO:PO-1002", label: "PO-1002", kind: "po", status: "SUCCESS", company_code: "1000", commitment_value_eur: 82000, sow_count: 1, documents: [], invoices: [
          { key: "INVOICE:9002:PO-1002:1", label: "INV-9002", kind: "invoice", invoice_number: "INV-9002", reporting_eur: 28000, document_date: "2025-05-14", evidence: "Power BI Invoice dataset" }
        ]}
      ]},
      { key: "SOW:__unlinked__", label: "SOW not identified", kind: "sow", evidence: "missing relationship key", pos: [
        { key: "PO:PO-1003", label: "PO-1003", kind: "po", status: "SUCCESS", company_code: "1000", sow_count: 0, documents: [
          { key: "DOCUMENT:PO-1003:4", label: "contract.pdf", kind: "document", evidence: "downloaded attachment" }
        ], invoices: []}
      ]}
    ],
    summary: { sows: 1, pos: 3, invoices: 2, documents: 2, warnings: 2, errors: 0 },
    validation: [
      { code: "po_missing_sow", severity: "warning", message: "PO PO-1003 has no identifiable SOW document." },
      { code: "po_missing_invoice", severity: "warning", message: "PO PO-1003 has no identifiable invoice document." }
    ]
  };
  const api = {
    get_app_settings: async () => ({ language: "en", font_scale: 1, download_root: "/tmp/ContractDownloader", concurrency: 4, retry_attempts: 1, msg_processing: "convert_extract", deduplicate_files: true, auto_updates: false, retention: "all", auth_browser: "auto", auth_browsers: { available: [] } }),
    get_concurrency_estimates: async () => ({}),
    check_auth: async () => ({ authenticated: true, message: "Browser preview" }),
    get_powerbi_status: async () => ({ available: true, authenticated: true, message: "Browser preview — simulated Power BI dataset." }),
    get_lab_relationships: async () => relationshipPreview,
    get_powerbi_po_columns: async () => ({ success: true, columns, updated_at: new Date().toISOString() }),
    refresh_powerbi_po_columns: async () => ({ success: true, columns, updated_at: new Date().toISOString(), refreshed: true }),
    get_powerbi_supplier_cache: async () => ({ success: true, suppliers }),
    search_powerbi_suppliers: async (term) => ({ success: true, suppliers: suppliers.concat([{ alias: `${term} Consulting`, official_name: `${term} Consulting Ltd`, uu: "WCSCUU999999", matches: [term], source: "Preview Power BI search" }]) }),
    save_powerbi_suppliers: async (items) => ({ success: true, suppliers: suppliers.concat(items || []) }),
    validate_powerbi_supplier_cache: async () => ({ success: true, checked: suppliers.length, invalid: [] }),
    get_powerbi_management_hierarchy_cache: async () => ({ success: true, paths: hierarchy, updated_at: new Date().toISOString() }),
    get_powerbi_management_hierarchy: async () => ({ success: true, paths: hierarchy, updated_at: new Date().toISOString() }),
    get_powerbi_po_date_range: async () => ({ success: true, min_date: "2021-08-05", max_date: "2026-08-01", updated_at: new Date().toISOString() }),
    refresh_powerbi_po_date_range: async () => ({ success: true, min_date: "2021-08-05", max_date: "2026-08-01", updated_at: new Date().toISOString(), refreshed: true }),
    get_powerbi_purchase_families: async () => ({ success: true, families: families.map((name) => ({ name })), column: "Commodity[L2 Purchase Family Name]", updated_at: new Date().toISOString(), source: "browser-preview" }),
    preview_powerbi_pos: async (_year, supplierCodes = [], paths = [], selectedColumns = [], datePeriods = [], familyNames = []) => {
      const filteredRows = filterRows(supplierCodes.map(String), paths, datePeriods.map(String), familyNames.map(String));
      const query = `-- Browser preview: no request was sent to Power BI.\n-- Simulated filters: supplier_uu_codes=${JSON.stringify(supplierCodes)}, date_periods=${JSON.stringify(datePeriods)}, family_names=${JSON.stringify(familyNames)}`;
      return { success: true, rows: filteredRows, columns: columns.map((item) => item.key), unique_pos: new Set(filteredRows.map((row) => row.po_number)).size, records: filteredRows.length, query_diagnostics: { source: "Browser preview — simulated Power BI dataset", dataset_id: "preview", filters: { supplier_uu_codes: supplierCodes, management_unit_paths: paths, po_creation_periods: datePeriods, date_ranges: [], purchase_families: familyNames }, selected_columns: selectedColumns.length ? selectedColumns : columns.map((item) => item.key), queries: [{ request: { queries: [{ query }] }, rows_returned: filteredRows.length }] } };
    },
    analyze_powerbi_grir: async (poNumbers = []) => ({ success: true, rows: rowsForPOs(poNumbers).map((row) => ({ po_number: row.po_number, goods_received_eur: row.commitment_value_eur * .45, invoice_received_eur: row.commitment_value_eur * .3, variance_eur: row.commitment_value_eur * .15, invoice_count: 2, status: "goods_received_gt_invoice" })) }),
    analyze_powerbi_grir_fx: async (poNumbers = []) => ({ success: true, rows: rowsForPOs(poNumbers).map((row) => ({ po_number: row.po_number, grir_total_eur: row.commitment_value_eur * .15, fx_impact_eur: 1200, po_fx_rate: 1.08, goods_received_fx_rate: 1.08, invoices: [] })) }),
    prepare_powerbi_input: async () => ({ success: true, path: "/tmp/powerbi-preview-input.csv", unique_pos: rows.length, source_metadata: { source: "Power BI PO Mass Download Dataset", filters: {} } }),
    export_powerbi_preview: async () => ({ success: true, path: "/tmp/powerbi-preview.csv", unique_pos: rows.length }),
    cancel_powerbi_query: async () => ({ success: true, cancelled: true })
  };
  window.__powerbiPreviewApi = api;
  window.pywebview = { api };
  setTimeout(() => window.dispatchEvent(new Event("pywebviewready")), 50);
})();
"""


class PreviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        if self.path.split("?", 1)[0] in {"/", "/index.html"}:
            html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
            bridge = f"<script>{PREVIEW_BRIDGE}</script>"
            html = html.replace('<script src="app.js"></script>', f"{bridge}<script src=\"app.js\"></script>")
            payload = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()

    def log_message(self, format: str, *args: object) -> None:
        print(format % args)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0, help="Port to bind; 0 chooses an available local port.")
    args = parser.parse_args()
    handler = partial(PreviewHandler, directory=str(WEB_ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Power BI UI preview: http://127.0.0.1:{server.server_port}/index.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
