"""Chat intentions, in-memory drafts, app identity, and literal unsent editing."""

import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openjarvis.server.chat_workflows import ChatWorkflows, WindowsChatUI, parse_request


@pytest.fixture(autouse=True)
def com(monkeypatch):
    com = SimpleNamespace(CoInitialize=Mock(), CoUninitialize=Mock())
    monkeypatch.setitem(sys.modules, "pythoncom", com)
    return com


def controller():
    ui = Mock()
    ui.search.return_value = "I filled the WhatsApp chat search."
    ui.fill.return_value = "Draft ready in the current WhatsApp chat."
    return ChatWorkflows(ui), ui, threading.Event()


@pytest.mark.parametrize(
    "text,app,name",
    [
        ("find chat with Alice on WhatsApp", "WhatsApp", "Alice"),
        ("find Alice Smith on linked in", "LinkedIn", "Alice Smith"),
        ("open the conversation with Alice on linkdien", "LinkedIn", "Alice"),
        ("in WhatsApp, find Alice", "WhatsApp", "Alice"),
        ("open WhatsApp and find Alice", "WhatsApp", "Alice"),
    ],
)
def test_chat_search_parses_explicit_app_and_person(text, app, name):
    request = parse_request(text)
    assert (request.kind, request.app, request.recipient) == ("find", app, name)


@pytest.mark.parametrize(
    "command",
    [
        "prepare a WhatsApp message for Alice saying Hello, Alice!",
        "draft a message to Alice on WhatsApp saying Hello, Alice!",
    ],
)
def test_draft_preserves_exact_text_and_does_not_fill_or_send(command):
    flow, ui, event = controller()
    result = flow.handle(command, event)
    assert flow.pending.text == "Hello, Alice!"
    assert "Hello, Alice!" in result["response"]
    ui.search.assert_called_once_with("WhatsApp", "Alice", event)
    ui.fill.assert_not_called()
    ui.send.assert_not_called()


def test_only_explicit_apply_command_puts_draft_in_current_chat():
    flow, ui, event = controller()
    flow.handle("prepare a WhatsApp message for Alice saying I'm on my way.", event)
    result = flow.handle("put the draft in this chat", event)
    ui.fill.assert_called_once_with("WhatsApp", "I'm on my way.", False, event)
    assert result["actions"] == ["message_box_draft"]


def test_missing_app_or_text_asks_before_any_ui_action():
    flow, ui, event = controller()
    assert (
        "Which app"
        in flow.handle("prepare a message for Alice saying Hi", event)["response"]
    )
    assert (
        "What should"
        in flow.handle("write a WhatsApp message to Alice", event)["response"]
    )
    ui.search.assert_not_called()
    ui.fill.assert_not_called()


def test_known_app_context_and_topic_writer_use_only_provided_data():
    flow, ui, event = controller()
    flow.remember_app("LinkedIn")
    writer = Mock(return_value="Could you tell me more about the role?")
    flow.handle(
        "write a message for Alice about asking for details of the role", event, writer
    )
    writer.assert_called_once_with(
        "LinkedIn", "Alice", "asking for details of the role"
    )
    assert flow.pending.text == "Could you tell me more about the role?"


def test_open_and_draft_compound_uses_named_app_context():
    flow, ui, event = controller()
    flow.handle("open WhatsApp and prepare a message for Alice saying Hello!", event)
    assert flow.pending.app == "WhatsApp"
    assert flow.pending.text == "Hello!"


def test_find_chat_without_app_uses_explicit_previous_app():
    flow, ui, event = controller()
    flow.remember_app("WhatsApp")
    flow.handle("find chat with Alice", event)
    ui.search.assert_called_once_with("WhatsApp", "Alice", event)


def test_failed_search_still_returns_reviewable_draft():
    flow, ui, event = controller()
    ui.search.side_effect = ValueError("Sign in normally in WhatsApp.")
    result = flow.handle("write a WhatsApp message to Alice saying Hello!", event)
    assert "Hello!" in result["response"] and "Sign in" in result["response"]
    assert flow.pending.text == "Hello!"


def test_expiry_cancellation_and_overlong_text_prevent_app_fill():
    flow, ui, event = controller()
    flow.handle("write a WhatsApp message to Alice saying Hello!", event)
    flow.pending.created -= 301
    assert (
        "Prepare a message first"
        in flow.handle("put the draft in this chat", event)["response"]
    )
    flow.handle("write a WhatsApp message to Alice saying Hello!", event)
    flow.handle("cancel draft", event)
    assert flow.pending is None
    event.set()
    assert flow.handle("put the draft in this chat", event)["response"] == "Stopped."
    ui.fill.assert_not_called()


def test_overlong_literal_is_not_silently_truncated():
    flow, ui, event = controller()
    result = flow.handle(
        "write a WhatsApp message to Alice saying " + "x" * 3001, event
    )
    assert "too long" in result["response"]
    assert flow.pending is None
    ui.search.assert_not_called()


