import pytest

from src.powerbi_provider import DATASET_ID, INVOICE_DATASET_ID, PRIORITY_SUPPLIERS, PowerBIError, PowerBIProvider


def test_po_column_catalog_exposes_confirmed_dataset_fields():
    columns = PowerBIProvider.po_columns()

    assert len(columns) >= 15
    assert columns[0]["key"] == "po_number"
    assert columns[0]["required"] is True
    assert any(column["source"] == "Cost Centre[Management Unit L6 Name]" for column in columns)
    assert columns[0]["table"] == "PurchaseOrder_Allocated"
    assert columns[0]["column"] == "PO Number"


def test_po_column_catalog_exposes_download_folder_fields():
    columns = {column["key"]: column for column in PowerBIProvider.po_columns()}

    assert columns["crg"]["label"] == "CRG"
    assert columns["crg"]["source"] == "Cost Centre[Cost Reporting Group Code]"
    assert columns["year"]["label"] == "Year"
    assert columns["year"]["source"] == "PurchaseOrder_Allocated[Year]"
    assert columns["crg"]["default"] is False
    assert columns["year"]["default"] is False


def test_discover_po_columns_includes_all_metadata_columns_and_origin(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)

    def fake_get_json(arguments, **_kwargs):
        path = " ".join(arguments)
        if f"datasets/{DATASET_ID}/tables" in path and "/columns" not in path:
            return {"value": [{"name": "PurchaseOrder_Allocated", "displayName": "Purchase Orders"}]}
        return {
            "value": [
                {"name": "PO Number", "displayName": "PO number", "dataType": "string"},
                {"name": "New Metadata Field", "dataType": "dateTime", "isHidden": True},
            ]
        }

    monkeypatch.setattr(provider, "_get_json", fake_get_json)
    columns = provider.discover_po_columns()
    discovered = next(column for column in columns if column["column"] == "New Metadata Field")

    assert discovered["table"] == "PurchaseOrder_Allocated"
    assert discovered["table_label"] == "Purchase Orders"
    assert discovered["source"] == "PurchaseOrder_Allocated[New Metadata Field]"
    assert discovered["group"] == "Purchase Orders"
    assert discovered["data_type"] == "dateTime"
    assert discovered["type"] == "date"
    assert discovered["hidden"] is True


