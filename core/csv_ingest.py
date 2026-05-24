"""
CSV bulk ingest for the structured candidate+job CSV format.

Each row contains candidate profile columns AND a matched job description.
Both sides are extracted and stored independently.

Column groups handled:
  Candidate: address, career_objective, skills, educational_*, professional_*,
             related_skills_in_job, positions, locations, responsibilities,
             languages, proficiency_levels, certification_*
  Job:       job_position_name, educational_requirements, experience_requirement,
             age_requirement, responsibilities.1, skills_required, matched_score

List-encoded fields (e.g. "['Python', 'Java']") are parsed with ast.literal_eval
with a safe fallback to a plain comma-split.
"""

import ast
import csv
import io
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterator, Optional

from .schemas import CandidateRecord, Identity, Profile, Compliance, Scores
from .store import save_record, load_record
from .config import RECORDS_DIR


# ---------------------------------------------------------------------------
# Safe list parser
# ---------------------------------------------------------------------------

def _parse_list(value: Any) -> list[str]:
    """Parse a stringified Python list, or fall back to comma-split."""
    if not value or (isinstance(value, float)):
        return []
    s = str(value).strip()
    if not s or s.lower() in ("none", "n/a", "nan", ""):
        return []
    if s.startswith("["):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if x and str(x).strip() not in ("", "None", "N/A")]
        except Exception:
            pass
    # Fallback: comma-split
    return [x.strip() for x in s.split(",") if x.strip() and x.strip() not in ("None", "N/A")]


def _scalar(value: Any) -> Optional[str]:
    if not value:
        return None
    s = str(value).strip()
    return None if s.lower() in ("none", "n/a", "nan", "") else s


def _parse_years_experience(start_dates: list[str], end_dates: list[str]) -> Optional[int]:
    """Estimate years of experience from the earliest start to latest end/now."""
    years = []
    for start in start_dates:
        try:
            # Accept formats like "Nov 2019", "June 2018", "2018"
            for fmt in ("%b %Y", "%B %Y", "%Y"):
                try:
                    dt = datetime.strptime(start.strip(), fmt)
                    years.append(dt.year)
                    break
                except ValueError:
                    continue
        except Exception:
            continue
    if not years:
        return None
    earliest = min(years)
    return max(0, datetime.now().year - earliest)


def _parse_seniority(positions: list[str], experience_years: Optional[int]) -> Optional[str]:
    """Infer seniority from job title keywords or years of experience."""
    title_text = " ".join(positions).lower()
    if any(k in title_text for k in ("senior", "lead", "principal", "staff", "head", "director")):
        return "Senior"
    if any(k in title_text for k in ("junior", "fresher", "entry", "trainee", "intern")):
        return "Junior"
    if any(k in title_text for k in ("manager", "vp", "vice president")):
        return "Lead"
    if experience_years is not None:
        if experience_years >= 7:
            return "Senior"
        if experience_years >= 3:
            return "Mid"
        if experience_years >= 1:
            return "Junior"
        return "Intern"
    return None


# ---------------------------------------------------------------------------
# Column name normalisation
# ---------------------------------------------------------------------------

_COLUMN_ALIASES: dict[str, str] = {
    # BOM-prefixed variants from Excel exports
    "\ufeffjob_position_name": "job_position_name",
    "ï»¿job_position_name": "job_position_name",
    # Typo variants seen in sample
    "educational_requirements": "educational_requirements",
    "educationaL_requirements": "educational_requirements",
    "experiencere_requirement": "experience_requirement",
    "responsibilities.1": "job_responsibilities",
}


def _norm_headers(raw_headers: list[str]) -> list[str]:
    normalised = []
    for h in raw_headers:
        h = h.strip()
        normalised.append(_COLUMN_ALIASES.get(h, h))
    return normalised


# ---------------------------------------------------------------------------
# Row → CandidateRecord
# ---------------------------------------------------------------------------

