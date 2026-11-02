"""Voice chat search and reviewable message drafts using the user's app session."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

APP = r"(?:whats\s*app|linked\s*in|linkdien)"


def app_name(value: str) -> str | None:
    key = re.sub(r"\W", "", value.casefold())
    return {"whatsapp": "WhatsApp", "linkedin": "LinkedIn", "linkdien": "LinkedIn"}.get(
        key
    )


@dataclass
class ChatRequest:
    kind: str
    app: str | None = None
    recipient: str = ""
    text: str = ""
    topic: str = ""


def parse_request(text: str) -> ChatRequest | None:
    command = text.strip()
    if re.match(
        r"^(?:send|post|publish)\b.*\b(?:message|whatsapp|linked\s*in)\b", command, re.I
    ):
        return ChatRequest("send")
    compound = re.fullmatch(
        rf"open\s+({APP})\s+(?:and|then)\s+(.+)", command, re.I | re.S
    )
    if compound:
        followup = parse_request(compound[2])
        if followup is None:
            followup = parse_request(f"in {compound[1]}, {compound[2]}")
        if followup and followup.kind in ("find", "draft", "text-question"):
            named_app = app_name(compound[1])
            if followup.app and followup.app != named_app:
                return ChatRequest("app-question")
            followup.app = named_app
            return followup
    if re.fullmatch(
        r"(?:put|place|insert|paste) (?:the |my )?draft "
        r"(?:in|into) (?:this|the current) chat[.!]?",
        command,
        re.I,
    ):
        return ChatRequest("apply")
    if re.fullmatch(r"replace (?:the )?current draft[.!]?", command, re.I):
        return ChatRequest("replace")
    if re.fullmatch(r"cancel (?:the |my )?(?:message|draft)[.!]?", command, re.I):
        return ChatRequest("cancel")
    found = re.fullmatch(
        r"(?:find|search(?: for)?|open)\s+"
        r"(?:(?:the |a )?(?:chat|conversation)\s+(?:with\s+)?)?"
        rf"(.+?)\s+(?:on|in)\s+({APP})[.!?]?",
        command,
        re.I,
    )
    if found:
        return ChatRequest("find", app_name(found[2]), found[1].strip())
    found = re.fullmatch(
        rf"(?:in|on)\s+({APP})[, ]+\s*(?:find|search(?: for)?)\s+"
        r"(?:chat with\s+)?(.+?)[.!?]?",
        command,
        re.I,
    )
    if found:
        return ChatRequest("find", app_name(found[1]), found[2].strip())
    found = re.fullmatch(
        r"(?:find|open)\s+(?:the )?(?:chat|conversation)\s+with\s+(.+?)[.!?]?",
        command,
        re.I,
    )
    if found:
        return ChatRequest("find", recipient=found[1].strip())
    draft = re.match(
        rf"^(?:prepare|draft|write)(?:\s+(?:an?|the))?\s+(?:({APP})\s+)?message\s+(?:to|for)\s+(.+)$",
        command,
        re.I | re.S,
    )
    if not draft:
        return None
    app, rest = app_name(draft[1]) if draft[1] else None, draft[2]
    pieces = re.split(
        r"\s+(saying|that says|with the text|about|asking)\s+",
        rest,
        maxsplit=1,
        flags=re.I,
    )
    person = pieces[0].strip()
    suffix = re.search(rf"\s+(?:on|in)\s+({APP})$", person, re.I)
    if suffix:
        named_app = app_name(suffix[1])
        if app and app != named_app:
            return ChatRequest("app-question")
        app, person = named_app, person[: suffix.start()].strip()
    if len(pieces) < 3:
        return ChatRequest("text-question", app, person)
    literal = pieces[1].casefold() in ("saying", "that says", "with the text")
    content = pieces[2].strip()
    if len(content) >= 2 and content[0] == content[-1] and content[0] in ('"', "'"):
        content = content[1:-1]
    return ChatRequest(
        "draft", app, person, content if literal else "", "" if literal else content
    )


@dataclass
class PendingDraft:
    app: str
    recipient: str
    text: str
    created: float


class ChatWorkflows:
    def __init__(self, ui):
        self.ui = ui
        self.last_app: str | None = None
        self.pending: PendingDraft | None = None

    def remember_app(self, name: str):
        if app := app_name(name):
            self.last_app = app

    def handle(self, text: str, cancelled, write=None) -> dict | None:
        request = parse_request(text)
        if request is None:
            return None
        if cancelled.is_set():
            return self.reply("Stopped.")
        if request.kind == "send":
            return self.reply(
                "I can prepare a draft for you to review. "
                "Complete the final send in the app."
            )
        if request.kind == "cancel":
            self.pending = None
            return self.reply("Okay, I discarded Jarvis's stored draft.")
        if request.kind in ("apply", "replace"):
            draft = self.pending
            if not draft or time.monotonic() - draft.created > 300:
                self.pending = None
                return self.reply(
                    "Prepare a message first. Drafts are kept for five minutes."
                )
            response = self.ui.fill(
                draft.app, draft.text, request.kind == "replace", cancelled
            )
            return self.reply(
                response,
                "message_box_draft" if response.startswith("Draft ready") else "",
            )
        app = request.app or self.last_app
        if not app or request.kind == "app-question":
            return self.reply("Which app should I use: WhatsApp or LinkedIn?")
        self.last_app = app
        if request.kind == "text-question":
            return self.reply(
                f"What should the {app} message to {request.recipient} say?"
            )
        if request.kind == "find":
            response = self.ui.search(app, request.recipient, cancelled)
            return self.reply(
                response, "chat_search" if response.startswith("I filled") else ""
            )
        message = request.text
        if request.topic and write:
            message = write(app, request.recipient, request.topic).strip()
        if cancelled.is_set():
            return self.reply("Stopped before preparing the draft.")
        if not message:
            return self.reply("What would you like the message to say?")
        if len(message) > 3000:
            return self.reply(
                "That message is too long for one draft. "
                "Split it into shorter messages."
            )
        self.pending = PendingDraft(app, request.recipient, message, time.monotonic())
        try:
            location = self.ui.search(app, request.recipient, cancelled)
        except (ValueError, RuntimeError, OSError) as exc:
            location = str(exc)
        if cancelled.is_set():
            self.pending = None
            return self.reply("Stopped. No message draft was placed in the app.")
        return self.reply(
            f"Draft for {request.recipient} on {app}: {message}\n{location} "
            "Select the intended conversation, then say 'put the draft in this chat'.",
            "message_draft",
        )

    @staticmethod
    def reply(text: str, action: str = "") -> dict:
        return {
            "handled": True,
            "response": text,
            "actions": [action] if action else [],
        }


class WindowsChatUI:
    """Named search/composer controls; no generated scripts or message submission."""

    NATIVE = {
        "WhatsApp": {"whatsapp.exe", "whatsapp.root.exe", "whatsapp.beta.exe"},
        "LinkedIn": {"linkedin.exe", "linkedin.root.exe"},
    }

    def __init__(self, open_app, open_url):
        self.open_app, self.open_url = open_app, open_url

    def _focus_native(self, app):
        import psutil
        from pywinauto import Desktop

        candidates = []
        for window in Desktop(backend="uia").windows():
            try:
                process = (
                    psutil.Process(window.element_info.process_id).name().casefold()
                )
                if process in self.NATIVE[app] and window.is_visible():
                    candidates.append(window)
            except Exception:
                continue
        exact = [
            w
            for w in candidates
            if w.window_text().casefold().strip() == app.casefold()
        ]
        targets = exact or candidates
        if len(targets) == 1:
            targets[0].set_focus()

    @staticmethod
    def _capture():
        import win32gui
        from pywinauto import Desktop

        window = (
            Desktop(backend="uia")
            .window(handle=win32gui.GetForegroundWindow())
            .wrapper_object()
        )
        fields = []
        for control in window.descendants(control_type="Edit"):
            try:
                if (
                    control.is_visible()
                    and control.is_enabled()
                    and not control.element_info.element.CurrentIsPassword
                ):
                    fields.append(control)
            except Exception:
                continue
        return window, fields

    @staticmethod
    def _label(control):
        info = control.element_info
        return " ".join(
            (control.window_text(), str(info.name or ""), str(info.automation_id or ""))
        )

    @staticmethod
    def _right_app(window, fields, app):
        import psutil

        process = psutil.Process(window.element_info.process_id).name().casefold()
        if process in WindowsChatUI.NATIVE[app]:
            return True
        # A browser title can be set by any website. Inspect only the browser's
        # address toolbar, outside the webpage document, before entering text.
        allowed = {
            "WhatsApp": {"web.whatsapp.com"},
            "LinkedIn": {"linkedin.com", "www.linkedin.com"},
        }[app]
        for control in fields:
            if not re.search(
                r"address|location|url", WindowsChatUI._label(control), re.I
            ):
                continue
            parent, toolbar, document = control, False, False
            for _ in range(12):
                parent = parent.parent()
                if parent is None:
                    break
                role = parent.element_info.control_type
                toolbar |= role == "ToolBar"
                document |= role == "Document"
                if role == "Window":
                    break
            if toolbar and not document:
                value = control.get_value().strip()
                url = urlsplit(value if "://" in value else "https://" + value)
                if url.scheme == "https" and url.hostname in allowed:
                    return True
        return False

    def _context(self, app):
        try:
            window, fields = self._capture()
            valid = self._right_app(window, fields, app)
        except Exception as exc:
            raise ValueError(
                f"I couldn't inspect {app}. Open its chat and repeat the command."
            ) from exc
        if not valid:
            raise ValueError(
                f"Bring your signed-in {app} chat to the foreground, "
                "then repeat the command."
            )
        return window, fields

    def search(self, app, person, cancelled):
        import pythoncom

        pythoncom.CoInitialize()
        try:
            if app == "LinkedIn":
                self.open_url("https://www.linkedin.com/messaging/")
            else:
                self.open_app(app, cancelled)
                self._focus_native(app)
            deadline = time.monotonic() + 10
            last_error = f"Open {app} and sign in, then repeat the chat search."
            while not cancelled.is_set() and time.monotonic() < deadline:
                try:
                    window, fields = self._context(app)
                    search = [
                        c
                        for c in fields
                        if re.search(r"search", self._label(c), re.I)
                        and not re.search(r"address|location|url", self._label(c), re.I)
                    ]
                    scoped = [
                        c
                        for c in search
                        if re.search(
                            r"search.*(?:message|conversation)|start.*chat|chat.*search",
                            self._label(c),
                            re.I,
                        )
                    ]
                    if len(scoped) == 1:
                        search = scoped
                    if len(search) == 1:
                        current, _ = self._context(app)
                        if current.handle != window.handle:
                            raise ValueError(
                                "The active window changed. "
                                "Repeat the search in the intended app."
                            )
                        search[0].set_edit_text(person)
                        if app == "LinkedIn" and not cancelled.is_set():
                            current, _ = self._context(app)
                            if current.handle != window.handle:
                                raise ValueError(
                                    "The active window changed. Repeat the search."
                                )
                            # Submit only a positively identified search field,
                            # never the message composer or a global Enter key.
                            search[0].type_keys("{ENTER}")
                        return (
                            f"I filled the {app} chat search with {person}. "
                            "Select the matching conversation."
                        )
                    last_error = (
                        f"I couldn't identify one {app} chat-search field. "
                        "Open its messaging view and try again."
                    )
                except (ValueError, RuntimeError, OSError) as exc:
                    last_error = str(exc)
                cancelled.wait(0.3)
            if cancelled.is_set():
                return "Stopped before searching."
            raise ValueError(last_error)
        finally:
            pythoncom.CoUninitialize()

    def fill(self, app, text, replace, cancelled):
        import pythoncom

        pythoncom.CoInitialize()
        try:
            window, fields = self._context(app)
            composers = [
                c
                for c in fields
                if re.search(r"message|reply|composer", self._label(c), re.I)
                and not re.search(r"search|filter|address|url", self._label(c), re.I)
            ]
            focused = [c for c in composers if c.has_keyboard_focus()]
            if len(focused) == 1:
                composers = focused
            if len(composers) != 1:
                raise ValueError(
                    f"Open the intended {app} conversation and leave one "
                    "message box active, then repeat the command."
                )
            field = composers[0]
            existing = field.get_value()
            if existing.strip() and existing != text and not replace:
                return (
                    "That message box already contains text. "
                    "Say 'replace current draft' to replace it."
                )
            current, _ = self._context(app)
            if current.handle != window.handle or cancelled.is_set():
                return (
                    "Stopped because the active window changed "
                    "or the task was cancelled."
                )
            field.set_edit_text(text)
            if field.get_value().replace("\r\n", "\n") != text.replace("\r\n", "\n"):
                raise ValueError(
                    "I couldn't verify the filled draft. "
                    "Check the message box before trying again."
                )
            return (
                f"Draft ready in the current {app} chat. "
                "Review the recipient and message before sending."
            )
        finally:
            pythoncom.CoUninitialize()
