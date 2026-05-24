# Linnify AI Talent Pool Manager UI

React frontend for the Linnify challenge implementation. The UI talks to the FastAPI backend for candidate extraction, talent pool maintenance, job shortlisting, outreach drafts, review queue actions, audit events, and LM Studio/Gemma configuration.

## Local Run

1. Install dependencies:

   ```bash
   npm install
   ```

2. Start the FastAPI backend from the repository root.

3. Start the UI proxy:

   ```bash
   npm run dev
   ```

The proxy serves the React app and forwards `/api/*` calls to `FASTAPI_URL` when set, or `http://127.0.0.1:8080` by default.

## Configuration

- Prefer LM Studio with Gemma for local LLM search and drafting by enabling local routing in Settings.
- External Gemini usage requires a key saved through the Settings screen or backend secrets file.
- LinkedIn workflows use provided URLs or pasted profile text only. The app does not scrape LinkedIn.