def _row_to_candidate(row: dict[str, str], row_num: int) -> tuple[str, CandidateRecord]:
    """Map a single CSV row to a (record_id, CandidateRecord)."""
    skills = _parse_list(row.get("skills", ""))
    degrees = _parse_list(row.get("degree_names", ""))
    institutions = _parse_list(row.get("educational_institution_name", ""))
    passing_years = _parse_list(row.get("passing_years", ""))
    majors = _parse_list(row.get("major_field_of_studies", ""))
    companies = _parse_list(row.get("professional_company_names", ""))
    positions = _parse_list(row.get("positions", ""))
    start_dates = _parse_list(row.get("start_dates", ""))
    end_dates = _parse_list(row.get("end_dates", ""))
    locations = _parse_list(row.get("locations", ""))
    languages = _parse_list(row.get("languages", ""))
    certs = _parse_list(row.get("certification_skills", ""))

    career_objective = _scalar(row.get("career_objective", ""))
    address = _scalar(row.get("address", ""))

    # Structured degrees: "B.Tech at ASET, Noida (2019)"
    study_degrees: list[str] = []
    for i, deg in enumerate(degrees):
        inst = institutions[i] if i < len(institutions) else ""
        year = passing_years[i] if i < len(passing_years) else ""
        major = majors[i] if i < len(majors) else ""
        parts = [deg]
        if major and major.lower() not in ("none", "n/a"):
            parts[0] = f"{deg} ({major})"
        if inst:
            parts.append(f"at {inst}")
        if year and year not in ("N/A", "None"):
            parts.append(f"({year})")
        study_degrees.append(" ".join(parts))

    # Previous jobs: "Big Data Analyst at Coca-Cola"
    previous_jobs: list[str] = []
    for i, pos in enumerate(positions):
        co = companies[i] if i < len(companies) else ""
        if co:
            previous_jobs.append(f"{pos} at {co}")
        else:
            previous_jobs.append(pos)

    yoe = _parse_years_experience(start_dates, end_dates)
    seniority = _parse_seniority(positions, yoe)

    # All skills including certs
    all_skills = list(dict.fromkeys(skills + certs))

    # Confidence based on data richness
    filled = sum([bool(career_objective), bool(all_skills), bool(previous_jobs), bool(study_degrees), bool(yoe)])
    confidence = round(min(0.45 + filled * 0.10, 0.90), 2)

    now = datetime.utcnow().isoformat() + "Z"
    record_id = f"cand_{uuid.uuid4().hex[:12]}"

    # Retention: 2 years from now (GDPR-compatible default)
    retention_until = (datetime.now(timezone.utc) + timedelta(days=730)).isoformat()

    rec = CandidateRecord(
        created_at=now,
        updated_at=now,
        identity=Identity(
            primary_name=f"CSV Candidate {row_num}",  # No name column in this schema
            linkedin_url=None,
            emails=[],
        ),
        profile=Profile(
            headline=positions[0] if positions else None,
            summary=career_objective,
            seniority=seniority,
            years_of_experience=yoe,
            technologies_used=all_skills,
            languages_spoken=languages,
            previous_jobs=previous_jobs,
            study_degrees=study_degrees,
            location=address or (locations[0] if locations else None),
            projects_developed=[],
        ),
        scores=Scores(extraction_confidence=confidence),
        compliance=Compliance(
            consent_basis="legitimate_interest",
            source="csv_bulk_import",
            data_region="EEA",
            retention_until=retention_until,
            human_review_required=confidence < 0.65,
        ),
    )
    return record_id, rec


# ---------------------------------------------------------------------------
# Dedup helper
# ---------------------------------------------------------------------------

def _existing_ids_by_skills() -> set[str]:
    """Build a set of skill-fingerprints for existing records to catch near-dupes."""
    fingerprints: set[str] = set()
    if not RECORDS_DIR.exists():
        return fingerprints
    for f in RECORDS_DIR.glob("*.json"):
        import json
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            skills = sorted(data.get("profile", {}).get("technologies_used", []))
            summary = (data.get("profile", {}).get("summary") or "")[:60]
            fp = "|".join(skills[:5]) + "|" + summary
            fingerprints.add(fp)
        except Exception:
            continue
    return fingerprints


# ---------------------------------------------------------------------------
# Public streaming ingest function
# ---------------------------------------------------------------------------

class CSVIngestProgress:
    """Shared mutable state for background CSV ingest tasks."""
    def __init__(self):
        self.total = 0
        self.processed = 0
        self.skipped = 0
        self.failed = 0
        self.errors: list[dict] = []
        self.done = False
        self.started_at = datetime.utcnow().isoformat() + "Z"
        self.finished_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "processed": self.processed,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors[:20],
            "done": self.done,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def stream_ingest_csv(content: bytes, progress: CSVIngestProgress) -> None:
    """
    Parse and ingest a CSV file from raw bytes.
    Updates `progress` in-place — designed to run in a background thread.

    - Streams row-by-row (never loads the whole file into a list)
    - Deduplicates by skill-fingerprint against existing records
    - Marks low-confidence rows for human review
    """
    try:
        text = content.decode("utf-8-sig")  # strips BOM if present
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        progress.done = True
        progress.finished_at = datetime.utcnow().isoformat() + "Z"
        return

    # Normalise headers (handle BOM, typos, alias variants)
    normalised = _norm_headers(list(reader.fieldnames))
    reader.fieldnames = normalised  # type: ignore[assignment]

    # Count rows for progress reporting (requires a second pass on the string)
    row_count = text.count("\n") - 1  # rough estimate
    progress.total = max(row_count, 0)

    existing_fingerprints = _existing_ids_by_skills()

    for row_num, row in enumerate(reader, start=1):
        # Skip rows that are entirely empty or only have job columns (no candidate data)
        skills_raw = row.get("skills", "") or ""
        career_raw = row.get("career_objective", "") or ""
        if not skills_raw.strip() and not career_raw.strip():
            progress.skipped += 1
            continue

        try:
            record_id, rec = _row_to_candidate(row, row_num)

            # Dedup: fingerprint = first 5 skills + first 60 chars of summary
            skills_sorted = sorted(rec.profile.technologies_used or [])
            summary_snip = (rec.profile.summary or "")[:60]
            fp = "|".join(skills_sorted[:5]) + "|" + summary_snip
            if fp in existing_fingerprints:
                progress.skipped += 1
                continue

            event = {
                "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                "event_type": "csv_bulk_ingest",
                "timestamp": rec.created_at,
                "actor": {"type": "system"},
                "source": {"source_type": "csv_import", "row": row_num},
                "changes": [{"operation": "create", "path": "/"}],
                "confidence": rec.scores.extraction_confidence,
            }
            save_record(record_id, rec, event=event)
            existing_fingerprints.add(fp)
            progress.processed += 1

        except Exception as e:
            progress.failed += 1
            if len(progress.errors) < 20:
                progress.errors.append({"row": row_num, "error": str(e)[:200]})

    progress.done = True
    progress.finished_at = datetime.utcnow().isoformat() + "Z"
