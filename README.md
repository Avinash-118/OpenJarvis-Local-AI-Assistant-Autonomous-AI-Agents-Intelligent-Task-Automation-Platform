# Jarvis AI Agent

A Windows setup for running [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) with local Ollama inference. No paid AI API key is required for the configured chat model.

## Run on this computer

1. Double-click **Start-OpenJarvis.cmd**. It starts Ollama if needed, then starts the OpenJarvis backend and waits for it to become ready.
2. Open **http://127.0.0.1:8766** if the browser does not open automatically.

After restarting Windows, run this shortcut again. An open or cached browser tab alone does not start the backend. If startup fails, check `.openjarvis-runtime/ollama.log` and `.openjarvis-runtime/server.log`.

Startup loads only the server commands and uses the configured Ollama engine without probing unused services. Chat loads secondary pages on demand. Starting a stopped backend still takes a short wait; reopening the page while Jarvis is running is much faster.

Double-click **Stop-OpenJarvis.cmd** to stop this project's server. The default model is **llama3.2:latest**, selected to fit this laptop's memory. Refresh the page after restarting if the browser still shows a different model.

## Set up a fresh clone

Install Git, Python 3.10 or newer, Node.js 22.22 or newer, and Ollama. Then right-click **Setup-OpenJarvis.ps1** and choose **Run with PowerShell**, or run it from PowerShell:

```powershell
.\Setup-OpenJarvis.ps1
```

The setup script installs a separate Python 3.13 environment, downloads the free `llama3.2` model if needed, installs the locked OpenJarvis desktop dependencies, and builds the browser interface. It creates local configuration from `config/config.local.example.toml` without overwriting an existing configuration. Initial setup needs internet access; inference uses the locally downloaded model.

## Hands-free voice and computer commands

In **Settings → Speech**, **Voice** should show **Windows (local)** and an installed voice such as Microsoft David. Click **Test voice** to check playback, then **Start voice mode** to open Chat and begin listening. Read-aloud buttons and automatic spoken replies use the same backend.

If an old browser tab does not show the voice button, press **Ctrl+Shift+R** or open **http://localhost:8766/**. In Chat, click **Start voice mode** once and allow microphone access in Chrome or Edge. Speak normally, then pause for about 1.2 seconds. Jarvis transcribes locally, runs your command or answers your question, speaks using an installed Windows voice, and starts listening again. Keep the Jarvis tab open. Say **stop listening** or click **Stop voice** to end the session. The browser requires the initial click after opening the app; recording never starts secretly on page load.

Try:

- “Open Gmail” or “Open YouTube.”
- “Search relaxing music on YouTube” or “Search the web for Chicago weather.”
- “Open Notepad,” “Open calculator,” “Open Access,” or the name of an installed Start menu app.
- “Write an email to someone@example.com asking about tomorrow’s meeting.” This opens a populated Gmail draft; review and send it yourself.
- With another app in the foreground, “Click the search box” or “Fill the search box with relaxing music.” The local model can use accessible Windows controls for a bounded sequence of steps.

Websites open in your normal default browser and can reuse its existing sign-ins. If a site requests a password, verification code, CAPTCHA, or other login step, complete that step in the site. Jarvis does not collect or store passwords. Website controls and Windows accessibility vary, so arbitrary workflows are not guaranteed. It will report unavailable controls instead of claiming completion. YouTube search opens results; selecting a particular video requires an accessible control and a follow-up instruction.

The one-shot microphone remains available for dictation into the message box. Hands-free voice needs no Kokoro model or paid speech service. Whisper may download its free speech model on first use. Small local language models can take several seconds to answer on this laptop.

Desktop commands are enabled only by this project's launcher, only on Windows, and only through the local same-origin interface. Generated shell commands are never executed. Use **Stop generating** to cancel a running task; stopping voice mode stops listening and playback.

## Optional native memory

SQLite memory requires OpenJarvis's Rust extension. Install Visual Studio Build Tools with **Desktop development with C++**, then run:

```powershell
.\Enable-Memory.ps1
```

This installs the pinned Rust 1.89 toolchain inside `.tools`, checks the official installer's SHA-256, builds the native extension, and restarts Jarvis. The first build can take a while. Subsequent setup runs preserve memory through a local marker. For a fresh clone with the C++ prerequisites installed, use `.\Setup-OpenJarvis.ps1 -WithMemory`.

## Layout

- `OpenJarvis/`: OpenJarvis source, upstream license, dependency lockfiles, and local fixes.
- `OpenJarvis-Local.py`: launcher with local inference settings and no inherited cloud API credentials.
- `Start-OpenJarvis.cmd` / `Stop-OpenJarvis.cmd`: Windows shortcuts.
- `Setup-OpenJarvis.ps1`: repeatable setup for a fresh checkout.
- `Enable-Memory.ps1`: optional project-local Rust/native memory setup.
- `config/config.local.example.toml`: shareable configuration template.
- `.openjarvis-runtime/`: personal configuration, databases, downloaded speech models and logs. Kept locally and excluded from Git.
- `.upstream-git/`: original upstream Git history retained locally after the move; excluded from this repository.

External usage analytics and automatic update checks are disabled in the provided configuration. The server binds to loopback only. Model weights, virtual environments, caches, recordings, personal databases and credentials are excluded from GitHub.

## Local fix

The model-list endpoint returns the configured server model first. This prevents a new browser from automatically selecting the larger vision model ahead of the intended lightweight chat model. The model endpoint regression tests passed (8 tests).

## Attribution and license

This project packages and customizes OpenJarvis; it does not claim authorship of the upstream framework. Upstream source was cloned from **open-jarvis/OpenJarvis**, commit **05839014**, with installed version **1.0.5.dev156+g05839014**. OpenJarvis is distributed under the Apache License 2.0. Its original README, license and copyright notices are retained under `OpenJarvis/`; the license is also provided at the project root.

Updates should be reviewed against upstream before replacing the vendored source so the local model-selection fix is preserved.
