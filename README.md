# Linnify AI Talent Pool Manager

AI Talent Pool Manager for the Linnify buildathon challenge. The app helps a recruiter extract candidate profiles, maintain a local talent pool, create job requirements, shortlist candidates, prepare outreach drafts, resolve review items, and inspect audit activity.

The project is local-first by default. A fresh clone runs without bundled API keys, without committed candidate data, and without any hosted-model dependency. Optional OpenAI, Anthropic, or Gemini keys can be added by each user in Settings for experiments, but the Linnify assistant workflow uses typed local proposals and human confirmation before records change.

## What Is Implemented

- Candidate intake from pasted CV text, uploaded CV files, spreadsheet rows, and provided LinkedIn URL/text.
- Talent pool records with provenance, compliance status, stale-profile detection, and manual refresh.
- Jobs and shortlist workflow with evidence-oriented ranking.
- Outreach drafts that are created for human review, not sent externally.
- Review queue for compliance flags, identity conflicts, and outreach drafts.
- Maintenance tools for intake processing, stale scans, bulk refresh, audit health, and compliance status.
- Assistant proposals for create job, shortlist, outreach draft, stale scan, intake processing, candidate refresh, and review summary workflows.
- Audit events for proposed and confirmed assistant actions.

## Security Notes

- `config.json` defaults to the local provider: `provider: "local"`, `model: "local-model"`.
- API keys are never stored in `config.json`; Settings writes them to `.secrets.json`, which is gitignored.
- Candidate-aware assistant actions are typed proposals. The user must confirm before data-changing actions execute.
- The assistant confirmation path disables hosted-model rerank/extraction/outreach calls for candidate data.
- LinkedIn refresh means "update from user-provided URL/text/profile data" or "flag as stale"; the app does not scrape LinkedIn.
- Outreach drafts stay in the review queue. The app does not send emails or external messages.

## Requirements

- Python 3.10+
- Node.js 20+ and npm
- Git
- Optional: LM Studio, Ollama, or another OpenAI-compatible local model server

## Install

From Windows PowerShell:

```powershell
git clone https://github.com/Vintersong/Buildathon_AI_Project.git
cd Buildathon_AI_Project

py -3 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt

cd .\ui
npm.cmd install
cd ..
```

The virtual environment can be named `venv` or `.venv`; both are ignored by git. The commands above use `venv` because that is the path used in the local startup examples.

## Start Locally

Terminal 1, from the repo root:

```powershell
.\venv\Scripts\python.exe -m uvicorn web.app:app --host 127.0.0.1 --port 8080
```

Terminal 2, from the repo root:

```powershell
cd .\ui
$env:PORT="3000"
$env:FASTAPI_URL="http://127.0.0.1:8080"
$env:DISABLE_HMR="true"
npm.cmd run dev
```

Open:

```text
http://127.0.0.1:3000
```

The UI dev server proxies `/api/*` requests to FastAPI on port `8080`.

## Optional Model Setup

The app works without a model key by using deterministic logic and templates where possible.

For local models, start an OpenAI-compatible server and set:

```powershell
$env:LM_STUDIO_BASE_URL="http://localhost:1234/v1"
$env:LM_STUDIO_MODEL="local-model"
```

For hosted experiments, open Settings in the UI, choose a provider, choose or type a model ID, paste that provider's key, and save. Supported provider families are:

- Local/OpenAI-compatible: `local-model` or the model served by LM Studio/Ollama
- HuggingFace (free tier): `meta-llama/Llama-3.1-8B-Instruct`, `google/gemma-4-26B-A4B-it`, `deepseek-ai/DeepSeek-V4-Flash` — get a free token at huggingface.co/settings/tokens
- OpenAI: `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-4.1`
- Anthropic: `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5`
- Gemini: `gemini-3.5-flash`, `gemini-3.1-pro-preview`, `gemini-3-flash-preview`, `gemini-3.1-flash-lite`, `gemini-2.5-pro`, `gemini-2.5-flash`

Each reviewer should use their own keys. Real `.env` or `.secrets.json` files should never be committed.

## Useful Checks

Backend regression tests:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_regressions.py -q
```

Offline eval — candidate matching and CV extraction accuracy (no cloud account needed):

```powershell
.\venv\Scripts\python.exe tools\run_eval.py
```

Runs two suites against golden data and prints pass/fail per case plus an overall summary:
- **Suite 1 — Candidate Match Ranking**: verifies `score_structured` ranks the correct candidate #1 across 10 role/candidate scenarios. No LLM involved — pure algorithm.
- **Suite 2 — CV Extraction Accuracy**: scores seniority exact match, skill recall, and YOE tolerance across 10 golden CVs. Uses the active provider; falls back to heuristics if no key is set.

Run a single suite:

```powershell
.\venv\Scripts\python.exe tools\run_eval.py --suite matching
.\venv\Scripts\python.exe tools\run_eval.py --suite extraction
```

LangSmith eval (requires a free LangSmith account at smith.langchain.com):

```powershell
$env:LANGCHAIN_API_KEY="ls__..."
.\venv\Scripts\python.exe tools\langsmith_eval.py
```

Creates two datasets in LangSmith on first run and streams per-example traces for review.

UI type check and production build:

```powershell
cd .\ui
npm.cmd run lint
npm.cmd run build
```

If Windows reports a locked `ui/dist` file during build, stop any running UI server and retry.

## Project Map

- `web/app.py`: FastAPI API, config endpoints, assistant proposals, confirmation endpoint, static UI serving.
- `core/`: extraction, matching, maintenance, review, outreach, compliance, security, and provider routing.
- `ui/src/`: React application.
- `tests/`: regression tests for security and logic behavior.
- `tools/`: evaluation and helper CLIs.
- `data/`: local runtime records and logs, ignored by git.
- `_reference/`: local challenge/reference documents, ignored by git.

