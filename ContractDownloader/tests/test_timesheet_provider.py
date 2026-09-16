import pandas as pd

from src.db.session_db import SessionDB
from src.timesheet_provider import TimesheetProvider


def _workbook(tmp_path):
    path = tmp_path / "timesheet.xlsx"
    frame = pd.DataFrame({
        "PWO": ["201", "201", "202", "203", ""],
        "Title": ["Accenture delivery", "Accenture delivery", "Deloitte support", "Fixed project", "Accenture"],
        "Billing Type": ["Central Billing", "Central Billing", "Local Billing", "Central Billing", "Central Billing"],
        "Resource Name": ["alice", "bob", "carol", "Fixed Price", "dave"],
        "Period Start Date": [43831, 43862, 43831, 43831, 43831],
        "Actual Bill Rate": ["USA - Level 7", "USA - Level 7", "UK - Level 5", "USA - Fixed Price", "USA - Level 4"],
        "Level": ["Level 7", "Level 7", "Level 5", "Fixed Price", "Level 4"],
        "Days": [2, 3, 4, 8, 1],
        "Fees": [100, 150, 400, 800, 50],
    })
    with pd.ExcelWriter(path) as writer:
        frame.to_excel(writer, sheet_name="Resource Timesheet", index=False)
    return path


def test_load_excludes_fixed_price_from_tm_and_keeps_exceptions(tmp_path):
    analysis = TimesheetProvider().load(str(_workbook(tmp_path)))

    assert analysis["summary"]["tm_pwo_count"] == 2
    assert analysis["summary"]["tm_days"] == 9.0
    assert analysis["summary"]["tm_fees"] == 650.0
    assert analysis["exception_summary"]["fixed_price_pwo_count"] == 1
    assert analysis["exception_summary"]["unmapped_pwo_rows"] == 1
    assert any(row["period_start"] == "2020-01-01" for row in analysis["rows"])


def test_filter_can_show_supplier_and_exception_scope(tmp_path):
    provider = TimesheetProvider()
    provider.load(str(_workbook(tmp_path)))
    full = provider.last_analysis

    supplier = provider.filter(full, "Accenture", "tm")
    exceptions = provider.filter(full, "", "exceptions")

    assert {row["pwo"] for row in supplier["rows"]} == {"201"}
    assert supplier["summary"]["tm_fees"] == 250.0
    assert {row["classification"] for row in exceptions["rows"]} == {"fixed_price"}


def test_timesheet_cache_round_trip(tmp_path):
    db = SessionDB(str(tmp_path / "sessions.db"))
    try:
        analysis = TimesheetProvider().load(str(_workbook(tmp_path)))
        cached = db.save_timesheet_analysis(analysis)
        restored = db.get_timesheet_analysis_cache()

        assert cached["updated_at"]
        assert restored["analysis"]["source"]["name"] == "timesheet.xlsx"
        assert restored["analysis"]["rows"] == analysis["rows"]
    finally:
        db.close()
