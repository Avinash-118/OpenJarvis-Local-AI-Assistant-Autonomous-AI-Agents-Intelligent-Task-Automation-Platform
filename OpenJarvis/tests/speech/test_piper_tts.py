"""Shared natural voice: valid WAV output, bounded settings, and safe fallback."""

import io
import wave
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.server.api_routes import speech_router
from openjarvis.speech import piper_tts
from openjarvis.speech._tts_discovery import get_tts_backend


@pytest.fixture
def fake_voice(monkeypatch, tmp_path):
    folder = tmp_path / "neural-voice"
    folder.mkdir()
    (folder / f"{piper_tts.VOICE}.onnx").write_bytes(b"model")
    (folder / f"{piper_tts.VOICE}.onnx.json").write_text("{}")
    calls = []

    class Voice:
        def synthesize_wav(self, text, output, syn_config):
            calls.append((text, syn_config.length_scale))
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(22050)
            output.writeframes(b"\0\0" * 2205)

    factory = Mock(return_value=Voice())
    monkeypatch.setattr(piper_tts, "_make_voice", factory)
    monkeypatch.setattr(piper_tts, "get_config_dir", lambda: tmp_path)
    return folder, factory, calls


def test_missing_model_does_not_claim_neural_voice_is_ready(tmp_path):
    assert not piper_tts.PiperTTSBackend(tmp_path).health()


def test_model_is_loaded_once_and_real_audio_format_is_preserved(fake_voice):
    folder, factory, calls = fake_voice
    backend = piper_tts.PiperTTSBackend(folder)
    assert backend.health()
    first = backend.synthesize("Hey, I'm here.", speed=0.97)
    backend.synthesize("Tell me more.")
    factory.assert_called_once()
    assert calls[0] == ("Hey, I'm here.", pytest.approx(1 / 0.97))
    assert first.voice_id == piper_tts.VOICE
    assert first.duration_seconds == pytest.approx(0.1)
    with wave.open(io.BytesIO(first.audio)) as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (
            22050,
            1,
            2,
        )


@pytest.mark.parametrize("speed", [0, float("nan"), 5])
def test_invalid_speed_is_rejected_before_loading_model(fake_voice, speed):
    with pytest.raises(ValueError, match="speed"):
        piper_tts.PiperTTSBackend(fake_voice[0]).synthesize("Hello", speed=speed)
    fake_voice[1].assert_not_called()


def test_uninstalled_voice_is_rejected(fake_voice):
    with pytest.raises(ValueError, match="not installed"):
        piper_tts.PiperTTSBackend(fake_voice[0]).synthesize(
            "Hello", voice_id="invented"
        )
    fake_voice[1].assert_not_called()


def test_standard_voice_api_uses_the_same_local_neural_backend(fake_voice):
    app = FastAPI()
    app.state.config = SimpleNamespace(
        speech=SimpleNamespace(
            tts_backend="piper", voice_id=piper_tts.VOICE, voice_speed=0.97
        )
    )
    app.include_router(speech_router)
    client = TestClient(app)
    health = client.get("/v1/speech/tts/health").json()
    assert health == {
        "available": True,
        "backend": "piper",
        "voice_id": piper_tts.VOICE,
        "speed": 0.97,
    }
    response = client.post("/v1/speech/synthesize", json={"text": "Hey, I'm here."})
    assert response.status_code == 200
    assert response.headers["x-voice-id"] == piper_tts.VOICE
    assert response.content[:4] == b"RIFF"


def test_missing_neural_voice_falls_back_to_local_windows(monkeypatch, tmp_path):
    from openjarvis.speech import windows_tts

    monkeypatch.setattr(piper_tts, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(windows_tts.WindowsTTSBackend, "health", lambda _: True)
    assert get_tts_backend("piper").backend_id == "windows"
