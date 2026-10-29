"""Speech output using installed Windows voices, with no model download."""

from __future__ import annotations

import io
import math
import sys
import tempfile
import wave
from contextlib import contextmanager
from pathlib import Path

from openjarvis.core.registry import TTSRegistry
from openjarvis.speech.tts import TTSBackend, TTSResult


@contextmanager
def _speaker():
    if sys.platform != "win32":
        raise RuntimeError("Windows speech output requires Windows.")
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    voice = None
    try:
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        yield voice
    finally:
        voice = None
        pythoncom.CoUninitialize()


def _audio_stream():
    import win32com.client

    return win32com.client.Dispatch("SAPI.SpFileStream")


@TTSRegistry.register("windows")
class WindowsTTSBackend(TTSBackend):
    """The same local voice backend serves Settings, read-aloud and voice mode."""

    backend_id = "windows"

    def __init__(self):
        self.default_voice_id = ""

    def health(self) -> bool:
        try:
            with _speaker() as voice:
                if voice.GetVoices().Count < 1:
                    return False
                self.default_voice_id = voice.Voice.GetDescription()
                return True
        except Exception:
            return False

    def available_voices(self) -> list[str]:
        with _speaker() as voice:
            tokens = voice.GetVoices()
            return [
                tokens.Item(index).GetDescription() for index in range(tokens.Count)
            ]

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        output_format: str = "wav",
    ) -> TTSResult:
        if not text.strip():
            raise ValueError("Speech text must not be empty.")
        if output_format != "wav":
            raise ValueError("Windows speech output supports WAV audio.")
        if not math.isfinite(speed) or not 0.5 <= speed <= 2.0:
            raise ValueError("Voice speed must be between 0.5 and 2.0.")

        with (
            _speaker() as voice,
            tempfile.TemporaryDirectory(prefix="jarvis-speech-") as folder,
        ):
            if voice_id:
                tokens = voice.GetVoices()
                selected = next(
                    (
                        tokens.Item(index)
                        for index in range(tokens.Count)
                        if voice_id
                        in (
                            tokens.Item(index).GetDescription(),
                            tokens.Item(index).Id,
                        )
                    ),
                    None,
                )
                if selected is None:
                    raise ValueError("The selected Windows voice is not installed.")
                voice.Voice = selected
            actual_voice = voice.Voice.GetDescription()
            voice.Rate = round(math.log2(speed) * 5)
            path = Path(folder) / "reply.wav"
            stream = _audio_stream()
            try:
                stream.Open(str(path), 3, False)
                voice.AudioOutputStream = stream
                # SVSFIsNotXML: read literal text, never interpret speech markup.
                voice.Speak(text, 16)
            finally:
                stream.Close()
                stream = None
            audio = path.read_bytes()

        with wave.open(io.BytesIO(audio), "rb") as wav:
            rate = wav.getframerate()
            duration = wav.getnframes() / rate
        return TTSResult(
            audio=audio,
            format="wav",
            voice_id=actual_voice,
            sample_rate=rate,
            duration_seconds=duration,
        )
