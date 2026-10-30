"""Local Windows wake-word listener and sign-in supervisor for Jarvis."""

from __future__ import annotations

import argparse
import ctypes
import io
import json
import logging
import math
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import wave
import webbrowser
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".openjarvis-runtime"
PYTHON = ROOT / "OpenJarvis" / ".venv" / "Scripts" / "python.exe"
MODEL = STATE / "wake-word" / "vosk-model-small-en-us-0.15"
URL = "http://127.0.0.1:8766"
RATE = 16000
BLOCK = 1280  # 80 ms of mono signed 16-bit PCM.
PAUSED = STATE / "voice-paused"
STOP = STATE / "voice-stop"
LEASE = STATE / "browser-voice.json"
STATUS = STATE / "background-voice.json"
WAKE = re.compile(
    r"^(?:(?:hey|okay|ok)\s+)?(?:jarvis|jervis)\b[,.:!?\s]*", re.IGNORECASE
)
SLEEP = re.compile(
    r"^(?:please\s+)?(?:stop listening|go to sleep|stop voice(?: mode)?|that is all|that\x27s all)[.!]?$",
    re.IGNORECASE,
)
log = logging.getLogger("jarvis.background")


def unlocked() -> bool:
    """Listen only on the user's interactive desktop, never the lock screen."""
    if sys.platform != "win32":
        return False
    from ctypes import wintypes

    user = ctypes.WinDLL("user32", use_last_error=True)
    user.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user.OpenInputDesktop.restype = wintypes.HANDLE
    user.GetUserObjectInformationW.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    desk = user.OpenInputDesktop(0, False, 1)  # DESKTOP_READOBJECTS
    if not desk:
        return False
    try:
        name = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD()
        return (
            bool(
                user.GetUserObjectInformationW(
                    desk, 2, name, ctypes.sizeof(name), ctypes.byref(needed)
                )
            )
            and name.value.casefold() == "default"
        )
    finally:
        user.CloseDesktop(desk)


