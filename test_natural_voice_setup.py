"""Voice configuration changes preserve the user's other local settings."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tomlkit

import natural_voice_setup as setup


class ProfileTests(unittest.TestCase):
    def test_profile_preserves_existing_settings_and_original_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / "state"
            state.mkdir()
            config = root / "config"
            config.mkdir()
            (config / "conversation-prompt.txt").write_text(
                "Talk naturally, and be honest.", "utf-8"
            )
            original = '[server]\nport=8766\n[engine]\ndefault="ollama"\n[speech]\nmodel="small"\ntts_backend="windows"\n'
            path = state / "config.toml"
            path.write_text(original, "utf-8")
            with patch.object(setup, "ROOT", root), patch.object(setup, "STATE", state):
                setup.apply_profile()
                result = tomlkit.parse(path.read_text("utf-8"))
                self.assertEqual(result["server"]["port"], 8766)
                self.assertEqual(result["engine"]["default"], "ollama")
                self.assertEqual(result["speech"]["model"], "small")
                self.assertEqual(result["speech"]["tts_backend"], "piper")
                self.assertEqual(
                    result["agent"]["default_system_prompt"],
                    "Talk naturally, and be honest.",
                )
                setup.apply_profile()
                self.assertEqual(
                    (state / "config.before-natural-voice.toml").read_text("utf-8"),
                    original,
                )

    def test_bad_download_is_never_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model"
            path.write_bytes(b"not the model")
            self.assertFalse(setup.verify(path, "0" * 64))


if __name__ == "__main__":
    unittest.main()
