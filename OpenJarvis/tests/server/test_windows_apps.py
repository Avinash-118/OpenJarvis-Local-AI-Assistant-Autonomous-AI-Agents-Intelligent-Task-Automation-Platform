"""Exercise registered Windows app discovery without starting real applications."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openjarvis.server import windows_apps as apps


@pytest.mark.parametrize(
    "spoken,expected",
    [
        ("Whats App", "WhatsApp"),
        ("what's app", "WhatsApp"),
        ("CHAT G P T", "ChatGPT"),
        ("Chrome", "Google Chrome"),
        ("VS Code", "Visual Studio Code"),
        ("Microsoft Word", "Word"),
    ],
)
def test_spoken_alias_finds_real_registered_entry(monkeypatch, spoken, expected):
    app = apps.WindowsApp(expected, "known!App")
    monkeypatch.setattr(apps, "installed_apps", lambda: (app,))
    assert apps.find_app(spoken) is app


def test_ambiguous_names_request_full_name(monkeypatch):
    inventory = (
        apps.WindowsApp("Python 3.13", "a"),
        apps.WindowsApp("Python 3.14", "b"),
    )
    monkeypatch.setattr(apps, "installed_apps", lambda: inventory)
    with pytest.raises(ValueError, match="Which app.*Python 3.13.*Python 3.14"):
        apps.find_app("Python")


def test_exact_name_wins_and_unknown_is_not_guessed(monkeypatch):
    app = apps.WindowsApp("Word", "word")
    monkeypatch.setattr(
        apps, "installed_apps", lambda: (app, apps.WindowsApp("Word tools", "other"))
    )
    assert apps.find_app("Word") is app
    assert apps.find_app("anything else") is None
    assert apps.find_app("Word; Remove-Item C:\\") is None


def test_catalog_parses_utf8_and_ignores_malformed_entries(monkeypatch):
    rows = [
        {"Name": "WhatsApp", "AppID": "known!App"},
        {"Name": "Edición", "AppID": "other!App"},
        {"Name": "WhatsApp", "AppID": "known!App"},
        {"Name": "bad", "AppID": "bad\ncommand"},
        {"Name": None, "AppID": "bad"},
    ]
    process = Mock(return_value=SimpleNamespace(stdout=json.dumps(rows)))
    monkeypatch.setattr(apps.subprocess, "run", process)
    assert [app.name for app in apps._read_apps()] == ["Edición", "WhatsApp"]
    args, kwargs = process.call_args
    assert args[0][-1] == apps._CATALOG_SCRIPT
    assert "shell" not in kwargs
    assert kwargs["timeout"] == 12


def test_discovery_is_cached_and_can_be_refreshed(monkeypatch):
    monkeypatch.setattr(apps.sys, "platform", "win32")
    monkeypatch.setattr(apps, "_cache", ())
    monkeypatch.setattr(apps, "_cache_time", None)
    read = Mock(return_value=(apps.WindowsApp("WhatsApp", "registered!App"),))
    monkeypatch.setattr(apps, "_read_apps", read)
    assert apps.installed_apps() == apps.installed_apps()
    assert read.call_count == 1
    apps.installed_apps(refresh=True)
    assert read.call_count == 2


def test_failed_refresh_preserves_last_inventory(monkeypatch):
    monkeypatch.setattr(apps.sys, "platform", "win32")
    previous = (apps.WindowsApp("WhatsApp", "registered!App"),)
    monkeypatch.setattr(apps, "_cache", previous)
    monkeypatch.setattr(apps, "_cache_time", None)
    monkeypatch.setattr(
        apps, "_read_apps", Mock(side_effect=OSError("discovery unavailable"))
    )
    assert apps.installed_apps(refresh=True) == previous


@pytest.mark.parametrize("fails", [True, False])
def test_activation_uses_registered_id_and_propagates_os_failure(monkeypatch, fails):
    launch = Mock(side_effect=OSError("Windows launch failed") if fails else None)
    monkeypatch.setattr(apps.os, "startfile", launch, raising=False)
    app = apps.WindowsApp("WhatsApp", "registered!App")
    if fails:
        with pytest.raises(OSError, match="Windows launch failed"):
            apps.activate_app(app)
    else:
        apps.activate_app(app)
    launch.assert_called_once_with("shell:AppsFolder\\registered!App")
