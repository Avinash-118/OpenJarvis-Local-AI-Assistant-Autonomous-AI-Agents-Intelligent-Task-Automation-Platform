"""Install pinned local voice assets and apply the conversational voice profile."""

from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

import tomlkit

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".openjarvis-runtime"
REVISION = "b4e358ffcb232591bf73a540e70f7de528e4174a"
ASSETS = {
    "en_US-lessac-medium.onnx": "5efe09e69902187827af646e1a6e9d269dee769f9877d17b16b1b46eeaaf019f",
    "en_US-lessac-medium.onnx.json": "efe19c417bed055f2d69908248c6ba650fa135bc868b0e6abb3da181dab690a0",
}


def verify(path: Path, expected: str) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest() == expected


def prepare_assets():
    folder = STATE / "neural-voice"
    folder.mkdir(parents=True, exist_ok=True)
    for name, expected in ASSETS.items():
        path = folder / name
        if path.exists():
            if not verify(path, expected):
                raise RuntimeError(
                    f"The installed voice asset failed verification: {name}"
                )
            continue
        print(f"Downloading offline voice: {name}", flush=True)
        url = f"https://huggingface.co/rhasspy/piper-voices/resolve/{REVISION}/en/en_US/lessac/medium/{name}"
        partial = path.with_suffix(path.suffix + ".download")
        with (
            urllib.request.urlopen(url, timeout=120) as source,
            partial.open("wb") as output,
        ):
            shutil.copyfileobj(source, output)
        if not verify(partial, expected):
            raise RuntimeError(
                f"The downloaded voice asset failed verification: {name}"
            )
        partial.replace(path)
    return folder


def apply_profile():
    path = STATE / "config.toml"
    template = ROOT / "config" / "config.local.example.toml"
    document = tomlkit.parse((path if path.exists() else template).read_text("utf-8"))
    backup = STATE / "config.before-natural-voice.toml"
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    speech = document.setdefault("speech", {})
    speech["tts_backend"] = "piper"
    speech["voice_id"] = "en_US-lessac-medium"
    speech["voice_speed"] = 0.97
    agent = document.setdefault("agent", {})
    prompt = (ROOT / "config" / "conversation-prompt.txt").read_text("utf-8").strip()
    agent["default_system_prompt"] = tomlkit.string(prompt, multiline=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(tomlkit.dumps(document), "utf-8")
    temporary.replace(path)
    (STATE / "natural-voice-enabled.json").write_text(
        json.dumps({"backend": "piper", "voice": "en_US-lessac-medium"}), "utf-8"
    )


def main():
    import os

    folder = prepare_assets()
    os.environ["OPENJARVIS_HOME"] = str(STATE)
    from openjarvis.speech.piper_tts import PiperTTSBackend

    backend = PiperTTSBackend(folder)
    result = backend.synthesize(
        "Hey, I'm here. Tell me what's on your mind. We can just chat for a bit.",
        speed=0.97,
    )
    preview = ROOT / ".tmp" / "natural-voice-preview.wav"
    preview.parent.mkdir(exist_ok=True)
    preview.write_bytes(result.audio)
    apply_profile()
    print("Natural offline voice and conversational reply style are ready.", flush=True)


if __name__ == "__main__":
    main()
