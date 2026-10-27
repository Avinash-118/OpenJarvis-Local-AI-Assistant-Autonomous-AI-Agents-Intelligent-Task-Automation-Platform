# Jarvis AI Agent

A Windows setup for running [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) with local Ollama inference. No paid AI API key is required for the configured chat model.

## Run on this computer

1. Double-click **Start-OpenJarvis.cmd**. It starts Ollama if needed, then starts the OpenJarvis backend and waits for it to become ready.
2. Open **http://127.0.0.1:8766** if the browser does not open automatically.

After restarting Windows, run this shortcut again. An open or cached browser tab alone does not start the backend. If startup fails, check `.openjarvis-runtime/ollama.log` and `.openjarvis-runtime/server.log`.

Double-click **Stop-OpenJarvis.cmd** to stop this project's server. The default model is **llama3.2:latest**, selected to fit this laptop's memory. Refresh the page after restarting if the browser still shows a different model.

## Set up a fresh clone

Install Git, Python 3.10 or newer, Node.js 22.22 or newer, and Ollama. Then right-click **Setup-OpenJarvis.ps1** and choose **Run with PowerShell**, or run it from PowerShell:

```powershell
.\Setup-OpenJarvis.ps1
```

The setup script installs a separate Python 3.13 environment, downloads the free `llama3.2` model if needed, installs the locked OpenJarvis desktop dependencies, and builds the browser interface. It creates local configuration from `config/config.local.example.toml` without overwriting an existing configuration. Initial setup needs internet access; inference uses the locally downloaded model.

## Voice input

In the app, open **Settings → Speech → Speech-to-Text** and turn it on. In Chat, click the microphone, allow microphone access, speak, click again to stop, then press Enter to send the transcription. Whisper runs locally; its speech model downloads on first use.

Spoken replies require the optional Kokoro text-to-speech setup. The initial agent is `simple` chat; controlling applications requires configuring a tool agent.

## Layout

- `OpenJarvis/`: OpenJarvis source, upstream license, dependency lockfiles, and local fixes.
- `OpenJarvis-Local.py`: launcher with local inference settings and no inherited cloud API credentials.
- `Start-OpenJarvis.cmd` / `Stop-OpenJarvis.cmd`: Windows shortcuts.
- `Setup-OpenJarvis.ps1`: repeatable setup for a fresh checkout.
- `config/config.local.example.toml`: shareable configuration template.
- `.openjarvis-runtime/`: personal configuration, databases, downloaded speech models and logs. Kept locally and excluded from Git.
- `.upstream-git/`: original upstream Git history retained locally after the move; excluded from this repository.

External usage analytics and automatic update checks are disabled in the provided configuration. The server binds to loopback only. Model weights, virtual environments, caches, recordings, personal databases and credentials are excluded from GitHub.

## Local fix

The model-list endpoint returns the configured server model first. This prevents a new browser from automatically selecting the larger vision model ahead of the intended lightweight chat model. The model endpoint regression tests passed (8 tests).

## Attribution and license

This project packages and customizes OpenJarvis; it does not claim authorship of the upstream framework. Upstream source was cloned from **open-jarvis/OpenJarvis**, commit **05839014**, with installed version **1.0.5.dev156+g05839014**. OpenJarvis is distributed under the Apache License 2.0. Its original README, license and copyright notices are retained under `OpenJarvis/`; the license is also provided at the project root.

Updates should be reviewed against upstream before replacing the vendored source so the local model-selection fix is preserved.