def test_preview_uses_discovered_metadata_column(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    provider.set_po_columns([
        {
            "key": "dataset_purchase_order_new_field_123",
            "label": "New Metadata Field",
            "group": "Purchase Orders",
            "source": "PurchaseOrder_Allocated[New Metadata Field]",
            "table": "PurchaseOrder_Allocated",
            "column": "New Metadata Field",
            "type": "date",
        },
        {
            "key": "po_number",
            "label": "PO number",
            "source": "PurchaseOrder_Allocated[PO Number]",
            "table": "PurchaseOrder_Allocated",
            "column": "PO Number",
            "required": True,
        },
    ])

    captured = {}

    def fake_run_json(_args, payload, **_kwargs):
        captured["query"] = payload["queries"][0]["query"]
        return {
            "status_code": 200,
            "text": {"results": [{"tables": [{"rows": [{
                "PurchaseOrder_Allocated[PO Number]": "PO100",
                "PurchaseOrder_Allocated[New Metadata Field]": "2026-08-01",
            }]}]}]},
        }

    monkeypatch.setattr(provider, "_run_json", fake_run_json)
    rows = provider.preview_pos("2026", [], columns=["dataset_purchase_order_new_field_123"])

    assert rows == [{
        "po_number": "PO100",
        "dataset_purchase_order_new_field_123": "2026-08-01",
    }]
    assert "'PurchaseOrder_Allocated'[New Metadata Field]" in captured["query"]


def test_preview_uses_only_selected_po_columns_and_keeps_po_number(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    captured = {}

    def fake_run_json(_args, payload, **_kwargs):
        captured["query"] = payload["queries"][0]["query"]
        return {
            "status_code": 200,
            "text": {"results": [{"tables": [{"rows": [{
                "PurchaseOrder_Allocated[PO Number]": "PO100",
                "Cost Centre[Management Unit L1 Name]": "Digital",
                "[PO document amount]": 125,
                "[Goods Received Value EUR]": 80,
            }]}]}]},
        }

    monkeypatch.setattr(provider, "_run_json", fake_run_json)
    rows = provider.preview_pos("2026", [], columns=["management_unit_l1", "po_document_amount", "goods_received_value_eur"])

    assert rows == [{
        "po_number": "PO100",
        "management_unit_l1": "Digital",
        "po_document_amount": 125,
        "goods_received_value_eur": 80,
    }]
    assert "'PurchaseOrder_Allocated'[PO Number]" in captured["query"]
    assert "'Cost Centre'[Management Unit L1 Name]" in captured["query"]
    assert '"PO document amount", SUM(\'Purchase Order\'[DocumentCurrencyAmount])' in captured["query"]
    assert "'Cost Centre'[Management Unit L3 Name]" not in captured["query"]


def test_preview_fetches_crg_and_year_for_folder_selection(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    captured = {}

    def fake_run_json(_args, payload, **_kwargs):
        captured["query"] = payload["queries"][0]["query"]
        return {
            "status_code": 200,
            "text": {"results": [{"tables": [{"rows": [{
                "PurchaseOrder_Allocated[PO Number]": "PO100",
                "Cost Centre[Cost Reporting Group Code]": "R5600",
                "PurchaseOrder_Allocated[Year]": "2026",
            }]}]}]},
        }

    monkeypatch.setattr(provider, "_run_json", fake_run_json)
    rows = provider.preview_pos("", [], columns=["po_number"])

    assert rows == [{"po_number": "PO100", "crg": "R5600", "year": "2026"}]
    assert "'Cost Centre'[Cost Reporting Group Code]" in captured["query"]
    assert "'PurchaseOrder_Allocated'[Year]" in captured["query"]


def test_preview_rejects_unknown_po_column(tmp_path):
    provider = PowerBIProvider(tmp_path)

    with pytest.raises(PowerBIError, match="Unsupported PO dataset column"):
        provider.preview_pos("2026", [], columns=["not_a_dataset_column"])


def test_preview_filters_confirmed_po_creation_date_periods(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    captured = {}

    def fake_run_json(_args, payload, **_kwargs):
        captured["query"] = payload["queries"][0]["query"]
        return {
            "status_code": 200,
            "text": {"results": [{"tables": [{"rows": [{
                "PurchaseOrder_Allocated[PO Number]": "PO100",
            }]}]}]},
        }

    monkeypatch.setattr(provider, "_run_json", fake_run_json)
    rows = provider.preview_pos(
        "",
        [],
        columns=["po_number"],
        date_periods=["2025-01", "2025-02"],
    )

    assert rows == [{"po_number": "PO100"}]
    assert "'PurchaseOrder_Allocated'[PO Creation Date] >= 20250101" in captured["query"]
    assert "'PurchaseOrder_Allocated'[PO Creation Date] < 20250301" in captured["query"]


def test_po_creation_date_range_normalizes_provider_response(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    monkeypatch.setattr(
        provider,
        "_run_json",
        lambda *_args, **_kwargs: {
            "text": {"results": [{"tables": [{"rows": [{
                "[Min PO Creation Date]": "2021-08-05T00:00:00Z",
                "[Max PO Creation Date]": "2026-08-01T00:00:00Z",
            }]}]}]},
        },
    )

    assert provider.po_creation_date_range() == {
        "min_date": "2021-08-05",
        "max_date": "2026-08-01",
    }


def test_powerbi_date_value_normalizes_integer_model_date(tmp_path):
    provider = PowerBIProvider(tmp_path)

    assert provider._normalize_powerbi_date(20260808) == "2026-08-08"


def test_priority_supplier_seed_contains_confirmed_codes():
    codes = {item["alias"]: item["uu"] for item in PRIORITY_SUPPLIERS}

    assert list(codes) == [
        "Accenture", "Infosys", "Deloitte", "EY", "Fractal",
        "TCS", "NTT", "Capgemini", "Cognizant", "LTI Mindtree",
    ]
    assert codes["Deloitte"] == "WCSCUU61655"
    assert codes["EY"] == "WCSCUU61677"
    assert codes["Fractal"] == "WCSCUU93195"
    assert codes["TCS"] == "WCSCUU536885"


def test_search_groups_supplier_hierarchy_and_keeps_sap_codes(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    monkeypatch.setattr(
        provider,
        "_run_json",
        lambda *_args, **_kwargs: {
            "text": {
                "results": [{
                    "tables": [{
                        "rows": [
                            {
                                "Supplier - Codes[SupplierHierarchyUU]": "DELOITTE TOUCHE TOHMATSU LIMITED:WCSCUU61655",
                                "Supplier - Codes[SupplierHierarchyGU]": "DELOITTE TOUCHE TOHMATSU LIMITED:WCSCGU1915",
                                "Supplier - Codes[SupplierHierarchyS]": "Deloitte Brazil:0050000001",
                            },
                            {
                                "Supplier - Codes[SupplierHierarchyUU]": "DELOITTE TOUCHE TOHMATSU LIMITED:WCSCUU61655",
                                "Supplier - Codes[SupplierHierarchyGU]": "DELOITTE TOUCHE TOHMATSU LIMITED:WCSCGU1915",
                                "Supplier - Codes[SupplierHierarchyS]": "Deloitte UK:0050000002",
                            },
                        ]
                    }]
                }]
            },
            "status_code": 200,
        },
    )

    result = provider.search_suppliers("Deloitte")

    assert len(result) == 1
    assert result[0]["uu"] == "WCSCUU61655"
    assert result[0]["sap_codes"] == ["0050000001", "0050000002"]


def test_search_in_lower_supplier_level_returns_associated_uu(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    monkeypatch.setattr(
        provider,
        "_run_json",
        lambda *_args, **_kwargs: {
            "status_code": 200,
            "text": {"results": [{"tables": [{"rows": [{
                "Supplier - Codes[SupplierHierarchyUU]": "LARSEN AND TOUBRO LIMITED:WCSCUU75570",
                "Supplier - Codes[SupplierHierarchyGU]": "LARSEN AND TOUBRO LIMITED:WCSCGU1234",
                "Supplier - Codes[SupplierHierarchyS]": "Mindtree:0050000001",
            }]}]}]},
        },
    )

    result = provider.search_suppliers("Mindtree")

    assert len(result) == 1
    assert result[0]["uu"] == "WCSCUU75570"
    assert result[0]["official_name"] == "LARSEN AND TOUBRO LIMITED"
    assert "Mindtree" in result[0]["matches"]


def test_delete_supplier_removes_only_custom_mapping(tmp_path):
    provider = PowerBIProvider(tmp_path)
    provider.save_suppliers([{"alias": "Example", "official_name": "Example Ltd", "uu": "WCSCUU999999"}])

    remaining = provider.delete_supplier("WCSCUU999999")

    assert not any(item["uu"] == "WCSCUU999999" for item in remaining)
    assert any(item["uu"] == "WCSCUU61655" for item in remaining)


def test_supplier_cache_persists_custom_entries_without_replacing_priority(tmp_path):
    provider = PowerBIProvider(tmp_path)
    custom = {"alias": "Example Supplier", "official_name": "Example Supplier Ltd", "uu": "WCSCUU999999", "source": "Power BI"}

    saved = provider.save_suppliers([custom])

    assert any(item["uu"] == "WCSCUU61655" for item in saved)
    assert any(item["uu"] == "WCSCUU999999" for item in saved)
    assert provider.cache_path.is_file()


def test_preview_uses_normalized_uu_name_from_model_label(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    captured = {}

    def fake_run_json(_args, payload, **_kwargs):
        captured["query"] = payload["queries"][0]["query"]
        return {
            "status_code": 200,
            "text": {"results": [{"tables": [{"rows": [{
                "PurchaseOrder_Allocated[PO Number]": "PO100",
                "Supplier - Codes[SupplierHierarchyUU]": "DELOITTE TOUCHE TOHMATSU LIMITED:WCSCUU61655",
                "Cost Centre[Management Unit L3 Name]": "Technology",
                "Company[L4 Legal Entity Code]": "5069",
                "Company[L4 Legal Entity Name]": "Example Entity",
                "Company[L5 Company Code]": "5069",
                "Company[L5 Company Name]": "5069:Example",
                "[Commitment Value EUR]": 10,
                "[Goods Received Value EUR]": 5,
            }]}]}]},
        }

    monkeypatch.setattr(provider, "_run_json", fake_run_json)
    rows = provider.preview_pos("2026", ["WCSCUU61655"])

    assert "WCSCUU61655" in captured["query"]
    assert rows[0]["supplier_uu"] == "DELOITTE TOUCHE TOHMATSU LIMITED"
    assert rows[0]["company_code"] == "5069"


def test_validate_normalizes_full_model_label_to_uu_code(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    monkeypatch.setattr(
        provider,
        "_run_json",
        lambda *_args, **_kwargs: {
            "status_code": 200,
            "text": {"results": [{"tables": [{"rows": [{
                "Supplier - Codes[SupplierHierarchyUU]": "DELOITTE TOUCHE TOHMATSU LIMITED:WCSCUU61655",
            }]}]}]},
        },
    )

    result = provider.validate_supplier_cache()

    assert result["checked"] == 10
    assert any(item["uu"] == "WCSCUU61655" for item in result["valid"])


def test_analyze_grir_joins_full_po_lifecycle_without_date_filters(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    calls = []

    def fake_run_json(arguments, payload, **_kwargs):
        calls.append((arguments, payload["queries"][0]["query"]))
        if "Purchase Order" in payload["queries"][0]["query"]:
            rows = [{
                "Purchase Order[PO Number]": "PO100",
                "[Goods Received EUR]": 120,
                "[PO Lines]": 2,
            }]
        else:
            rows = [{
                "Invoice[PO Number]": "PO100",
                "[Invoice Received EUR]": 95,
                "[Invoice Ledger Lines]": 3,
                "[Invoice Documents]": 2,
                "[Invoice Numbers]": 2,
            }]
        return {"status_code": 200, "text": {"results": [{"tables": [{"rows": rows}]}]}}

    monkeypatch.setattr(provider, "_run_json", fake_run_json)
    result = provider.analyze_grir(["PO100", "UNK"])

    assert result == [{
        "po_number": "PO100",
        "goods_received_eur": 120.0,
        "invoice_received_eur": 95.0,
        "variance_eur": 25.0,
        "po_lines": 2,
        "invoice_count": 2,
        "invoice_ledger_lines": 3,
        "status": "goods_received_gt_invoice",
    }]
    assert len(calls) == 2
    assert all("Time" not in query and "Year" not in query for _, query in calls)


def test_analyze_grir_fx_returns_invoice_details_and_separates_fx_impact(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    calls = []

    def fake_execute(dataset_id, query, **_kwargs):
        calls.append((dataset_id, query))
        if dataset_id == "45f78e7b-bb55-42f4-a5e3-8b790e6dfbb3":
            return [{
                "Purchase Order[PO Number]": "PO100",
                "[PO Document Amount]": 1000,
                "[PO Reporting EUR]": 1100,
                "[Goods Received Document Amount]": 900,
                "[Goods Received EUR]": 990,
                "[PO Currencies]": 1,
            }]
        return [
            {
                "Invoice[PO Number]": "PO100",
                "Invoice[PO Line Number]": "00010",
                "Invoice[Purchase Invoice Number]": "INV-1",
                "Invoice[Accounting Document Number]": "DOC-1",
                "Invoice[Document Date]": "2025-01-01",
                "Document Currency[Document Currency Code]": "GBP",
                "[Invoice Document Amount]": 600,
                "[Invoice Reporting EUR]": 650,
                "[Invoice Ledger Lines]": 2,
            },
            {
                "Invoice[PO Number]": "PO100",
                "Invoice[PO Line Number]": "00010",
                "Invoice[Purchase Invoice Number]": "INV-2",
                "Invoice[Accounting Document Number]": "DOC-2",
                "Invoice[Document Date]": "2025-02-01",
                "Document Currency[Document Currency Code]": "GBP",
                "[Invoice Document Amount]": 300,
                "[Invoice Reporting EUR]": 330,
                "[Invoice Ledger Lines]": 1,
            },
        ]

    monkeypatch.setattr(provider, "_execute_dataset_query", fake_execute)
    result = provider.analyze_grir_fx(["PO100", "UNK"])

    assert result[0]["po_number"] == "PO100"
    assert result[0]["po_fx_rate"] == 1.1
    assert result[0]["goods_received_fx_rate"] == 1.1
    assert result[0]["invoice_received_eur"] == 980.0
    assert result[0]["grir_total_eur"] == 10.0
    assert result[0]["fx_impact_eur"] == -10.0
    assert result[0]["grir_ex_fx_eur"] == 0.0
    assert result[0]["invoices"][0]["status"] == "fx_variance"
    assert result[0]["invoices"][0]["fx_impact_eur"] == -10.0
    assert len(calls) == 2
    assert all("Time" not in query and "Year" not in query for _, query in calls)


def test_analyze_grir_fx_does_not_invent_rate_for_zero_invoice_amount(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)

    def fake_execute(dataset_id, _query, **_kwargs):
        if dataset_id == "45f78e7b-bb55-42f4-a5e3-8b790e6dfbb3":
            return [{
                "Purchase Order[PO Number]": "PO100",
                "[PO Document Amount]": 100,
                "[PO Reporting EUR]": 110,
                "[Goods Received Document Amount]": 100,
                "[Goods Received EUR]": 110,
                "[PO Currencies]": 1,
            }]
        return [{
            "Invoice[PO Number]": "PO100",
            "Invoice[Purchase Invoice Number]": "INV-1",
            "[Invoice Document Amount]": 0,
            "[Invoice Reporting EUR]": 0,
            "[Invoice Ledger Lines]": 1,
        }]

    monkeypatch.setattr(provider, "_execute_dataset_query", fake_execute)
    invoice = provider.analyze_grir_fx(["PO100"])[0]["invoices"][0]

    assert invoice["invoice_fx_rate"] is None
    assert invoice["fx_impact_eur"] is None
    assert invoice["status"] == "no_invoice_fx"


def test_relationship_data_exposes_po_commitment_and_invoice_rows(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)

    def fake_execute(dataset_id, _query, **_kwargs):
        if dataset_id == DATASET_ID:
            return [{
                "Purchase Order[PO Number]": "PO100",
                "[Commitment Value EUR]": 500000,
                "[PO Document Amount]": 500000,
                "[PO Reporting EUR]": 500000,
                "[Goods Received Document Amount]": 0,
                "[Goods Received EUR]": 0,
                "[PO Currencies]": 1,
            }]
        return [{
            "Invoice[PO Number]": "PO100",
            "Invoice[Purchase Invoice Number]": "INV-1",
            "Invoice[Accounting Document Number]": "DOC-1",
            "Invoice[Document Date]": "2026-08-01",
            "[Invoice Document Amount]": 100,
            "[Invoice Reporting EUR]": 110,
            "[Invoice Ledger Lines]": 2,
        }]

    monkeypatch.setattr(provider, "_execute_dataset_query", fake_execute)

    result = provider.relationship_data(["PO100"])

    assert result["pos"]["PO100"]["commitment_value_eur"] == 500000.0
    assert result["invoices"]["PO100"][0]["invoice_number"] == "INV-1"
    assert result["invoices"]["PO100"][0]["reporting_eur"] == 110.0


def test_purchase_family_column_discovered_from_info_view_metadata(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)

    def fake_run_json(_args, payload, **_kwargs):
        assert payload["queries"][0]["query"] == "EVALUATE INFO.VIEW.COLUMNS()"
        return {
            "text": {"results": [{"tables": [{"rows": [
                {"[Table]": "Commodity", "[Name]": "L2 Purchase Family Name", "[IsHidden]": False},
                {"[Table]": "Commodity", "[Name]": "L4 Purchase Commodity Name", "[IsHidden]": False},
            ]}]}]},
        }

    monkeypatch.setattr(provider, "_run_json", fake_run_json)

    table, column = provider._purchase_family_column()

    assert (table, column) == ("Commodity", "L2 Purchase Family Name")
    assert provider._discovered_family_column == ("Commodity", "L2 Purchase Family Name")


def test_purchase_family_column_falls_back_to_constants(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)

    def fake_run_json(_args, _payload, **_kwargs):
        raise PowerBIError("metadata unavailable")

    monkeypatch.setattr(provider, "_run_json", fake_run_json)

    table, column = provider._purchase_family_column()

    assert (table, column) == ("Commodity", "L2 Purchase Family Name")


def test_purchase_families_returns_column_and_distinct_names(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    provider._discovered_family_column = ("Purchase Family", "Purchase Family L4 Name")
    captured = {}

    def fake_run_json(_args, payload, **_kwargs):
        captured["query"] = payload["queries"][0]["query"]
        return {
            "status_code": 200,
            "text": {"results": [{"tables": [{"rows": [
                {"Purchase Family L4 Name": "IT Services"},
                {"Purchase Family L4 Name": "Marketing"},
                {"Purchase Family L4 Name": "IT Services"},
                {"Purchase Family L4 Name": ""},
            ]}]}]},
        }

    monkeypatch.setattr(provider, "_run_json", fake_run_json)

    result = provider.purchase_families()

    assert result["column"] == "'Purchase Family'[Purchase Family L4 Name]"
    assert result["families"] == [{"name": "IT Services"}, {"name": "Marketing"}]
    assert "SUMMARIZECOLUMNS('Commodity'[L1 Procurement Team Name], 'Purchase Family'[Purchase Family L4 Name])" in captured["query"]
    assert result["hierarchy"] == [{"name": "Unassigned", "families": [{"name": "IT Services"}, {"name": "Marketing"}]}]


def test_purchase_families_returns_l1_l2_hierarchy(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)

    monkeypatch.setattr(
        provider,
        "_run_json",
        lambda *_args, **_kwargs: {
            "status_code": 200,
            "text": {"results": [{"tables": [{"rows": [
                {
                    "Commodity[L1 Procurement Team Name]": "IT and Telecoms",
                    "Commodity[L2 Purchase Family Name]": "IT Services",
                },
                {
                    "Commodity[L1 Procurement Team Name]": "IT and Telecoms",
                    "Commodity[L2 Purchase Family Name]": "IT Telecom",
                },
                {
                    "Commodity[L1 Procurement Team Name]": "Marketing",
                    "Commodity[L2 Purchase Family Name]": "Media",
                },
            ]}]}]},
        },
    )

    result = provider.purchase_families()

    assert result["hierarchy"] == [
        {"name": "IT and Telecoms", "families": [{"name": "IT Services"}, {"name": "IT Telecom"}]},
        {"name": "Marketing", "families": [{"name": "Media"}]},
    ]


def test_preview_filters_by_discovered_family_column(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)
    provider._discovered_family_column = ("Purchase Family", "Purchase Family L4 Name")
    captured = {}

    def fake_run_json(_args, payload, **_kwargs):
        captured["query"] = payload["queries"][0]["query"]
        return {"status_code": 200, "text": {"results": [{"tables": [{"rows": []}]}]}}

    monkeypatch.setattr(provider, "_run_json", fake_run_json)

    provider.preview_pos("", [], date_periods=["2026-01"], family_names=["IT Services", "Marketing"])

    assert "TREATAS({\"IT Services\", \"Marketing\"}, 'Purchase Family'[Purchase Family L4 Name])" in captured["query"]


def test_preview_returns_query_diagnostics(tmp_path, monkeypatch):
    provider = PowerBIProvider(tmp_path)

    monkeypatch.setattr(
        provider,
        "_run_json",
        lambda *_args, **_kwargs: {"status_code": 200, "text": {"results": [{"tables": [{"rows": []}]}]}},
    )

    provider.preview_pos(
        "",
        ["WCSCUU61655"],
        management_paths=[{"l1": "Digital", "l2": "Engineering"}],
        columns=["po_number"],
        date_periods=["2025-01", "2025-02"],
        family_names=["IT Services"],
    )

    diagnostics = provider.last_preview_diagnostics()
    assert diagnostics["filters"]["supplier_uu_codes"] == ["WCSCUU61655"]
    assert diagnostics["filters"]["po_creation_periods"] == ["2025-01", "2025-02"]
    assert diagnostics["filters"]["purchase_families"] == ["IT Services"]
    assert diagnostics["queries"]
    assert "20250101" in diagnostics["queries"][0]["request"]["queries"][0]["query"]
