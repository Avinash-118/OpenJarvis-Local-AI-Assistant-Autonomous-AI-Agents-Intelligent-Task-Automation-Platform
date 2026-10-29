"""Regressions for the shared Windows voice backend and ordinary speech API."""

import io
import wave
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.server.api_routes import speech_router
from openjarvis.speech import windows_tts
from openjarvis.speech._tts_discovery import get_tts_backend


@pytest.fixture
def fake_sapi(monkeypatch):
    token = SimpleNamespace(
        GetDescription=lambda: "Microsoft Test Voice", Id="installed-test-voice"
    )
    tokens = SimpleNamespace(Count=1, Item=lambda index: token)
    speaker = SimpleNamespace(GetVoices=lambda: tokens, Voice=token, Rate=0)
    calls = []

    class Stream:
        def Open(self, path, mode, events):
            self.path = path

        def Close(self):
            pass

    def speak(text, flags):
        calls.append((text, flags))
        with wave.open(speaker.AudioOutputStream.path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b"\0\0" * 2205)

    speaker.Speak = speak

    @contextmanager
    def available():
        yield speaker

    monkeypatch.setattr(windows_tts, "_speaker", available)
    monkeypatch.setattr(windows_tts, "_audio_stream", Stream)
    return speaker, tokens, calls


def test_health_detects_installed_voice(fake_sapi):
    backend = windows_tts.WindowsTTSBackend()
    assert backend.health()
    assert backend.default_voice_id == "Microsoft Test Voice"
    assert backend.available_voices() == ["Microsoft Test Voice"]


def test_missing_voice_does_not_report_ready(fake_sapi):
    fake_sapi[1].Count = 0
    assert not windows_tts.WindowsTTSBackend().health()


def test_windows_synthesis_produces_literal_wav_and_removes_temp_file(fake_sapi):
    backend = windows_tts.WindowsTTSBackend()
    result = backend.synthesize("<audio>Read these words literally</audio>", speed=1.5)
    assert fake_sapi[2] == [("<audio>Read these words literally</audio>", 16)]
    assert fake_sapi[0].Rate > 0
    with wave.open(io.BytesIO(result.audio), "rb") as wav:
        assert wav.getframerate() == result.sample_rate == 22050
    assert result.duration_seconds == pytest.approx(0.1)
    from pathlib import Path

    assert not Path(fake_sapi[0].AudioOutputStream.path).exists()


def test_unknown_voice_is_rejected_without_speaking(fake_sapi):
    with pytest.raises(ValueError, match="not installed"):
        windows_tts.WindowsTTSBackend().synthesize("Hello", voice_id="invented")
    assert not fake_sapi[2]


@pytest.mark.parametrize("speed", [0, float("nan"), 5])
def test_bad_speed_is_rejected(fake_sapi, speed):
    with pytest.raises(ValueError, match="speed"):
        windows_tts.WindowsTTSBackend().synthesize("Hello", speed=speed)


def test_standard_speech_api_discovers_and_synthesizes_windows_voice(fake_sapi):
    # The screenshot used this endpoint, rather than /v1/desktop/speak.
    app = FastAPI()
    app.state.config = SimpleNamespace(
        speech=SimpleNamespace(tts_backend="windows", voice_id="", voice_speed=1.0)
    )
    app.include_router(speech_router)
    client = TestClient(app)
    health = client.get("/v1/speech/tts/health").json()
    assert health == {
        "available": True,
        "backend": "windows",
        "voice_id": "Microsoft Test Voice",
        "speed": 1.0,
    }
    response = client.post(
        "/v1/speech/synthesize", json={"text": "Hello from Settings"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["x-voice-id"] == "Microsoft Test Voice"
    assert response.content[:4] == b"RIFF"
    assert get_tts_backend("windows").backend_id == "windows"
