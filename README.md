# Buildathon AI Project

This repository contains an experimental AI application with a Python backend (`core/`, `tools/`, `requirements/`) and a separate UI layer (`ui/`, `web/`). It is designed so you can either:

- Run the system against a **local model** using **LM Studio**, or  
- Run it against a **hosted model API** using an **API key** configured in `config.json` and environment variables.

The sections below walk through installation, running the project, and configuring model access in both modes.

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

1. (Optional) Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Linux / macOS
   # or
   .venv\Scripts\activate         # Windows
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

1. Open `config.json` in the repo root.
2. Look for fields related to the model provider, for example:

   ```jsonc
   {
     "model_backend": "lmstudio",
     "lmstudio": {
       "base_url": "http://localhost:1234/v1",
       "model": "your-model-name"
     }
   }
   ```

   Adjust field names to match the existing schema in `config.json` (do not invent new keys; reuse what’s there).

3. Make sure:
   - `base_url` matches the LM Studio server URL.
   - `model` matches the model name LM Studio displays for your running server.

4. Save `config.json`.

### 4.3 Run the backend with LM Studio

From the repo root, start the main backend process. Depending on how the project is structured, it might look like:

```bash
python -m core.main
# or
python core/main.py
# or another documented entrypoint in core/
```

Check the scripts or `core/` package to confirm the actual command used in this version of the repo.

Once the backend is running:

- Open the UI (see section 6) and interact with the system.
- All model calls should go to LM Studio’s local server, with no external API usage.

---

## 5. Using a hosted API key (OpenAI-style)

Instead of LM Studio, you can also use a hosted LLM provider via an API key.

### 5.1 Get an API key

1. Register with your chosen provider (e.g., OpenAI, Anthropic, etc.).
2. Create an API key in their dashboard.
3. **Never commit this key** to version control.

### 5.2 Export the API key as an environment variable

On Linux / macOS:

```bash
export OPENAI_API_KEY="your-key-here"
```

On Windows (PowerShell):

```powershell
$env:OPENAI_API_KEY="your-key-here"
```

Adjust the environment variable name to match what the code expects (for example `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.), based on how the project reads configuration in `core/`.

### 5.3 Configure `config.json` for API mode

Open `config.json` and switch to an API provider configuration, for example:

```jsonc
{
  "model_backend": "openai",
  "openai": {
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4.1-mini"
  }
}
```

Use the existing structure in `config.json` as a template and only change values (not the general schema). Typical fields:

- `model_backend` – string switch indicating which backend to use.
- Provider-specific section (`openai`, `anthropic`, etc.) – base URL and model name.

The backend will combine `config.json` with your environment variables when making requests.

### 5.4 Run the backend with hosted API

With your environment variable set and `config.json` pointing to the API provider, start the backend as in LM Studio mode:

```bash
python -m core.main
# or equivalent entrypoint
```

Requests will now be sent to the hosted API instead of LM Studio.

---

## 6. Running the UI

This project appears to have both `ui/` and `web/` directories for the interface layer.

Typical pattern:

1. Start the backend (section 4.3 or 5.4).
2. In a new terminal, move into the UI directory:

   ```bash
   cd web
   # or
   cd ui
   ```

3. Follow the readme or package file there:
   - If it is a JavaScript/TypeScript frontend, you will likely run:

     ```bash
     npm install
     npm run dev
     ```

   - Or another command indicated by the scripts in `package.json` within that directory.

4. Open the local URL printed by the UI dev server (commonly `http://localhost:5173` or `http://localhost:3000`) in your browser.

From there, you can interact with the system end-to-end: the UI talks to the backend, and the backend talks either to LM Studio or your chosen hosted provider.

---

## 7. Switching between LM Studio and API mode

To switch back and forth:

1. Stop the backend.
2. Edit `config.json`:
   - Set `"model_backend"` to `"lmstudio"` for local LM Studio.
   - Set `"model_backend"` to `"openai"` (or the relevant provider string) for hosted API.
3. Start or stop LM Studio’s local server as needed.
4. Ensure the correct environment variables are set for hosted API mode.

You do not need to change code when switching; configuration and environment variables are sufficient, as long as you follow the existing `config.json` schema and the expected env var names used by the code in `core/`.

---

## 8. Troubleshooting

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

