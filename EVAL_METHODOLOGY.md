# Evaluation Methodology

Linnify's brief requires *"a set of clearly defined metrics to test accuracy... from the beginning of the project"* with an example target of **80 % matching accuracy**. This document describes how we measure each capability, the targets we hold ourselves to, and how to reproduce the numbers.

## TL;DR — Run It

```bash
# With your Gemini key set in Settings (or via GEMINI_API_KEY env)
python -m core.eval.run_eval

# Without an API key (LLM-as-judge skipped, local checks only)
python -m core.eval.run_eval --no-llm
```

Exit code `0` if both modules pass their targets, `1` otherwise. JSON report on stdout.

## What We Measure

The brief defines four modules. Each gets its own metric — chosen so that "good" means the same thing as a recruiter would mean.

| Module                       | Metric                                   | Target | Status     |
| ---------------------------- | ---------------------------------------- | ------ | ---------- |
| 1. CV / LinkedIn extraction  | Per-field accuracy (avg across 10 CVs)   | ≥ 0.85 | Automated  |
| 2. Talent-pool maintenance   | Refresh staleness coverage               | ≥ 0.95 | Manual     |
| 3. Shortlisting              | Top-1 hit rate (10 job/candidate cases)  | ≥ 0.80 | Automated  |
| 4. Outreach drafts           | Personalisation + tone (LLM-as-judge)    | ≥ 0.75 | Spec-only  |

"Automated" = covered by `python -m core.eval.run_eval`.
"Manual" / "Spec-only" = methodology defined here, no harness yet.

---

## 1. CV Extraction Accuracy

**Code**: `core/eval/eval_extraction.py`
**Golden set**: 10 hand-authored CVs in `core/eval/golden_data.GOLDEN_EXTRACTIONS`, spanning intern → principal, 9 industries, EU and non-EU candidates.

**Scoring per field:**
- `seniority`: case-insensitive substring match against expected label.
- `technologies_used`: fraction of expected skills present in extracted list (recall-weighted — extracting *extra* skills is not penalised, missing them is).
- `years_of_experience`: within ±1 year tolerance.
- Other fields (when added): LangChain `criteria=correctness` LLM-as-judge when a Gemini key is configured; otherwise exact string match.

**Aggregate**: mean of per-case-per-field scores. Threshold **0.85** = roughly "one missed field per CV is acceptable, two is not".

**LLM mode toggle**: `--no-llm` restricts evaluation to `seniority` and `technologies_used` (the fields the local regex extractor handles deterministically). Useful in CI without API quota.

---

## 2. Talent-pool Maintenance

The brief specifies bulk refresh + "auto-update profiles untouched in 6 months". Hard to automate without a real LinkedIn ToS-compliant data source, so the metric here is **operational**, not LLM-quality:

**Metric**: refresh-staleness coverage = `1 - (count of records with last_refreshed_at older than STALE_REFRESH_MONTHS / total active records)`.
**Target**: ≥ 0.95 after a scheduled run of `tools/retention_cli.py` (when implemented as a daily job).
**Sources**: `core.maintenance.find_stale_candidates`, `core.maintenance.bulk_refresh`.
**How to verify in demo**: ingest a CV, manually backdate `state.last_refreshed_at` in `records/<id>.json` by 7 months, call `/api/maintenance/bulk-refresh`, confirm the record is updated and its event log contains a `bulk_refresh_update` entry.

---

## 3. Shortlisting Accuracy

**Code**: `core/eval/eval_matching.py`
**Golden set**: 10 job/candidate scenarios in `GOLDEN_MATCHES`. Each is a requirement + 2–3 candidates with a designated "correct winner".

**Metric**: top-1 hit rate — does the candidate ranked #1 by our scoring pipeline equal the expected winner?
**Target**: ≥ 0.80 (matches the brief's stated example: *"80 % accuracy matching candidates to roles"*).

**Pipeline scored**: `score_keywords` × `_scoring_weights["skills"]` + structured signals (experience, location, language, freshness). The full production path *also* runs an embedding rerank + LLM rerank on top of this; the eval intentionally measures the deterministic substrate so the score is reproducible without API quota. To evaluate the full LLM rerank quality, run `generate_shortlist` against the same golden set and compare top-1 to `expected_winner_index`.

**Why top-1 and not NDCG**: a recruiter scanning a shortlist looks at the top few. Getting #1 wrong is more painful than ordering #4 vs #5 wrong. We accept the simplicity loss.

---

## 4. Outreach Draft Quality (spec-only)

Drafts pass through human review (`/api/review/outreach`) before sending, so the bar is "good enough that a human approves with minimal edits", not "ready to send unedited".

**Proposed metric** (not yet automated):
- Sample 20 drafts produced by `core.outreach.generate_draft` against held-out (candidate, job) pairs.
- LLM-as-judge (LangChain `criteria` evaluator) rates each on three axes 0–1:
  - **Personalisation** — does the draft reference a specific skill/project from the candidate?
  - **Tone** — professional, not over-familiar?
  - **Faithfulness** — no fabricated facts about the candidate or company?
- Pass: each axis ≥ 0.75 averaged across the sample.

**Bias against own model**: when budget permits, run the judge with a *different* model from the one that generated the draft to reduce same-family bias.

---

## What's *Not* in Scope for Metrics

- **PII redaction correctness**: covered by unit tests in `tests/test_regressions.py`, not the eval harness — it's binary (a leak is a bug, not a percentage).
- **Compliance rule precision/recall**: same — `core.compliance.evaluate_compliance` is rule-driven, tested by enumeration.
- **End-to-end latency**: tracked operationally (request logs), not as an accuracy metric.

---

## Reproducibility Notes

- The golden sets are deterministic Python dicts — no flaky CSV parsing, no network calls.
- LLM-mode scores will fluctuate ±2 % between runs; threshold has 5 % headroom.
- When a Gemini key is configured via Settings → API Key, the runner picks it up automatically (`core.config.get_active_api_key()`).
- Last known-good scores on the maintained dev branch (record these per release):
  - CV extraction (no-LLM): **0.92** ✓
  - Shortlisting top-1: **0.90** ✓
  - CV extraction (LLM mode): TBD — re-run after API key is plumbed end-to-end.
