# Linnify AI Talent Pool Manager UI

React frontend for the Linnify challenge implementation. The UI talks to the FastAPI backend for candidate intake, talent pool maintenance, job shortlisting, outreach drafts, review actions, audit events, settings, and assistant proposals.

## Install

```powershell
cd .\ui
npm.cmd install
```

## Run Locally

Start the backend first from the repository root:

```powershell
.\venv\Scripts\python.exe -m uvicorn web.app:app --host 127.0.0.1 --port 8080
```

Then start the UI proxy:

```powershell
cd .\ui
$env:PORT="3000"
$env:FASTAPI_URL="http://127.0.0.1:8080"
$env:DISABLE_HMR="true"
npm.cmd run dev
```

Open `http://127.0.0.1:3000`.

The proxy serves the React app and forwards `/api/*` calls to `FASTAPI_URL`.

## Settings

- Default provider is local/OpenAI-compatible (`local-model`).
- Optional hosted providers are OpenAI, Anthropic, and Gemini.
- Provider keys should be entered in Settings or supplied through local environment variables.
- Real `.env` and `.secrets.json` files are ignored and should not be committed.
- LinkedIn workflows use provided URLs or pasted profile text only. The app does not scrape LinkedIn.

## Checks

```powershell
npm.cmd run lint
npm.cmd run build
```

