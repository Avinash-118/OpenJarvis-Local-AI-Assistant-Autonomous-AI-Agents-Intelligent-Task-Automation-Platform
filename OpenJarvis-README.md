# OpenJarvis on this computer

Double-click **Start-OpenJarvis.cmd** to start the local server and open the app.
The address is **http://127.0.0.1:8766**. Double-click **Stop-OpenJarvis.cmd** to stop it.

- Source: `OpenJarvis/`, cloned from https://github.com/open-jarvis/OpenJarvis.
- Python: the project's separate `.venv`, using Python 3.13.
- Frontend: built from the repository and served by the backend; Node is not needed on each launch.
- Inference: existing Ollama installation, with `llama3.2:latest` selected.
- Settings, local databases and logs: `.openjarvis-runtime/` beside the source folder.
- Optional external usage analytics and update checks are disabled.
- The launcher removes inherited cloud API credentials from the app's environment. It does not change your Windows environment or other applications.

Keep Ollama running. The installed models can be used without a paid API account.
The default configuration starts with conversation. Tool agents and other integrations can be configured inside OpenJarvis.

The model-list endpoint has a local fix to put the configured chat model first. This prevents a new browser profile from automatically selecting the larger vision model just because it appears first in Ollama's list. If you encounter a memory error, refresh the page and confirm that the model selector shows `llama3.2:latest`.

The desktop dependencies include faster-whisper for microphone transcription. Its model downloads on first use. Neural spoken replies require the optional Kokoro voice setup; a successful text chat does not validate microphone or speaker hardware.

For troubleshooting, read `.openjarvis-runtime/server.log`. The optional Rust extension is not built in this setup.

## Updating later

Stop the app, then update the checkout and reinstall its locked dependencies before rebuilding the frontend. The launch and configuration files are outside the cloned repository so they remain separate from upstream source changes.
