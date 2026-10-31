# Jarvis AI Agent

A Windows setup for running [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) with local Ollama inference. No paid AI API key is required for the configured chat model.

## Run on this computer

1. Double-click **Start-OpenJarvis.cmd**. It starts Ollama if needed, then starts the OpenJarvis backend and waits for it to become ready.
2. Open **http://127.0.0.1:8766** if the browser does not open automatically.

An open or cached browser tab alone does not start the backend. Enable automatic voice startup below to start Jarvis when you sign in; otherwise run the shortcut after restarting Windows. If startup fails, check `.openjarvis-runtime/ollama.log` and `.openjarvis-runtime/server.log`.

Startup loads only the server commands and uses the configured Ollama engine without probing unused services. Chat loads secondary pages on demand. Starting a stopped backend still takes a short wait; reopening the page while Jarvis is running is much faster.

Double-click **Stop-OpenJarvis.cmd** to stop this project's server. The default model is **llama3.2:latest**, selected to fit this laptop's memory. Refresh the page after restarting if the browser still shows a different model.

## Set up a fresh clone


Install Git, Python 3.10 or newer, Node.js 22.22 or newer, and Ollama. Then right-click **Setup-OpenJarvis.ps1** and choose **Run with PowerShell**, or run it from PowerShell:

```powershell
.\Setup-OpenJarvis.ps1
```

The setup script installs a separate Python 3.13 environment, downloads the free `llama3.2` model if needed, installs the locked OpenJarvis desktop dependencies, and builds the browser interface. It creates local configuration from `config/config.local.example.toml` without overwriting an existing configuration. Initial setup needs internet access; inference uses the locally downloaded model.

## Hands-free voice and computer commands

### Natural conversation and voice

Run **Enable-NaturalVoice.ps1** to use a free offline neural voice and a conversational reply style. It verifies and downloads the pinned English voice model, keeps a backup of the previous configuration, and restarts Jarvis. **Settings → Speech → Voice** then shows **Neural (local) / Natural English**. Click **Test voice** to hear it.

Jarvis uses shorter, plain-spoken answers, contractions, and recent conversation context. It avoids repeated introductions and stock responses. Follow-up listening lasts 60 seconds after a reply, and the last ten turns are retained within a bounded context window. It remains an AI assistant and does not claim human experiences or completed actions it did not perform.

For a fresh clone, run **Setup-OpenJarvis.ps1 -WithNaturalVoice**. Later setup and memory-install runs preserve the optional voice dependencies. The voice uses [Piper](https://github.com/OHF-Voice/piper1-gpl), an optional GPL-3.0 dependency installed from PyPI, and the upstream [Lessac English voice](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium). Model weights are kept locally and excluded from Git.

### Start with Windows and wake by voice

Run **Enable-BackgroundVoice.ps1** once. It installs the pinned free voice dependencies, downloads a checksum-pinned [Vosk English model](https://alphacephei.com/vosk/models), adds a shortcut to your Windows user Startup folder, and starts a visible Jarvis tray icon. No administrator account or paid API is required. Repeat setup runs preserve this feature.

After signing in, wait for the spoken ready message. Say **“Jarvis”**, wait for its acknowledgment, then ask your question or give a computer command. You can also say **“Jarvis, open YouTube”** in one sentence. Jarvis speaks the answer, then accepts follow-up requests for 60 seconds before returning to wake-word mode. Say **“stop listening”** to end that conversation and return to waiting for “Jarvis.”

The listener works with the browser closed. **Settings → Speech → Wake word: Jarvis** shows its live status and a **Pause microphone** button. The tray icon also offers **Pause microphone**, **Open Jarvis**, and **Quit background voice**. Pausing closes microphone capture; resume using the tray or Settings. Browser voice mode temporarily takes over from the background listener so one request is not handled twice.

It runs while you are signed in and Windows is unlocked. It pauses on the lock screen and resumes after unlock or sleep recovery. A sleeping or powered-off laptop cannot hear the wake word. Wake detection, transcription, reasoning, and voice output run locally. The companion does not save microphone recordings; chat requests use the server's existing local history and trace settings.

**Start-Jarvis-Background.cmd** starts the tray listener manually. **Stop-OpenJarvis.cmd** stops both background voice and this project's backend. **Disable-BackgroundVoice.ps1** removes only this installation's startup shortcut and stops its listener; it retains models and personal data.

### Browser voice mode

In **Settings → Speech**, **Voice** shows the active speech backend. With natural voice enabled it shows **Neural (local)**; the basic installation uses **Windows (local)** and an installed voice such as Microsoft David. Click **Test voice** to check playback, then **Start voice mode** to open Chat and begin listening. Read-aloud buttons and automatic spoken replies use the same backend.

If an old browser tab does not show the voice button, press **Ctrl+Shift+R** or open **http://localhost:8766/**. In Chat, click **Start voice mode** once and allow microphone access in Chrome or Edge. Speak normally, then pause for about 1.2 seconds. Jarvis transcribes locally, runs your command or answers your question, speaks using the active local voice, and starts listening again. Keep the Jarvis tab open. Say **stop listening** or click **Stop voice** to end the session. This browser mode requires the initial click after opening the app; the separately enabled Windows companion provides automatic wake-word listening.

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
- `Enable-BackgroundVoice.ps1` / `Disable-BackgroundVoice.ps1`: enable or remove automatic voice startup for the current Windows user.
- `jarvis_background.py`: local wake-word listener, tray controls, and backend recovery.
- `requirements-background.txt`: pinned optional background voice libraries.
- `Enable-NaturalVoice.ps1` / `natural_voice_setup.py`: verified offline voice installation and conversational style configuration.
- `requirements-natural-voice.txt`: pinned optional neural speech dependencies.
- `config/config.local.example.toml`: shareable configuration template.
- `.openjarvis-runtime/`: personal configuration, databases, downloaded speech models and logs. Kept locally and excluded from Git.
- `.upstream-git/`: original upstream Git history retained locally after the move; excluded from this repository.

External usage analytics and automatic update checks are disabled in the provided configuration. The server binds to loopback only. Model weights, virtual environments, caches, recordings, personal databases and credentials are excluded from GitHub.

## Local fix

The model-list endpoint returns the configured server model first. This prevents a new browser from automatically selecting the larger vision model ahead of the intended lightweight chat model. The model endpoint regression tests passed (8 tests).

## Attribution and license

This project packages and customizes OpenJarvis; it does not claim authorship of the upstream framework. Upstream source was cloned from **open-jarvis/OpenJarvis**, commit **05839014**, with installed version **1.0.5.dev156+g05839014**. OpenJarvis is distributed under the Apache License 2.0. Its original README, license and copyright notices are retained under `OpenJarvis/`; the license is also provided at the project root.

Updates should be reviewed against upstream before replacing the vendored source so the local model-selection fix is preserved.
