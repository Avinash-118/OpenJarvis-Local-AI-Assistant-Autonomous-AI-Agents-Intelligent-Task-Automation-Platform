"""Small offline neural voice for conversational speech on a Windows laptop."""

from __future__ import annotations

import io
import json
import logging
import math
import threading
import wave
from pathlib import Path

from openjarvis.core.paths import get_config_dir
from openjarvis.core.registry import TTSRegistry
from openjarvis.speech.tts import TTSBackend, TTSResult

logger = logging.getLogger(__name__)
VOICE = "en_US-lessac-medium"


def _make_voice(model: Path, config: Path):
    # Optional native libraries are loaded only when speech is requested.
    import onnxruntime as ort
    from piper import PiperVoice
    from piper.config import PiperConfig

    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(
        str(model), sess_options=options, providers=["CPUExecutionProvider"]
    )
    return PiperVoice(
        session=session,
        config=PiperConfig.from_dict(json.loads(config.read_text("utf-8"))),
        download_dir=model.parent,
    )


@TTSRegistry.register("piper")
class PiperTTSBackend(TTSBackend):
    """One cached neural voice shared by chat, read-aloud, and wake-word mode."""

    backend_id = "piper"
    default_voice_id = VOICE

    def __init__(self, model_dir: Path | None = None):
        self.model_dir = (
            Path(model_dir)
            if model_dir is not None
            else get_config_dir() / "neural-voice"
        )
        self._voice = None
        self._lock = threading.RLock()

    def _load(self):
        with self._lock:
            if self._voice is None:
                model = self.model_dir / f"{VOICE}.onnx"
                config = self.model_dir / f"{VOICE}.onnx.json"
                if not model.is_file() or not config.is_file():
                    raise FileNotFoundError(
                        "Natural voice is not installed. Run Enable-NaturalVoice.ps1."
                    )
                self._voice = _make_voice(model, config)
            return self._voice

    def health(self) -> bool:
        try:
            self._load()
            return True
        except Exception:
            logger.debug("Local natural voice unavailable", exc_info=True)
            return False

    def available_voices(self) -> list[str]:
        self._load()
        return [VOICE]

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
            raise ValueError("Natural speech supports WAV audio.")
        if not math.isfinite(speed) or not 0.5 <= speed <= 2:
            raise ValueError("Voice speed must be between 0.5 and 2.0.")
        if voice_id and voice_id != VOICE:
            raise ValueError("The selected neural voice is not installed.")
        from piper import SynthesisConfig

        buffer = io.BytesIO()
        with self._lock, wave.open(buffer, "wb") as output:
            self._load().synthesize_wav(
                text.strip(), output, syn_config=SynthesisConfig(length_scale=1 / speed)
            )
        audio = buffer.getvalue()
        with wave.open(io.BytesIO(audio), "rb") as output:
            rate = output.getframerate()
            duration = output.getnframes() / rate
            if (
                output.getsampwidth() != 2
                or output.getnchannels() != 1
                or duration <= 0
            ):
                raise RuntimeError("The neural voice returned invalid audio.")
        return TTSResult(
            audio=audio,
            format="wav",
            sample_rate=rate,
            duration_seconds=duration,
            voice_id=VOICE,
        )
