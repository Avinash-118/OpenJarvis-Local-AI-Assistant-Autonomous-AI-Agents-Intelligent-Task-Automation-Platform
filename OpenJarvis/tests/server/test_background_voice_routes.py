"""Microphone coordination uses short leases and the local desktop boundary."""

import json
import threading
import time
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.server import desktop_routes as desktop


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENJARVIS_DESKTOP_CONTROL", "1")
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    monkeypatch.setattr(desktop, "_voice_root", lambda: tmp_path)
    app = FastAPI()
    app.include_router(desktop.router)
    return TestClient(app, base_url="http://127.0.0.1:8766")


HEADERS = {"X-Jarvis-Desktop": "1"}


def test_a_stale_browser_cannot_release_a_newer_session(client, tmp_path):
    url = "/v1/desktop/voice/browser"
    first, second = "first-browser-token", "second-browser-token"
    for token in (first, second):
        assert (
            client.post(
                url, json={"active": True, "token": token}, headers=HEADERS
            ).status_code
            == 200
        )
    client.post(url, json={"active": False, "token": first}, headers=HEADERS)
    lease = json.loads((tmp_path / "browser-voice.json").read_text())
    assert lease["token"] == second
    assert time.time() < lease["expires_at"] <= time.time() + 16
    client.post(url, json={"active": False, "token": second}, headers=HEADERS)
    assert not (tmp_path / "browser-voice.json").exists()


def test_pausing_cancels_background_actions_and_keeps_browser_actions(
    client, monkeypatch, tmp_path
):
    background, browser = threading.Event(), threading.Event()
    monkeypatch.setattr(
        desktop, "_jobs", {"background-one": background, "browser-task": browser}
    )
    response = client.post(
        "/v1/desktop/voice/pause", json={"paused": True}, headers=HEADERS
    )
    assert response.status_code == 200
    assert (tmp_path / "voice-paused").exists()
    assert background.is_set()
    assert not browser.is_set()
    client.post("/v1/desktop/voice/pause", json={"paused": False}, headers=HEADERS)
    assert not (tmp_path / "voice-paused").exists()


@pytest.mark.parametrize(
    "path,body",
    [
        ("/v1/desktop/voice/browser", {"active": True, "token": "unauthorized-token"}),
        ("/v1/desktop/voice/pause", {"paused": False}),
    ],
)
def test_cross_origin_pages_cannot_control_the_microphone(client, tmp_path, path, body):
    response = client.post(
        path, json=body, headers={**HEADERS, "Origin": "https://example.com"}
    )
    assert response.status_code == 403
    assert not list(tmp_path.iterdir())


def test_dead_process_status_is_not_reported_as_ready(client, monkeypatch, tmp_path):
    process = Mock()
    process.cmdline.return_value = ["python.exe", "some-other-app.py"]
    monkeypatch.setattr("psutil.Process", lambda _: process)
    (tmp_path / "background-voice.json").write_text(
        json.dumps({"pid": 123, "phase": "wake-word", "updated_at": time.time()})
    )
    status = client.get("/v1/desktop/voice", headers=HEADERS).json()
    assert status["running"] is False
    assert status["phase"] == "stopped"


def test_live_owned_process_reports_its_real_phase(client, monkeypatch, tmp_path):
    process = Mock()
    process.cmdline.return_value = [
        "pythonw.exe",
        str(tmp_path.parent / "jarvis_background.py"),
    ]
    monkeypatch.setattr("psutil.Process", lambda _: process)
    (tmp_path / "background-voice.json").write_text(
        json.dumps({"pid": 123, "phase": "wake-word", "updated_at": time.time()})
    )
    status = client.get("/v1/desktop/voice", headers=HEADERS).json()
    assert status["running"] is True
    assert status["wake_word"] == "Jarvis"
