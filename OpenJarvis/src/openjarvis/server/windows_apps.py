"""Discover and activate this user's registered Windows applications by name."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# This fixed read-only command never includes user speech or model output.
_CATALOG_SCRIPT = (
    "$ErrorActionPreference = 'Stop'; "
    "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
    "@(Get-StartApps | Select-Object Name, AppID) | ConvertTo-Json -Compress"
)
_cache: tuple[WindowsApp, ...] = ()
_cache_time: float | None = None
_cache_lock = threading.Lock()
_ALIASES = {
    "chrome": "googlechrome",
    "edge": "microsoftedge",
    "teams": "microsoftteams",
    "vscode": "visualstudiocode",
    "zoom": "zoomworkplace",
    "msword": "word",
    "microsoftword": "word",
    "msexcel": "excel",
    "microsoftexcel": "excel",
    "microsoftpowerpoint": "powerpoint",
    "microsoftaccess": "access",
    "windowsexplorer": "fileexplorer",
}


@dataclass(frozen=True)
class WindowsApp:
    name: str
    app_id: str


def name_key(name: str) -> str:
    """Ignore speech spacing and punctuation: 'Chat G P T' -> 'chatgpt'."""
    key = "".join(c for c in name.casefold() if c.isalnum())
    return _ALIASES.get(key, key)


def _read_apps() -> tuple[WindowsApp, ...]:
    powershell = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", _CATALOG_SCRIPT],
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        check=True,
        timeout=12,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    rows = json.loads(result.stdout)
    if isinstance(rows, dict):
        rows = [rows]
    if rows is None:
        return ()
    if not isinstance(rows, list):
        raise ValueError("Windows returned an invalid application list.")
    apps = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name, app_id = row.get("Name"), row.get("AppID")
        if not isinstance(name, str) or not isinstance(app_id, str):
            continue
        name, app_id = name.strip(), app_id.strip()
        if not name or not app_id or any(ord(c) < 32 for c in app_id):
            continue
        apps[app_id] = WindowsApp(name, app_id)
    return tuple(sorted(apps.values(), key=lambda app: app.name.casefold()))


def installed_apps(*, refresh: bool = False) -> tuple[WindowsApp, ...]:
    """Cache discovery so normal app commands don't start PowerShell each time."""
    global _cache, _cache_time
    if sys.platform != "win32":
        return ()
    with _cache_lock:
        now = time.monotonic()
        if not refresh and _cache_time is not None and now - _cache_time < 120:
            return _cache
        try:
            _cache = _read_apps()
        except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
            # Preserve an earlier usable list; the desktop route also tries .lnk files.
            logger.warning("Windows app discovery failed", exc_info=True)
        _cache_time = now
        return _cache


def find_app(name: str) -> WindowsApp | None:
    key = name_key(name)
    if not key:
        return None
    apps = installed_apps()
    exact = [app for app in apps if name_key(app.name) == key]
    # A short name may omit a vendor or a version suffix, but must be unambiguous.
    candidates = exact or [
        app
        for app in apps
        if name_key(app.name) in ("microsoft" + key, "windows" + key)
        or app.name.casefold().startswith(name.casefold().strip() + " ")
    ]
    if len(candidates) > 1:
        names = ", ".join(app.name for app in candidates[:5])
        raise ValueError(f"Which app do you mean: {names}? Say its full name.")
    return candidates[0] if candidates else None


def activate_app(app: WindowsApp) -> None:
    """Activate an ID obtained from Windows, without evaluating a command string."""
    # ShellExecute returns after launch; Shell.Application.InvokeVerb can block
    # this worker until a packaged application exits.
    os.startfile("shell:AppsFolder\\" + app.app_id)
