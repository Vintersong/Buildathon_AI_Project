"""
Offline evaluation harness for Bloodhound.

Runs both eval suites against the golden dataset — no LangSmith account,
no cloud service, no API key required (extraction falls back to heuristics
when no provider key is configured).

Usage:
    python tools/run_eval.py               # run all suites
    python tools/run_eval.py --suite matching
    python tools/run_eval.py --suite extraction
"""

import sys
import argparse
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.eval.golden_data import GOLDEN_EXTRACTIONS, GOLDEN_MATCHES
from core.schemas import (
    CandidateRecord,
    Profile,
    RequirementRecord,
    RequirementCriteria,
)

_DUMMY_TS = "2024-01-01T00:00:00+00:00"

# ---------------------------------------------------------------------------
# Helpers shared with langsmith_eval.py
# ---------------------------------------------------------------------------

def _record_from_golden_candidate(c: dict) -> CandidateRecord:
    return CandidateRecord(
        created_at=_DUMMY_TS,
        updated_at=_DUMMY_TS,
        profile=Profile(
            seniority=c.get("seniority"),
            technologies_used=c.get("skills", []),
            years_of_experience=c.get("experience"),
            location=c.get("location"),
        ),
    )


def _req_from_golden(r: dict) -> RequirementRecord:
    return RequirementRecord(
        id=r["id"],
        title=r["title"],
        created_at=_DUMMY_TS,
        updated_at=_DUMMY_TS,
        requirements=RequirementCriteria(
            must_have=r.get("must_have", []),
            nice_to_have=r.get("nice_to_have", []),
            location=r.get("location"),
        ),
    )


# ---------------------------------------------------------------------------
# Matching suite  (no LLM — pure scoring algorithm)
# ---------------------------------------------------------------------------

def run_matching_suite() -> dict:
    from core.match import score_structured

    print("\n" + "=" * 60)
    print("  SUITE 1: Candidate Match Ranking  (score_structured)")
    print("=" * 60)

    passed = 0
    total = len(GOLDEN_MATCHES)

    for case in GOLDEN_MATCHES:
        req_record = _req_from_golden(case["requirement"])
        candidates = case["candidates"]
        winner_idx = case["expected_winner_index"]
        expected_id = candidates[winner_idx]["id"]

        scored = []
        for c in candidates:
            record = _record_from_golden_candidate(c)
            score = score_structured(record, req_record, {})
            scored.append({"id": c["id"], "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        top_id = scored[0]["id"]
        ok = top_id == expected_id

        if ok:
            passed += 1

        status = "PASS" if ok else "FAIL"
        desc = case["description"]
        scores_str = "  ".join(f"{s['id']}={s['score']:.3f}" for s in scored)
        print(f"  [{status}]  {desc}")
        if not ok:
            print(f"         expected={expected_id}  got={top_id}  scores: {scores_str}")

    accuracy = passed / total
    overall = "PASS" if accuracy >= 0.8 else "FAIL"
    print(f"\n  Result: {passed}/{total} correct  ({accuracy:.0%})  [{overall}]")
    return {"passed": passed, "total": total, "accuracy": accuracy}


# ---------------------------------------------------------------------------
# Extraction suite  (uses active LLM or heuristic fallback)
# ---------------------------------------------------------------------------

def run_extraction_suite() -> dict:
    from core.extract import extract_candidate_data

    print("\n" + "=" * 60)
    print("  SUITE 2: CV Extraction Accuracy  (extract_candidate_data)")
    print("=" * 60)

    sen_pass = yoe_pass = 0
    skill_scores: list[float] = []
    total = len(GOLDEN_EXTRACTIONS)
    errors = 0

    for case in GOLDEN_EXTRACTIONS:
        expected = case["expected"]
        cv_snippet = case["cv_text"].split("\n")[0]  # first line = name for display

        try:
            extraction, _ = extract_candidate_data(case["cv_text"])
        except Exception as e:
            print(f"  [ERROR]  {cv_snippet!r}  —  {e}")
            errors += 1
            total -= 1
            continue

        # Seniority
        pred_sen = (extraction.seniority or "").strip()
        exp_sen = (expected.get("seniority") or "").strip()
        sen_ok = pred_sen == exp_sen

        # Skill recall
        pred_skills = set(s.lower() for s in (extraction.technologies_used or []))
        exp_skills = set(s.lower() for s in (expected.get("technologies_used") or []))
        recall = len(pred_skills & exp_skills) / len(exp_skills) if exp_skills else 1.0
        skill_scores.append(recall)

        # YOE ±1
        pred_yoe = extraction.years_of_experience
        exp_yoe = expected.get("years_of_experience")
        yoe_ok = (
            pred_yoe is not None
            and exp_yoe is not None
            and abs(pred_yoe - exp_yoe) <= 1
        )

        if sen_ok:
            sen_pass += 1
        if yoe_ok:
            yoe_pass += 1

        missing_skills = exp_skills - pred_skills
        issues = []
        if not sen_ok:
            issues.append(f"seniority: expected={exp_sen!r} got={pred_sen!r}")
        if not yoe_ok:
            issues.append(f"yoe: expected={exp_yoe} got={pred_yoe}")
        if missing_skills:
            issues.append(f"missing skills: {', '.join(sorted(missing_skills))}")

        status = "PASS" if sen_ok and yoe_ok and recall >= 0.8 else "FAIL"
        print(f"  [{status}]  {cv_snippet}")
        if issues:
            for issue in issues:
                print(f"         {issue}")

    if total == 0:
        print("  (No cases ran — all errored)")
        return {"passed": 0, "total": 0, "accuracy": 0.0}

    sen_acc = sen_pass / total
    yoe_acc = yoe_pass / total
    skill_avg = sum(skill_scores) / len(skill_scores) if skill_scores else 0.0

    print(f"\n  seniority_exact:  {sen_pass}/{total}  ({sen_acc:.0%})  "
          f"[{'PASS' if sen_acc >= 0.8 else 'FAIL'}]")
    print(f"  skill_recall avg: {skill_avg:.0%}          "
          f"[{'PASS' if skill_avg >= 0.8 else 'FAIL'}]")
    print(f"  yoe_within_1yr:   {yoe_pass}/{total}  ({yoe_acc:.0%})  "
          f"[{'PASS' if yoe_acc >= 0.8 else 'FAIL'}]")

    combined = (sen_acc + skill_avg + yoe_acc) / 3
    return {"seniority": sen_acc, "skill_recall": skill_avg, "yoe": yoe_acc, "combined": combined}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Offline eval harness for Bloodhound")
    parser.add_argument(
        "--suite",
        choices=["matching", "extraction", "all"],
        default="all",
    )
    args = parser.parse_args()

    match_result = extract_result = None

    if args.suite in ("matching", "all"):
        match_result = run_matching_suite()

    if args.suite in ("extraction", "all"):
        extract_result = run_extraction_suite()

    # Overall banner
    print("\n" + "=" * 60)
    print("  OVERALL")
    print("=" * 60)

    if match_result:
        acc = match_result["accuracy"]
        print(f"  Matching accuracy:    {acc:.0%}  [{'PASS' if acc >= 0.8 else 'FAIL'}]")

    if extract_result:
        c = extract_result.get("combined", 0.0)
        print(f"  Extraction combined:  {c:.0%}  [{'PASS' if c >= 0.8 else 'FAIL'}]")

    all_pass = all([
        (match_result is None or match_result["accuracy"] >= 0.8),
        (extract_result is None or extract_result.get("combined", 0.0) >= 0.8),
    ])
    print(f"\n  {'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")
    print("=" * 60)

    sys.exit(0 if all_pass else 1)
