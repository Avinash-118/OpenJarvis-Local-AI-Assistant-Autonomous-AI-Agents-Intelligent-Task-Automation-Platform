"""Verify voice startup is enabled, detached, and restricted to this checkout."""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class LauncherVoiceTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).with_name("OpenJarvis-Local.py")
        spec = importlib.util.spec_from_file_location("jarvis_test_launcher", path)
        self.launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.launcher)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.launcher.ROOT, self.launcher.STATE = root, root / "state"
        self.launcher.STATE.mkdir()
        self.launcher.PYTHON = root / "python.exe"
        (root / "pythonw.exe").touch()
        (root / "jarvis_background.py").touch()
        self.com = types.SimpleNamespace(CoInitialize=Mock(), CoUninitialize=Mock())
        self.dispatch = Mock()
        self.modules = patch.dict(
            sys.modules,
            {
                "pythoncom": self.com,
                "win32com.client": types.SimpleNamespace(Dispatch=self.dispatch),
            },
        )
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def enable(self):
        (self.launcher.STATE / "background-voice-enabled.json").touch()

    def test_disabled_feature_stays_disabled(self):
        with patch.object(self.launcher.subprocess, "Popen") as process:
            self.launcher.ensure_background_voice({})
        self.dispatch.assert_not_called()
        process.assert_not_called()

    def test_enabled_voice_is_launched_hidden_through_windows_shell(self):
        self.enable()
        self.launcher.ensure_background_voice({})
        args = self.dispatch.return_value.ShellExecute.call_args.args
        self.assertEqual(args[0], str(self.launcher.ROOT / "pythonw.exe"))
        self.assertEqual(
            args[1], '"' + str(self.launcher.ROOT / "jarvis_background.py") + '"'
        )
        self.assertEqual(args[-2:], ("open", 0))
        self.com.CoUninitialize.assert_called_once()

    def test_existing_verified_listener_is_not_launched_twice(self):
        self.enable()
        state = {"pid": 42, "updated_at": self.launcher.time.time()}
        (self.launcher.STATE / "background-voice.json").write_text(
            json.dumps(state), "utf-8"
        )
        with patch("psutil.Process") as process:
            process.return_value.cmdline.return_value = [
                "pythonw.exe",
                str(self.launcher.ROOT / "jarvis_background.py"),
            ]
            self.launcher.ensure_background_voice({})
        self.dispatch.assert_not_called()

    def test_shell_failure_falls_back_to_hidden_local_python(self):
        self.enable()
        self.dispatch.side_effect = RuntimeError("Shell unavailable")
        with patch.object(self.launcher.subprocess, "Popen") as process:
            self.launcher.ensure_background_voice({"test": "value"})
        self.assertEqual(
            process.call_args.args[0][0], str(self.launcher.ROOT / "pythonw.exe")
        )
        self.assertTrue(
            process.call_args.kwargs["creationflags"]
            & self.launcher.subprocess.CREATE_NO_WINDOW
        )


if __name__ == "__main__":
    unittest.main()
