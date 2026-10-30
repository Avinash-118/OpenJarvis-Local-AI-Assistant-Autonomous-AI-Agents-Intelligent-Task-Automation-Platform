"""Keep the local launcher independent of unrelated CLI features and probes."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("command", ["start", "stop", "restart", "status", "serve"])
def test_server_entry_points_skip_unrelated_commands(command, tmp_path):
    code = """
import sys
command = sys.argv[1]
sys.argv = ['jarvis', '--quiet', command, '--help']
from openjarvis.cli import cli
cli.main(standalone_mode=False)
for name in ('ask', 'bench_cmd', 'eval_cmd', 'deep_research_setup_cmd'):
    assert 'openjarvis.cli.' + name not in sys.modules, name
if command != 'serve':
    assert 'openjarvis.cli.serve' not in sys.modules
    assert 'openjarvis.engine' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code, command],
        env={
            **os.environ,
            "OPENJARVIS_HOME": str(tmp_path),
            "OPENJARVIS_NO_UPDATE_CHECK": "1",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Usage:" in result.stdout


def test_single_engine_startup_does_not_probe_other_services(monkeypatch):
    serve = importlib.import_module("openjarvis.cli.serve")
    probe = Mock(side_effect=AssertionError("unrelated services were probed"))
    monkeypatch.setattr(serve, "discover_engines", probe)
    monkeypatch.setenv("OPENJARVIS_DISCOVER_ENGINES", "0")
    engine = object()
    assert serve._startup_engines(object(), "ollama", engine) == [("ollama", engine)]
    probe.assert_not_called()


def test_normal_startup_retains_engine_discovery(monkeypatch):
    serve = importlib.import_module("openjarvis.cli.serve")
    expected = [("ollama", object()), ("vllm", object())]
    probe = Mock(return_value=expected)
    monkeypatch.setattr(serve, "discover_engines", probe)
    monkeypatch.delenv("OPENJARVIS_DISCOVER_ENGINES", raising=False)
    config = object()
    assert serve._startup_engines(config, "ollama", object()) == expected
    probe.assert_called_once_with(config)
