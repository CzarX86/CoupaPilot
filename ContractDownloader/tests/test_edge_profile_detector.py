import json

from src.auth.browser import BrowserProfileManager, CorporateEdgeProfileDetector


def _profile(root, name, email):
    profile = root / name
    profile.mkdir(parents=True)
    (profile / "Preferences").write_text(
        json.dumps({"account_info": [{"email": email}]}),
        encoding="utf-8",
    )


def test_detector_finds_single_corporate_edge_profile(monkeypatch, tmp_path):
    _profile(tmp_path, "Profile 1", "employee@unilever.com")
    monkeypatch.setattr(CorporateEdgeProfileDetector, "_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(CorporateEdgeProfileDetector, "edge_is_running", staticmethod(lambda: False))

    result = CorporateEdgeProfileDetector().detect()

    assert result.state == "profile_detected"
    assert result.selected is not None
    assert result.selected.user_data_dir == tmp_path
    assert result.selected.profile_name == "Profile 1"
    assert result.available_profiles == ("Profile 1",)


def test_detector_matches_any_unilever_account_domain(monkeypatch, tmp_path):
    _profile(tmp_path, "Default", "employee@personal.example")
    _profile(tmp_path, "Profile 2", "employee@unilever.com.br")
    monkeypatch.setattr(CorporateEdgeProfileDetector, "_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(CorporateEdgeProfileDetector, "edge_is_running", staticmethod(lambda: False))

    result = CorporateEdgeProfileDetector().detect()

    assert result.state == "profile_detected"
    assert result.selected is not None
    assert result.selected.profile_name == "Profile 2"
    assert result.available_profiles == ("Default", "Profile 2")


def test_detector_requires_hil_for_multiple_profiles(monkeypatch, tmp_path):
    _profile(tmp_path, "Default", "one@unilever.com")
    _profile(tmp_path, "Profile 2", "two@unilever.com")
    monkeypatch.setattr(CorporateEdgeProfileDetector, "_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(CorporateEdgeProfileDetector, "edge_is_running", staticmethod(lambda: False))

    result = CorporateEdgeProfileDetector().detect()

    assert result.state == "action_required"
    assert result.selected is None
    assert len(result.candidates) == 2


def test_detector_prefers_named_unilever_work_profile(monkeypatch, tmp_path):
    _profile(tmp_path, "Default", "employee@unilever.com")
    _profile(tmp_path, "Profile 2", "employee@unilever.com")
    (tmp_path / "Local State").write_text(
        json.dumps(
            {
                "profile": {
                    "info_cache": {
                        "Default": {"name": "Personal"},
                        "Profile 2": {"name": "Unilever Work"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(CorporateEdgeProfileDetector, "_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(CorporateEdgeProfileDetector, "edge_is_running", staticmethod(lambda: False))

    result = CorporateEdgeProfileDetector().detect()

    assert result.state == "profile_detected"
    assert result.selected is not None
    assert result.selected.profile_name == "Profile 2"


def test_detector_reports_open_edge_without_attempting_to_close_it(monkeypatch, tmp_path):
    monkeypatch.setattr(CorporateEdgeProfileDetector, "_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(CorporateEdgeProfileDetector, "edge_is_running", staticmethod(lambda: True))

    result = CorporateEdgeProfileDetector().detect()

    assert result.state == "edge_must_be_closed"
    assert "Quit Microsoft Edge" in result.message


def test_macos_blocking_process_check_targets_only_the_main_edge_process(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return type("Result", (), {"returncode": 0, "stdout": ""})()

    monkeypatch.setattr("src.auth.browser.sys.platform", "darwin")
    monkeypatch.setattr("src.auth.browser.subprocess.run", fake_run)

    assert CorporateEdgeProfileDetector.edge_is_running() is True
    assert calls == [["pgrep", "-x", "Microsoft Edge"]]


def test_detector_ignores_a_stale_edge_profile_lock_without_deleting_it(monkeypatch, tmp_path):
    _profile(tmp_path, "Profile 1", "employee@unilever.com")
    (tmp_path / "SingletonLock").symlink_to("stale-edge-process")
    monkeypatch.setattr(CorporateEdgeProfileDetector, "_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(CorporateEdgeProfileDetector, "edge_is_running", staticmethod(lambda: False))

    result = CorporateEdgeProfileDetector().detect()

    assert result.state == "profile_detected"
    assert (tmp_path / "SingletonLock").is_symlink()


def test_detector_ignores_unilever_text_in_custom_links(monkeypatch, tmp_path):
    profile = tmp_path / "Default"
    profile.mkdir()
    (profile / "Preferences").write_text(
        json.dumps(
            {
                "account_info": [{"email": "employee@personal.example"}],
                "custom_links": {
                    "list": [
                        {"title": "Unilever portal", "url": "https://unilever.corp"},
                        {"title": "@unilever docs", "url": "https://example.com/unilever"},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(CorporateEdgeProfileDetector, "_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(CorporateEdgeProfileDetector, "edge_is_running", staticmethod(lambda: False))

    result = CorporateEdgeProfileDetector().detect()

    assert result.state == "action_required"
    assert result.selected is None
    assert result.candidates == ()


def test_detector_populates_display_name_and_safe_evidence(monkeypatch, tmp_path):
    profile = tmp_path / "Default"
    profile.mkdir()
    (profile / "Preferences").write_text(
        json.dumps({"account_info": [{"email": "employee@unilever.com"}]}),
        encoding="utf-8",
    )
    (tmp_path / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Default": {"name": "Perfil 1"}}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(CorporateEdgeProfileDetector, "_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(CorporateEdgeProfileDetector, "edge_is_running", staticmethod(lambda: False))

    result = CorporateEdgeProfileDetector().detect()

    assert result.state == "profile_detected"
    assert result.selected is not None
    assert result.selected.profile_name == "Default"
    assert result.selected.display_name == "Perfil 1"
    assert "Preferences.account_info[0].email" in result.selected.evidence
    assert not any("@unilever" in item for item in result.selected.evidence)


def test_detector_reports_profile_not_found_code(monkeypatch, tmp_path):
    (tmp_path / "Default").mkdir()
    monkeypatch.setattr(CorporateEdgeProfileDetector, "_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(CorporateEdgeProfileDetector, "edge_is_running", staticmethod(lambda: False))

    result = CorporateEdgeProfileDetector().detect()

    assert result.state == "action_required"
    assert result.code == "EDGE_PROFILE_NOT_FOUND"


def test_detector_reports_ambiguous_code_for_tie(monkeypatch, tmp_path):
    _profile(tmp_path, "Default", "one@unilever.com")
    _profile(tmp_path, "Profile 2", "two@unilever.com")
    monkeypatch.setattr(CorporateEdgeProfileDetector, "_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(CorporateEdgeProfileDetector, "edge_is_running", staticmethod(lambda: False))

    result = CorporateEdgeProfileDetector().detect()

    assert result.state == "action_required"
    assert result.code == "EDGE_PROFILE_AMBIGUOUS"


def test_detector_counts_integer_account_type_as_ranking_signal(monkeypatch, tmp_path):
    profile = tmp_path / "Default"
    profile.mkdir()
    (profile / "Preferences").write_text(
        json.dumps(
            {
                "account_info": [
                    {"email": "employee@unilever.com", "edge_account_type": 2}
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(CorporateEdgeProfileDetector, "_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(CorporateEdgeProfileDetector, "edge_is_running", staticmethod(lambda: False))

    result = CorporateEdgeProfileDetector().detect()

    assert result.selected is not None
    assert "Preferences.account_info.edge_account_type" in result.selected.evidence


def test_detector_blocks_a_live_edge_profile_lock(monkeypatch, tmp_path):
    _profile(tmp_path, "Profile 1", "employee@unilever.com")
    (tmp_path / "SingletonLock").symlink_to("Mac-4242")
    monkeypatch.setattr(CorporateEdgeProfileDetector, "_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(CorporateEdgeProfileDetector, "edge_is_running", staticmethod(lambda: False))
    monkeypatch.setattr(BrowserProfileManager, "_lock_owner_alive", classmethod(lambda cls, path: True))
    monkeypatch.setattr(
        BrowserProfileManager,
        "_process_info",
        staticmethod(lambda pid: (1, "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")),
    )

    result = CorporateEdgeProfileDetector().detect()

    assert result.state == "edge_must_be_closed"
    assert "⌘Q" in result.message
