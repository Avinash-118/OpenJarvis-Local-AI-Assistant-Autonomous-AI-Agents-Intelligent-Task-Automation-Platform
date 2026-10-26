"""Launch this OpenJarvis checkout using local inference and workspace state."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'OpenJarvis'
STATE = ROOT / '.openjarvis-runtime'
PYTHON = SOURCE / '.venv' / 'Scripts' / 'python.exe'
URL = 'http://127.0.0.1:8766'


def local_environment():
    env = os.environ.copy()
    # Do not expose inherited cloud credentials to a local-only app.
    # This changes the child process environment, never Windows settings.
    for name in list(env):
        if name.endswith('_API_KEY') or name.endswith('_API_TOKEN') or name in (
            'HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN', 'ANTHROPIC_AUTH_TOKEN',
        ):
            env.pop(name, None)
    env.update({
        'OPENJARVIS_HOME': str(STATE),
        'OPENJARVIS_NO_UPDATE_CHECK': '1',
        'JARVIS_NUM_CTX': '4096',
        'PYTHONUTF8': '1',
        'PYTHONIOENCODING': 'utf-8',
        'NIM_HOST': 'http://127.0.0.1:9',
        'HF_HOME': str(STATE / 'huggingface'),
    })
    return env


def healthy():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URL + '/health', timeout=2) as response:
            return json.load(response).get('status') == 'ok'
    except (OSError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser(description='Start or stop the local OpenJarvis installation.')
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not PYTHON.is_file():
        raise SystemExit('OpenJarvis is not installed: its Python environment is missing.')
    STATE.mkdir(exist_ok=True)
    env = local_environment()
    command = [str(PYTHON), '-m', 'openjarvis.cli', '--quiet']
    if args.stop:
        return subprocess.call(command + ['stop'], cwd=SOURCE, env=env)
    if healthy():
        # Confirm the service is registered to this checkout's state directory.
        state_path = STATE / 'server.json'
        if not state_path.is_file():
            raise SystemExit('Port 8766 is already in use. No existing service was changed.')
        state = json.loads(state_path.read_text('utf-8'))
        import psutil
        try:
            process = psutil.Process(state['pid'])
            if Path(process.cwd()).resolve() != SOURCE.resolve() or 'openjarvis.cli' not in process.cmdline():
                raise SystemExit('Port 8766 belongs to another process. No existing service was changed.')
        except psutil.Error:
            raise SystemExit('Could not verify the existing OpenJarvis process. Check server.log.')
    else:
        result = subprocess.call(command + ['start', '--host', '127.0.0.1', '--port', '8766',
                                            '--engine', 'ollama', '--model', 'llama3.2:latest', '--agent', 'simple'],
                                 cwd=SOURCE, env=env)
        if result:
            return result
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and not healthy():
            time.sleep(1)
        if not healthy():
            raise SystemExit(f'OpenJarvis did not become ready. Check {STATE / "server.log"}')
    print(f'OpenJarvis is ready: {URL}')
    if not args.no_browser:
        webbrowser.open(URL)
    return 0


if __name__ == '__main__':
    sys.exit(main())
