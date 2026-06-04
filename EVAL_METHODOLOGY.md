# Evaluation Methodology

The Linnify brief asks for clearly defined metrics from the beginning of the project, including an example target of 80% matching accuracy. This document defines the metrics, thresholds, and commands used to evaluate the AI Talent Pool Manager.

## Quick Run

```powershell
# Security and logic regression suite
.\venv\Scripts\python.exe -m pytest tests\test_regressions.py -q

# Primary candidate-role matching KPI
.\venv\Scripts\python.exe -m tools.eval_candidates

# Offline extraction/ranking harness
.\venv\Scripts\python.exe -m core.eval.run_eval --no-llm
```

Use `core.eval.run_eval` without `--no-llm` only after configuring a local model or a hosted provider key. Hosted providers are optional and must be supplied by the local user; no key is committed to the repository.

## Metrics

| Module | Metric | Target | Status |
| --- | --- | --- | --- |
| CV / LinkedIn extraction | Per-field accuracy across golden CVs | >= 0.85 | Automated |
| Talent-pool maintenance | Stale-profile coverage after refresh workflow | >= 0.95 | Logic tested plus demo workflow |
| Candidate-role matching | Exact label accuracy on CSV eval set | >= 0.80 | Automated |
| Outreach drafts | Personalization, tone, and faithfulness | >= 0.75 | Human review plus optional judge |
| Security / compliance | No direct PII in unsafe paths; no unconfirmed agent writes | 0 known leaks | Regression tested |

## 1. CV Extraction Accuracy

Code:

- `core/eval/eval_extraction.py`
- `core/eval/golden_data.py`
- `core/extract.py`

Golden set:

- Hand-authored CV examples covering multiple seniorities, industries, and geographies.

Scoring:

- `seniority`: case-insensitive substring match against the expected label.
- `technologies_used`: recall of expected skills in the extracted list.
- `years_of_experience`: within +/- 1 year tolerance.
- Other fields: exact string match offline, or optional configured-provider LLM-as-judge when explicitly enabled.

Default demo command:

```powershell
.\venv\Scripts\python.exe -m core.eval.run_eval --no-llm
```

The `--no-llm` path is deterministic and suitable for handoff. Optional LLM-as-judge scoring routes through `core.llm.complete`, so it can use local, OpenAI, Anthropic, or Gemini settings when configured by the user.

## 2. Talent-Pool Maintenance

Code:

- `core/maintenance.py`
- `web/app.py` maintenance endpoints
- `tests/test_regressions.py`

Metric:

```text
refresh_staleness_coverage =
1 - stale_active_records_after_refresh / total_active_records
```

Target:

```text
>= 0.95
```

Demo workflow:

1. Ingest a candidate.
2. Backdate `state.last_refreshed_at` by more than 6 months in the local data record.
3. Run `/api/maintenance/stale`.
4. Confirm the stale record appears.
5. Run `/api/maintenance/bulk-refresh` for that record.
6. Confirm the record has updated refresh metadata and an audit event.

LinkedIn refresh does not scrape LinkedIn. It uses user-provided URLs/text/profile data or marks a candidate for manual review.

## 3. Candidate-Role Matching Accuracy

Code:

- `tools/eval_candidates.py`
- `core/candidate_role_eval.py`
- `tests/data/candidate_role_eval.csv`

Task:

Given a free-text candidate profile and a free-text role description, predict whether the candidate is a fit.

Metric:

```text
accuracy = correct labels / total examples
```

Label space:

```text
match, no_match
```

Target:

```text
>= 0.80
```

Run:

```powershell
.\venv\Scripts\python.exe -m tools.eval_candidates
```

The primary KPI is deterministic and offline. It uses local skill, seniority, and experience signals rather than a hosted model, which makes the result repeatable for demos and CI.

## 4. Outreach Draft Quality

Code:

- `core/outreach.py`
- `core/review.py`
- `web/app.py` review/outreach endpoints

Operational target:

Drafts should be specific enough for a reviewer to approve with minimal edits, while staying faithful to known candidate and job data.

Scoring dimensions:

- Personalization: references relevant candidate evidence.
- Tone: professional and appropriate for recruiting.
- Faithfulness: no fabricated candidate facts, company promises, or external claims.

Target:

```text
average score per dimension >= 0.75
```

The application does not send outreach. Drafts are inserted into the review queue and must be approved by a human outside this app before any communication happens.

## 5. Security And Agent Regression

Code:

- `web/app.py`
- `core/security.py`
- `tests/test_regressions.py`

Required behavior:

- Candidate-aware assistant prompts do not call hosted providers in the Linnify action path.
- Assistant responses return typed `proposals`, `actions`, and `errors`.
- Confirmed writes happen only through `POST /api/agent/actions/{proposal_id}/confirm`.
- Proposed and confirmed actions create audit events.
- Candidate refresh uses provided data or stale flags, not external scraping.
- Outreach drafts are generated locally/template-first for the confirmed assistant path and are not sent.
- Secrets stay outside git in `.secrets.json` or local environment variables.

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_regressions.py -q
```

## Release Checklist

Before sending the repository link:

1. Run backend regressions.
2. Run the candidate-role eval.
3. Run UI lint/build.
4. Run a secret scan for common key patterns.
5. Confirm `git status` does not include local secrets, local data, `node_modules`, virtual environments, or browser/build caches.

