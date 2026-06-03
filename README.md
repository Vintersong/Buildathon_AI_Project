# Buildathon AI Project

This repository contains an experimental AI application with a Python backend (`core/`, `tools/`, `requirements/`) and a separate UI layer (`ui/`, `web/`). **Bring your own key for whatever agent you want** — pick a provider in the in-app **Settings** page and paste your API key. Supported providers:

- **Anthropic (Claude)** — set an Anthropic API key
- **OpenAI (GPT)** — set an OpenAI API key
- **Google Gemini** — set a Gemini API key
- **Local / OpenAI-compatible** — a local model via **LM Studio**, Ollama, or any OpenAI-compatible server (no key required)

Keys are stored locally in `.secrets.json` (gitignored) and never committed. With no key configured the app still runs using built-in heuristic extraction and template outreach, so you can explore the UI before adding a provider.

The sections below walk through installation, running the project, and configuring model access.

---

## 1. Prerequisites

Before you start, install:

- **Python 3.10+** (and `pip`)
- **Git**
- Optional but recommended: **virtualenv** or another environment manager
- For local inference: **LM Studio** (desktop app)

Clone the repository:

```bash
git clone https://github.com/Vintersong/Buildathon_AI_Project.git
cd Buildathon_AI_Project
```

The repository root contains `requirements.txt`, `config.json`, and the main code directories (`core/`, `tools/`, `ui/`, `web/`).

---

## 2. Python environment & dependencies

To keep things clean it is recommended to use a Python virtual environment.

1. Create and activate a virtual environment:

   **Linux / macOS:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

   **Windows (PowerShell):**

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

2. Install dependencies for the backend:

   ```bash
   pip install -r requirements.txt
   ```

If there are additional sub-requirements under `requirements/`, install them in the same environment as needed.

---

## 3. Basic project layout

Key directories and files:

- `core/` – Core application logic (orchestration, main services, etc.).
- `tools/` – Helper utilities, tools, or integrations used by the core.
- `ui/` – UI-related files (desktop or local UI development assets).
- `web/` – Web UI or frontend code.
- `config.json` – Main configuration file (model provider, API keys, ports, etc.).
- `requirements.txt` – Python dependency list.

You will typically:

1. Configure `config.json` according to your preferred model backend.
2. Export any needed environment variables (for API keys).
3. Start the backend (e.g., a main Python entrypoint under `core/`).
4. Start the UI (web or desktop) from `ui/` or `web/`.

Because entrypoints can change over time, open `core/` and `web/` to find the appropriate `main.py`/`app.py` and frontend dev commands when setting things up locally.

---

## 4. Using LM Studio (local model)

This mode runs the model on your own machine via LM Studio’s local server.

### 4.1 Install and set up LM Studio

1. Download and install **LM Studio** from its official website.
2. Open LM Studio and:
   - Go to the **Models** or **Explore** section.
   - Download a compatible chat or instruct model (for example, a LLaMA or Mistral variant that supports chat completion).
3. Go to the **Server** / **Local Inference Server** tab inside LM Studio.
4. Start the local server:
   - Choose the model you downloaded.
   - Set the host and port (by default LM Studio usually runs on `http://localhost:1234` for its API server).
   - Start the server and keep LM Studio running.

### 4.2 Point this project at LM Studio

1. Open `config.json` in the repo root and set `use_local_llm` to `true`:

   ```json
   {
     "model": "google/gemma-4-e4b",
     "confidence_threshold": 0.85,
     "sovereign_cloud": true,
     "use_local_llm": true
   }
   ```

2. Make sure the `model` value matches the model ID shown in LM Studio (check the **Local Server** tab — it lists the loaded model ID).

3. If LM Studio is running on a non-default port, set the env var before starting the backend:

   ```powershell
   # Windows
   $env:LM_STUDIO_BASE_URL="http://localhost:1234/v1"
   $env:LM_STUDIO_MODEL="google/gemma-4-e4b"
   ```

   ```bash
   # Linux / macOS
   export LM_STUDIO_BASE_URL="http://localhost:1234/v1"
   export LM_STUDIO_MODEL="google/gemma-4-e4b"
   ```

### 4.3 Run the backend with LM Studio

From the repo root:

```bash
python -m uvicorn web.app:app --host 127.0.0.1 --port 8080 --reload
```

The API will be available at `http://127.0.0.1:8080`.  
The built React UI is served automatically from the same port — open `http://127.0.0.1:8080` in your browser.

Once the backend is running all model calls go to LM Studio’s local server with no external API usage.

---

