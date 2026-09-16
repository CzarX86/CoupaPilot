import asyncio


def test_frozen_cli_entrypoint_consumes_cancelled_error(monkeypatch, capsys):
    import src.main as main_module

    def cancel_run(coro):
        coro.close()
        raise asyncio.CancelledError

    monkeypatch.setattr(main_module.asyncio, "run", cancel_run)

    main_module._run_cli_pipeline()

    assert "Run interrupted safely" in capsys.readouterr().out


def test_macos_uses_the_bundle_icon_instead_of_a_runtime_favicon(tmp_path):
    from src.main import _runtime_webview_icon

    icon_file = tmp_path / "favicon.ico"
    icon_file.write_bytes(b"icon")

    assert _runtime_webview_icon(str(icon_file), platform="darwin") is None
    assert _runtime_webview_icon(str(icon_file), platform="win32") == str(icon_file)
    assert _runtime_webview_icon(str(tmp_path / "missing.ico"), platform="win32") is None
