from src.reports.lab_relationships import build_lab_relationships
from src.db.session_db import PODownload, SessionDB
from src.gui.api import AppAPI


def test_builds_sow_po_invoice_tree_from_captured_attachments():
    view = build_lab_relationships(
        [
            {"po_number": "PO-1", "status": "SUCCESS", "company_code": "1000"},
            {"po_number": "PO-2", "status": "SUCCESS", "company_code": "1000"},
        ],
        [
            {"id": 1, "po_number": "PO-1", "attachment_name": "SOW-ABC123.pdf", "sha256": "sow"},
            {"id": 2, "po_number": "PO-2", "attachment_name": "SOW-ABC123.pdf", "sha256": "sow"},
            {"id": 3, "po_number": "PO-1", "attachment_name": "Invoice-9001.pdf"},
            {"id": 4, "po_number": "PO-2", "attachment_name": "Invoice-9002.pdf"},
        ],
    )

    assert view["summary"] == {
        "sows": 1,
        "pos": 2,
        "invoices": 2,
        "documents": 4,
        "warnings": 0,
        "errors": 0,
    }
    assert view["tree"][0]["label"] == "ABC123"
    assert [row["label"] for row in view["tree"][0]["pos"]] == ["PO-1", "PO-2"]


def test_flags_multiple_sows_and_invoice_owners():
    view = build_lab_relationships(
        [{"po_number": "PO-1"}, {"po_number": "PO-2"}],
        [
            {"id": 1, "po_number": "PO-1", "attachment_name": "SOW-A.pdf"},
            {"id": 2, "po_number": "PO-1", "attachment_name": "SOW-B.pdf"},
            {"id": 3, "po_number": "PO-1", "attachment_name": "Invoice-9001.pdf"},
            {"id": 4, "po_number": "PO-2", "attachment_name": "Invoice-9001.pdf"},
        ],
    )

    codes = {item["code"] for item in view["validation"]}
    assert {"po_multiple_sows", "po_missing_sow", "invoice_multiple_pos"} <= codes
    assert view["summary"]["errors"] == 2


def test_keeps_unlinked_records_visible():
    view = build_lab_relationships(
        [{"po_number": "PO-1", "status": "ERROR"}],
        [{"id": 1, "po_number": "PO-1", "attachment_name": "contract.pdf"}],
    )

    assert view["tree"][0]["label"] == "SOW not identified"
    assert view["tree"][0]["pos"][0]["label"] == "PO-1"
    assert {item["code"] for item in view["validation"]} == {"po_missing_sow", "po_missing_invoice"}


def test_groups_numberless_sows_by_sha256_and_shows_powerbi_invoices():
    digest = "a" * 64
    view = build_lab_relationships(
        [{"po_number": "PO-1"}, {"po_number": "PO-2"}],
        [
            {"po_number": "PO-1", "attachment_name": "Statement of Work.pdf", "sha256": digest},
            {"po_number": "PO-2", "attachment_name": "Statement of Work.pdf", "sha256": digest},
        ],
        {
            "pos": {
                "PO-1": {"commitment_value_eur": 500000},
                "PO-2": {"commitment_value_eur": 500000},
            },
            "invoices": {
                "PO-1": [{"invoice_number": "INV-1", "reporting_eur": 125000}],
                "PO-2": [{"invoice_number": "INV-2", "reporting_eur": 125000}],
            },
        },
    )

    contract = view["tree"][0]
    assert contract["key"] == f"SOW-HASH:{digest}"
    assert [item["label"] for item in contract["pos"]] == ["PO-1", "PO-2"]
    assert contract["commitment_total_eur"] == 1_000_000
    assert [item["label"] for item in contract["pos"][0]["invoices"]] == ["INV-1"]
    assert view["summary"]["invoices"] == 2


def test_does_not_use_a_filename_as_contract_key_without_sha256():
    view = build_lab_relationships(
        [{"po_number": "PO-1"}],
        [{"po_number": "PO-1", "attachment_name": "Statement of Work.pdf"}],
    )

    assert view["tree"][0]["key"] == "SOW:__unlinked__"


def test_api_reads_the_selected_local_session(tmp_path):
    db = SessionDB(str(tmp_path / "lab.db"))
    try:
        session_id = db.create_session("input.csv")
        db.add_po(PODownload(session_id, "PO-1", "1000", "SUCCESS"))
        db.record_po_attachment(session_id, "PO-1", "SOW-ABC.pdf", sha256="abc")
        result = AppAPI(db, str(tmp_path)).get_lab_relationships(session_id)
    finally:
        db.close()

    assert result["success"] is True
    assert result["session"]["id"] == session_id
    assert result["summary"]["sows"] == 1


def test_api_merges_powerbi_relationship_data_without_changing_local_keys(tmp_path):
    class EnrichedAPI(AppAPI):
        def _get_lab_relationship_powerbi(self, po_numbers):
            assert po_numbers == ["PO-1"]
            return {
                "pos": {"PO-1": {"commitment_value_eur": 500000}},
                "invoices": {"PO-1": [{"invoice_number": "INV-1", "reporting_eur": 100}]},
            }

    db = SessionDB(str(tmp_path / "lab-powerbi.db"))
    try:
        session_id = db.create_session("input.csv")
        db.add_po(PODownload(session_id, "PO-1", "1000", "SUCCESS"))
        db.record_po_attachment(session_id, "PO-1", "SOW.pdf", sha256="a" * 64)
        result = EnrichedAPI(db, str(tmp_path)).get_lab_relationships(session_id)
    finally:
        db.close()

    po = result["tree"][0]["pos"][0]
    assert po["commitment_value_eur"] == 500000
    assert po["invoices"][0]["invoice_number"] == "INV-1"