## 5. Using a hosted provider (Anthropic / OpenAI / Gemini)

Instead of a local model you can use any hosted provider via an API key. The flow is the same for all of them — only the key and model name differ.

### 5.1 Get an API key

| Provider | Where to get a key | Example model |
|----------|--------------------|---------------|
| Anthropic (Claude) | [console.anthropic.com](https://console.anthropic.com/) | `claude-sonnet-4-6` |
| OpenAI (GPT) | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | `gpt-4o-mini` |
| Google Gemini | [Google AI Studio](https://aistudio.google.com/app/apikey) | `gemini-2.5-flash` |

**Never commit your key** — the project keeps it out of `config.json` automatically and stores it in the gitignored `.secrets.json`.

### 5.2 Choose a provider and set the key

**Option A — Settings UI (recommended):**

1. Start the backend (see section 4.3) and open `http://127.0.0.1:8080` → **Settings**.
2. Pick your provider from the **Provider** dropdown (the model name defaults sensibly; adjust if needed).
3. Paste the key for that provider and click **Save**. It takes effect immediately — no restart.

Keys are stored per-provider in `.secrets.json`, so you can keep several configured and switch the dropdown at will.

**Option B — environment variable:**

```bash
export ANTHROPIC_API_KEY="your-key-here"   # or OPENAI_API_KEY / GEMINI_API_KEY
```
```powershell
$env:ANTHROPIC_API_KEY="your-key-here"     # Windows PowerShell
```

### 5.3 Provider selection in `config.json`

```json
{
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "confidence_threshold": 0.85,
  "sovereign_cloud": false,
  "use_local_llm": false
}
```

`provider` selects the backend (`gemini` | `openai` | `anthropic` | `local`) and `model` is the model name for that provider. The Settings UI writes both fields for you.

### 5.4 Run the backend

```bash
python -m uvicorn web.app:app --host 127.0.0.1 --port 8080 --reload
```

All model calls now route to your selected provider.

---

## 6. Running the UI

The React UI is pre-built in `ui/dist/` and served automatically by the backend at `http://127.0.0.1:8080`. **No separate UI process is needed for normal use** — just start the backend (section 4.3 or 5.4) and open that URL.

### 6.1 Rebuilding the UI (after frontend changes)

If you modify anything under `ui/src/`, rebuild before restarting the backend:

```bash
cd ui
npm install       # first time only
npm run build
```

Then restart the backend server.

### 6.2 Frontend dev server (hot reload)

For active frontend development, run the Vite dev server alongside the backend:

**Terminal 1 — backend:**
```bash
python -m uvicorn web.app:app --host 127.0.0.1 --port 8080 --reload
```

**Terminal 2 — frontend dev server:**
```bash
cd ui
npm run dev
```

Open `http://localhost:5173` — it proxies API calls to the backend on port 8080.

---

## 7. Switching providers

The `provider` field in `config.json` controls which backend is used:

| `provider` | Requires |
|---|---|
| `anthropic` | Anthropic API key (env var or Settings UI) |
| `openai` | OpenAI API key (env var or Settings UI) |
| `gemini` | Gemini API key (env var or Settings UI) |
| `local` | a local OpenAI-compatible server (e.g. LM Studio on port 1234) |

The easiest way to switch is the **Provider** dropdown on the **Settings** page in the UI — no file editing required. (`use_local_llm: true` is still honoured as a legacy shortcut for `provider: local`.)

---

## 8. Running the LangChain benchmark

The project includes a binary candidate-role matching evaluation powered by LangChain. It uses LM Studio when available and falls back to a local heuristic automatically.

```bash
# Full run (32 examples — needs LM Studio, may be slow on low-end hardware)
python -m tools.eval_candidates

# Lightweight run (recommended for demos / CI)
python -m tools.eval_candidates --limit 6

# Custom dataset or accuracy target
python -m tools.eval_candidates --data tests/data/candidate_role_eval.csv --target 0.8
```

Exit code `0` = pass, `1` = below target, `2` = startup error.

---

## 9. Troubleshooting


- **Backend cannot reach model**  
  - Check `config.json` values (URL, model name).  
  - For LM Studio, verify the server is running and the port matches.  
  - For APIs, confirm your environment variable is exported in the same shell.

- **UI shows errors or blank page**  
  - Make sure the backend is running first.  
  - Check the UI dev server output for port and error messages.  
  - Confirm any API base URL in the UI config matches the backend address.

- **Import or module errors in Python**  
  - Verify the virtual environment is activated.  
  - Re-run `pip install -r requirements.txt`.