def browser_active(now: float | None = None) -> bool:
    try:
        return float(json.loads(LEASE.read_text("utf-8"))["expires_at"]) > (
            time.time() if now is None else now
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def wav_bytes(frames: list[bytes]) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(b"".join(frames))
    return buffer.getvalue()


def wake_seed(
    frames: list[bytes], audio_seconds: float, result: dict, *, final: bool
) -> tuple[list[bytes], float]:
    """Trim pre-roll to the detected word, retaining a small phoneme margin."""
    import numpy as np

    count = min(20, len(frames))
    words = result.get("result" if final else "partial_result", [])
    for word in reversed(words):
        if word.get("word") != "jarvis":
            continue
        try:
            seconds = audio_seconds - float(word["start"]) + 0.12
            if math.isfinite(seconds) and seconds >= 0:
                count = min(len(frames), max(3, math.ceil(seconds * RATE / BLOCK)))
        except (KeyError, ValueError, TypeError):
            pass
        break
    background = frames[:-count] if count else frames
    rms = []
    for frame in background:
        samples = np.frombuffer(frame, dtype="<i2").astype(np.float32) / 32768
        rms.append(float(np.sqrt(np.mean(samples * samples))))
    noise = max(0.001, float(np.percentile(rms, 20))) if rms else 0.001
    return frames[-count:], noise


class TurnBoundary:
    """End an utterance after a pause, with bounded startup and recording time."""

    def __init__(self, noise: float = 0.001):
        self.elapsed = 0.0
        self.voiced = 0.0
        self.silence = 0.0
        self.noise = max(0.001, noise)
        self.started = False

    def update(self, rms: float, seconds: float = BLOCK / RATE) -> bool:
        self.elapsed += seconds
        threshold = max(0.004, min(self.noise * 2.5, 0.25))
        if rms > threshold:
            self.voiced += seconds
            self.silence = 0
            self.started = self.voiced >= 0.24
        else:
            self.silence += seconds
            if not self.started:
                self.noise = self.noise * 0.95 + min(rms, 0.25) * 0.05
                if self.silence > 0.35:
                    self.voiced = 0
        return (
            self.elapsed >= 30
            or (self.started and self.silence >= 1.2)
            or (not self.started and self.elapsed >= 6)
        )


class Dialogue:
    """Require a wake phrase before opening a short conversation window."""

    def __init__(self):
        self.until = 0.0

    def accept(self, text: str, now: float, *, woke: bool = False) -> str | None:
        text = text.strip()
        match = WAKE.match(text)
        if match:
            self.until = now + 30
            return text[match.end() :].strip()
        if woke or now >= self.until:
            # A wake detector false positive must not execute background speech.
            return None
        return text


class LocalAgent:
    def __init__(self):
        self.http = httpx.Client(
            base_url=URL,
            trust_env=False,
            timeout=httpx.Timeout(150, connect=3),
            headers={"X-Jarvis-Desktop": "1"},
        )
        self.history: list[dict[str, str]] = []
        self.job: str | None = None

    def healthy(self) -> bool:
        try:
            response = self.http.get("/health", timeout=2)
            return response.is_success and response.json().get("status") == "ok"
        except (httpx.HTTPError, OSError, ValueError):
            return False

    def cancel(self):
        job = self.job
        if job:
            try:
                self.http.post("/v1/desktop/cancel", json={"id": job}, timeout=2)
            except (httpx.HTTPError, OSError):
                log.debug("Desktop cancellation failed", exc_info=True)

    def transcribe(self, audio: bytes) -> str:
        response = self.http.post(
            "/v1/speech/transcribe",
            files={"file": ("voice.wav", audio, "audio/wav")},
            data={"language": "en"},
        )
        response.raise_for_status()
        return response.json().get("text", "").strip()

    def answer(self, text: str) -> str:
        history = self.history[-10:]
        self.job = "background-" + uuid.uuid4().hex
        try:
            response = self.http.post(
                "/v1/desktop/command",
                json={"id": self.job, "text": text, "messages": history},
            )
            response.raise_for_status()
            result = response.json()
            if result.get("handled"):
                reply = result.get("response") or "Done."
            else:
                models = self.http.get("/v1/models")
                models.raise_for_status()
                model = models.json()["data"][0]["id"]
                response = self.http.post(
                    "/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": history + [{"role": "user", "content": text}],
                        "max_tokens": 256,
                        "stream": False,
                    },
                )
                response.raise_for_status()
                reply = (
                    response.json()["choices"][0]["message"]["content"]
                    or "I did not get an answer. Please try again."
                )
            self.history = (
                history
                + [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": reply},
                ]
            )[-10:]
            return reply
        finally:
            self.job = None

    def speech(self, text: str) -> bytes:
        # Keep URLs and formatting out of speech, while retaining readable text.
        text = re.sub(r"```.*?```", "That answer includes code.", text, flags=re.DOTALL)
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"[*_#`]", "", text).strip()[:2500]
        response = self.http.post("/v1/speech/synthesize", json={"text": text})
        response.raise_for_status()
        return response.content


