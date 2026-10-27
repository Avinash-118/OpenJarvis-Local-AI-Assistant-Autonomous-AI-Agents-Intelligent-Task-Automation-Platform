"""Startup regressions: model server reuse, startup, and readable failures."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location('local_launcher', Path(__file__).with_name('OpenJarvis-Local.py'))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class StartupTests(unittest.TestCase):
    def test_existing_ollama_is_reused(self):
        with patch.object(launcher, 'ollama_ready', return_value=True), patch.object(launcher.subprocess, 'Popen') as spawn:
            launcher.ensure_ollama({})
        spawn.assert_not_called()

    def test_stopped_ollama_is_started_on_loopback(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(launcher, 'STATE', Path(folder)), \
                patch.object(launcher, 'ollama_ready', side_effect=[False, True]), \
                patch.object(launcher.shutil, 'which', return_value='ollama.exe'), \
                patch.object(launcher.subprocess, 'Popen') as spawn:
            launcher.ensure_ollama({'EXAMPLE': 'preserved'})
        self.assertEqual(spawn.call_args.args[0], ['ollama.exe', 'serve'])
        self.assertEqual(spawn.call_args.kwargs['env']['OLLAMA_HOST'], '127.0.0.1:11434')
        self.assertEqual(spawn.call_args.kwargs['env']['EXAMPLE'], 'preserved')

    def test_missing_ollama_has_actionable_error(self):
        with patch.object(launcher, 'ollama_ready', return_value=False), \
                patch.object(launcher.shutil, 'which', return_value=None), \
                patch.object(launcher.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(SystemExit, 'Ollama is not installed'):
                launcher.ensure_ollama({})
        spawn.assert_not_called()

    def test_failed_start_points_to_log(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(launcher, 'STATE', Path(folder)), \
                patch.object(launcher, 'ollama_ready', return_value=False), \
                patch.object(launcher.shutil, 'which', return_value='ollama.exe'), \
                patch.object(launcher.subprocess, 'Popen', return_value=Mock(poll=Mock(return_value=1))):
            with self.assertRaisesRegex(SystemExit, 'ollama.log'):
                launcher.ensure_ollama({})


if __name__ == '__main__':
    unittest.main()