def test_send_request_never_claims_message_was_sent():
    flow, ui, event = controller()
    result = flow.handle("send a WhatsApp message to Alice", event)
    assert "prepare a draft" in result["response"]
    ui.fill.assert_not_called()
    ui.send.assert_not_called()


class Field:
    def __init__(self, label, value="", focused=False):
        self.element_info = SimpleNamespace(
            name=label, automation_id="", control_type="Edit"
        )
        self.value = value
        self.window_text = lambda: label
        self.get_value = lambda: self.value
        self.has_keyboard_focus = lambda: focused
        self.set_edit_text = Mock(side_effect=self.set_value)
        self.type_keys = Mock()

    def set_value(self, text):
        self.value = text


def adapter(fields):
    ui = WindowsChatUI(Mock(), Mock())
    ui._focus_native = Mock()
    ui._context = Mock(return_value=(SimpleNamespace(handle=42), fields))
    return ui


def test_whatsapp_search_uses_named_search_field_not_browser_address():
    address, search = (
        Field("Address and search bar"),
        Field("Search or start a new chat"),
    )
    ui = adapter([address, search])
    ui.search("WhatsApp", "Alice", threading.Event())
    search.set_edit_text.assert_called_once_with("Alice")
    address.set_edit_text.assert_not_called()
    search.type_keys.assert_not_called()


def test_linkedin_search_submits_only_the_identified_search_field():
    search, composer = Field("Search messages"), Field("Write a message")
    ui = adapter([search, composer])
    ui.search("LinkedIn", "Alice", threading.Event())
    ui.open_url.assert_called_once_with("https://www.linkedin.com/messaging/")
    search.type_keys.assert_called_once_with("{ENTER}")
    composer.type_keys.assert_not_called()


def test_native_focus_selects_only_the_requested_app(monkeypatch):
    window = Mock()
    window.element_info.process_id = 42
    window.window_text.return_value = "WhatsApp"
    window.is_visible.return_value = True
    desktop = Mock()
    desktop.return_value.windows.return_value = [window]
    monkeypatch.setitem(sys.modules, "pywinauto", SimpleNamespace(Desktop=desktop))
    monkeypatch.setattr(
        "psutil.Process",
        Mock(return_value=SimpleNamespace(name=lambda: "WhatsApp.Root.exe")),
    )
    WindowsChatUI(Mock(), Mock())._focus_native("WhatsApp")
    window.set_focus.assert_called_once()


def test_message_box_gets_literal_text_with_no_send_key():
    field = Field("Type a message")
    ui = adapter([field])
    text = "Meet at 6?\nBudget 5% + {notes}!"
    assert "Draft ready" in ui.fill("WhatsApp", text, False, threading.Event())
    assert field.value == text
    field.type_keys.assert_not_called()


def test_existing_draft_is_preserved_until_explicit_replace():
    field = Field("Write a message", value="User's existing draft")
    ui = adapter([field])
    assert "already contains text" in ui.fill(
        "LinkedIn", "New text", False, threading.Event()
    )
    field.set_edit_text.assert_not_called()
    ui.fill("LinkedIn", "New text", True, threading.Event())
    assert field.value == "New text"


def test_ambiguous_composers_and_changed_window_prevent_typing():
    fields = [Field("Write a message"), Field("Type a message")]
    ui = adapter(fields)
    with pytest.raises(ValueError, match="one message box"):
        ui.fill("LinkedIn", "Hello", False, threading.Event())
    ui = adapter(fields[:1])
    ui._context.side_effect = [
        (SimpleNamespace(handle=42), fields[:1]),
        (SimpleNamespace(handle=43), fields[:1]),
    ]
    assert "Stopped" in ui.fill("LinkedIn", "Hello", False, threading.Event())
    fields[0].set_edit_text.assert_not_called()


@pytest.mark.parametrize(
    "url,inside_document,expected",
    [
        ("https://www.linkedin.com/messaging/", False, True),
        ("https://linkedin.com.attacker.example/", False, False),
        ("https://www.linkedin.com/messaging/", True, False),
        ("http://www.linkedin.com/", False, False),
    ],
)
def test_browser_identity_uses_real_address_toolbar_not_page_title(
    monkeypatch, url, inside_document, expected
):
    monkeypatch.setattr(
        "psutil.Process", Mock(return_value=SimpleNamespace(name=lambda: "chrome.exe"))
    )
    window = SimpleNamespace(element_info=SimpleNamespace(process_id=42))
    root = SimpleNamespace(element_info=SimpleNamespace(control_type="Window"))
    toolbar = SimpleNamespace(
        element_info=SimpleNamespace(control_type="ToolBar"), parent=lambda: root
    )
    document = SimpleNamespace(
        element_info=SimpleNamespace(control_type="Document"), parent=lambda: toolbar
    )
    address = Field("Address and search bar", url)
    address.parent = lambda: document if inside_document else toolbar
    assert WindowsChatUI._right_app(window, [address], "LinkedIn") is expected
