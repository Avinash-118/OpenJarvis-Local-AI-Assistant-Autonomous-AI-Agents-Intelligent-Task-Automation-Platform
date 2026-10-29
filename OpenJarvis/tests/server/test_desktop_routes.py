"""Exercise real routing boundaries while mocking OS effects and model output."""

import threading
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.server import desktop_routes as desktop


def command(text, messages=None):
    return desktop.Command(id="test", text=text, messages=messages or [])


def run(text, messages=None):
    return desktop.execute(command(text, messages), Mock(), "local", threading.Event())


@pytest.mark.parametrize(
    "text,url",
    [
        ("Can you open my Gmail?", "https://mail.google.com/"),
        ("Hey Jarvis, open YouTube", "https://www.youtube.com/"),
        ("open example.com", "https://example.com"),
        ("search relaxing music on youtube", "search_query=relaxing+music"),
    ],
)
def test_opens_requested_browser_target(monkeypatch, text, url):
    opened = Mock()
    monkeypatch.setattr(desktop, "_open_url", opened)
    result = run(text)
    assert result["handled"] is True
    assert url in opened.call_args.args[0]


def test_chat_has_no_desktop_effect(monkeypatch):
    opened = Mock()
    monkeypatch.setattr(desktop, "_open_url", opened)
    assert run("Explain how rainbows form")["handled"] is False
    opened.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://user:secret@example.com",
        "ms-settings:privacy",
    ],
)
def test_navigation_cannot_launch_an_arbitrary_uri(url):
    with pytest.raises(ValueError):
        desktop._open_url(url)


def test_draft_strips_invented_recipient_and_encodes_text(monkeypatch):
    opened = Mock()
    monkeypatch.setattr(desktop, "_open_url", opened)
    monkeypatch.setattr(
        desktop,
        "_json_reply",
        lambda *args: {
            "ready": True,
            "to": "invented@example.com",
            "subject": "Question & answer",
            "body": "Hello!\nA+B & C?",
        },
    )
    result = run("Write an email asking about the meeting")
    assert result["handled"] is True
    url = opened.call_args.args[0]
    assert "invented" not in url
    assert "Question+%26+answer" in url
    assert "Hello%21%0AA%2BB+%26+C%3F" in url


def test_draft_question_does_not_open_empty_compose(monkeypatch):
    opened = Mock()
    monkeypatch.setattr(desktop, "_open_url", opened)
    monkeypatch.setattr(
        desktop,
        "_json_reply",
        lambda *args: {"ready": False, "question": "What should the email say?"},
    )
    assert run("write an email")["response"].startswith("What should the email say")
    opened.assert_not_called()


def test_cancelled_task_never_opens_site(monkeypatch):
    opened = Mock()
    monkeypatch.setattr(desktop, "_open_url", opened)
    cancelled = threading.Event()
    cancelled.set()
    assert (
        desktop.execute(command("open gmail"), Mock(), "local", cancelled)["response"]
        == "Stopped."
    )
    opened.assert_not_called()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPENJARVIS_DESKTOP_CONTROL", "1")
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    app = FastAPI()
    app.state.engine = Mock()
    app.state.model = "local"
    app.include_router(desktop.router)
    return TestClient(app, base_url="http://127.0.0.1:8766")


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Jarvis-Desktop": "1", "Origin": "https://attacker.example"},
        {"X-Jarvis-Desktop": "1", "Host": "attacker.example"},
        {"X-Jarvis-Desktop": "1", "Sec-Fetch-Site": "cross-site"},
    ],
)
def test_external_site_cannot_drive_computer(client, monkeypatch, headers):
    executor = Mock()
    monkeypatch.setattr(desktop, "execute", executor)
    response = client.post(
        "/v1/desktop/command",
        json={"id": "test", "text": "open gmail"},
        headers=headers,
    )
    assert response.status_code == 403
    executor.assert_not_called()


def test_local_chat_can_execute_and_returns_observed_result(client, monkeypatch):
    monkeypatch.setattr(
        desktop, "execute", lambda *args: {"handled": True, "response": "Opened."}
    )
    response = client.post(
        "/v1/desktop/command",
        json={"id": "test", "text": "open gmail"},
        headers={"X-Jarvis-Desktop": "1", "Origin": "http://127.0.0.1:8766"},
    )
    assert response.status_code == 200
    assert response.json()["response"] == "Opened."


def test_launcher_opt_in_is_required(client, monkeypatch):
    monkeypatch.delenv("OPENJARVIS_DESKTOP_CONTROL")
    assert (
        client.get("/v1/desktop/health", headers={"X-Jarvis-Desktop": "1"}).status_code
        == 404
    )


def test_speech_returns_local_wav_without_cache(client, monkeypatch):
    monkeypatch.setattr(desktop, "windows_speech", lambda text: b"RIFFtest-WAVE")
    response = client.post(
        "/v1/desktop/speak", json={"text": "Hello."}, headers={"X-Jarvis-Desktop": "1"}
    )
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "no-store"
    assert response.content == b"RIFFtest-WAVE"


def test_valid_draft_is_not_discarded_for_inconsistent_model_ready_flag(monkeypatch):
    opened = Mock()
    monkeypatch.setattr(desktop, "_open_url", opened)
    monkeypatch.setattr(
        desktop,
        "_json_reply",
        lambda *args: {
            "ready": False,
            "to": "",
            "subject": "",
            "body": "Join me for lunch tomorrow?",
        },
    )
    result = run("Write an email to friend@example.com inviting them to lunch")
    assert result["response"].startswith("I opened a Gmail draft")
    assert "friend%40example.com" in opened.call_args.args[0]


def test_bare_email_request_asks_before_using_model(monkeypatch):
    model = Mock()
    monkeypatch.setattr(desktop, "_json_reply", model)
    assert (
        "What should the email say"
        in run("Write an email to friend@example.com")["response"]
    )
    model.assert_not_called()


def test_new_open_command_takes_priority_over_unfinished_email(monkeypatch):
    opened = Mock()
    draft = Mock()
    monkeypatch.setattr(desktop, "_open_url", opened)
    monkeypatch.setattr(desktop, "_draft_email", draft)
    result = run(
        "Open YouTube",
        [
            {"role": "user", "content": "Write an email"},
            {
                "role": "assistant",
                "content": "What should the email say, and who is it for?",
            },
            {"role": "user", "content": "Open YouTube"},
        ],
    )
    assert result["response"] == "I opened YouTube."
    draft.assert_not_called()
    opened.assert_called_once()