class BackgroundVoice:
    def __init__(self):
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.agent = LocalAgent()
        self.dialogue = Dialogue()
        self.phase = "starting"
        self.error: str | None = None
        self.icon = None
        self.lock = threading.Lock()
        self.noise_floor = 0.001

    def set_phase(self, phase: str, error: str | None = None):
        with self.lock:
            self.phase, self.error = phase, error
        if self.icon:
            labels = {
                "wake-word": "Say Jarvis",
                "listening": "Listening to your request",
                "working": "Thinking",
                "speaking": "Speaking",
                "paused": "Microphone paused",
                "locked": "Waiting for you to unlock Windows",
                "browser-voice": "Voice is active in the browser",
                "error": "Needs attention",
                "starting": "Starting",
            }
            self.icon.title = "Jarvis — " + labels.get(phase, phase)

    def allowed(self) -> bool:
        return (
            not self.stop.is_set()
            and not STOP.exists()
            and not PAUSED.exists()
            and not browser_active()
            and unlocked()
        )

    def pause_reason(self) -> str:
        if PAUSED.exists():
            return "paused"
        if browser_active():
            return "browser-voice"
        return "locked"

    def heartbeat(self):
        while not self.stop.is_set():
            if STOP.exists():
                self.quit()
                break
            with self.lock:
                state = {
                    "pid": os.getpid(),
                    "phase": self.phase,
                    "error": self.error,
                    "wake_word": "Jarvis",
                    "updated_at": time.time(),
                    "paused": PAUSED.exists(),
                }
            try:
                temporary = STATUS.with_suffix(".tmp")
                temporary.write_text(json.dumps(state), "utf-8")
                temporary.replace(STATUS)
            except OSError:
                log.exception("Could not update background voice status")
            self.stop.wait(2)

    def supervise_backend(self):
        while not self.stop.is_set():
            if self.agent.healthy():
                self.ready.set()
                self.stop.wait(15)
                continue
            self.ready.clear()
            self.set_phase("starting")
            try:
                options = {
                    "creationflags": subprocess.CREATE_NO_WINDOW
                    | subprocess.CREATE_NEW_PROCESS_GROUP
                }
                with (STATE / "autostart-server.log").open(
                    "a", encoding="utf-8"
                ) as output:
                    process = subprocess.Popen(
                        [
                            str(PYTHON),
                            str(ROOT / "OpenJarvis-Local.py"),
                            "--no-browser",
                        ],
                        cwd=ROOT,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        **options,
                    )
                    process.wait(timeout=240)
                if process.returncode:
                    raise RuntimeError(
                        "Jarvis startup failed; see autostart-server.log"
                    )
            except Exception as exc:
                log.exception("Backend startup failed")
                self.set_phase("error", str(exc))
            self.stop.wait(5)

    def speak(self, text: str):
        import sounddevice as sd

        if not self.allowed():
            return
        self.set_phase("speaking")
        audio = self.agent.speech(text)
        if not self.allowed():
            return
        with wave.open(io.BytesIO(audio), "rb") as source:
            if source.getsampwidth() != 2:
                raise ValueError("The configured voice must return 16-bit WAV audio")
            with sd.RawOutputStream(
                samplerate=source.getframerate(),
                channels=source.getnchannels(),
                dtype="int16",
            ) as output:
                while self.allowed():
                    chunk = source.readframes(4096)
                    if not chunk:
                        break
                    output.write(chunk)
        self.stop.wait(0.35)  # Let speaker echo fade before reopening the mic.

    def record(self, stream, seed: list[bytes] | None = None) -> bytes | None:
        import numpy as np

        self.set_phase("listening")
        frames = list(seed or [])
        boundary = TurnBoundary(self.noise_floor)
        for frame in frames:
            samples = np.frombuffer(frame, dtype="<i2").astype(np.float32) / 32768
            boundary.update(float(np.sqrt(np.mean(samples * samples))))
        # The seed can include pre-wake silence; never end before new audio.
        boundary.silence = 0
        if seed:
            boundary.started = True  # Vosk already detected speech, even if quiet.
        while self.allowed():
            data, _overflow = stream.read(BLOCK)
            frame = bytes(data)
            frames.append(frame)
            samples = np.frombuffer(frame, dtype="<i2").astype(np.float32) / 32768
            if boundary.update(float(np.sqrt(np.mean(samples * samples)))):
                return wav_bytes(frames) if boundary.started else None
        return None

    def capture(self, detector, *, wake: bool) -> bytes | None:
        import sounddevice as sd

        with sd.RawInputStream(
            samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK
        ) as stream:
            if not wake:
                return self.record(stream)
            self.set_phase("wake-word")
            detector.Reset()
            pre_roll: deque[bytes] = deque(maxlen=50)
            seen = 0
            while self.allowed():
                frame = bytes(stream.read(BLOCK)[0])
                seen += 1
                pre_roll.append(frame)
                final = detector.AcceptWaveform(frame)
                result = json.loads(
                    detector.Result() if final else detector.PartialResult()
                )
                text = result.get("text" if final else "partial", "")
                if re.search(r"\bjarvis\b", text):
                    seed, self.noise_floor = wake_seed(
                        list(pre_roll), seen * BLOCK / RATE, result, final=bool(final)
                    )
                    return self.record(stream, seed)
        return None

    def listen(self):
        from vosk import KaldiRecognizer, Model, SetLogLevel

        try:
            SetLogLevel(-1)
            model = Model(str(MODEL))
            if model.vosk_model_find_word("jarvis") < 0:
                raise RuntimeError("The wake-word model does not contain Jarvis")
            detector = KaldiRecognizer(
                model, RATE, json.dumps(["jarvis", "hey jarvis", "[unk]"])
            )
            detector.SetWords(True)
            detector.SetPartialWords(True)
        except Exception as exc:
            log.exception("Wake-word model initialization failed")
            self.set_phase("error", str(exc))
            return
        greeted = False
        while not self.stop.is_set():
            if not self.allowed():
                self.dialogue.until = 0
                self.set_phase(self.pause_reason())
                self.stop.wait(0.5)
                continue
            if not self.ready.wait(0.5):
                continue
            try:
                if not greeted:
                    self.speak("Jarvis is ready. Say Jarvis when you need me.")
                    greeted = True
                woke = time.monotonic() >= self.dialogue.until
                audio = self.capture(detector, wake=woke)
                if audio is None or not self.allowed():
                    continue
                self.set_phase("transcribing")
                text = self.agent.transcribe(audio)
                if not self.allowed():
                    continue
                command = self.dialogue.accept(text, time.monotonic(), woke=woke)
                if command is None:
                    continue
                if not command:
                    reply = "Yes? I'm listening."
                elif SLEEP.fullmatch(command):
                    self.dialogue.until = 0
                    self.agent.history.clear()
                    self.speak("Okay. Say Jarvis when you need me.")
                    continue
                else:
                    self.set_phase("working")
                    reply = self.agent.answer(command)
                if self.allowed():
                    self.speak(reply)
                    self.dialogue.until = time.monotonic() + 30
            except Exception as exc:
                log.exception("Background voice turn failed")
                self.set_phase("error", str(exc))
                self.dialogue.until = 0
                self.stop.wait(5)

    def toggle_pause(self, *_):
        if PAUSED.exists():
            PAUSED.unlink()
        else:
            PAUSED.touch()
            self.set_phase("paused")
            threading.Thread(target=self.agent.cancel, daemon=True).start()
        if self.icon:
            self.icon.update_menu()

    def quit(self, *_):
        if self.stop.is_set():
            return
        self.stop.set()
        self.agent.cancel()
        if self.icon:
            self.icon.stop()

    def run(self):
        import pystray
        from PIL import Image, ImageDraw

        image = Image.new("RGBA", (64, 64), "#07151b")
        draw = ImageDraw.Draw(image)
        draw.ellipse((12, 12, 52, 52), outline="#20d5ee", width=5)
        draw.rectangle((29, 22, 35, 39), fill="#20d5ee")
        self.icon = pystray.Icon(
            "Jarvis AI Agent",
            image,
            "Jarvis — Starting",
            menu=pystray.Menu(
                pystray.MenuItem(
                    "Open Jarvis", lambda *_: webbrowser.open(URL), default=True
                ),
                pystray.MenuItem(
                    lambda _: (
                        "Resume microphone" if PAUSED.exists() else "Pause microphone"
                    ),
                    self.toggle_pause,
                ),
                pystray.MenuItem("Quit background voice", self.quit),
            ),
        )
        for target in (self.heartbeat, self.supervise_backend, self.listen):
            threading.Thread(target=target, daemon=True).start()
        try:
            self.icon.run()
        finally:
            self.quit()
            STATUS.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Jarvis wake-word listener and Windows sign-in supervisor"
    )
    parser.add_argument("--stop", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print background status without using the microphone",
    )
    args = parser.parse_args()
    STATE.mkdir(exist_ok=True)
    if args.stop:
        STOP.touch()
        return 0
    if args.check:
        print(
            STATUS.read_text("utf-8")
            if STATUS.exists()
            else json.dumps({"phase": "stopped"})
        )
        return 0
    if sys.platform != "win32":
        raise SystemExit("This background listener requires Windows")
    import msvcrt

    # A held byte lock is released by Windows even after a crash or reboot.
    with (STATE / "background-voice.lock").open("a+b") as instance:
        if not instance.tell():
            instance.write(b"\0")
            instance.flush()
        instance.seek(0)
        try:
            msvcrt.locking(instance.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return 0
        STOP.unlink(missing_ok=True)
        handler = RotatingFileHandler(
            STATE / "background-voice.log",
            maxBytes=1_000_000,
            backupCount=2,
            encoding="utf-8",
        )
        logging.basicConfig(
            level=logging.INFO,
            handlers=[handler],
            format="%(asctime)s %(levelname)s %(message)s",
        )
        try:
            BackgroundVoice().run()
        except Exception:
            log.exception("Background voice stopped unexpectedly")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
