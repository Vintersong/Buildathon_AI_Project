"""Quick end-to-end smoke test for CSV and Excel import paths."""
import io, json, tempfile
from pathlib import Path
from unittest.mock import patch
from core import csv_ingest, store
from core.csv_ingest import CSVIngestProgress, stream_ingest_file

# ── Test 1: plain CSV ──────────────────────────────────────────────────────────
csv_content = (
    "candidate_name,email,skills,career_objective,job_position_name,skills_required\r\n"
    "Ada Lovelace,ada@test.com,\"['Python', 'FastAPI']\",Builds APIs.,Python Engineer,\"['Python']\"\r\n"
    "Grace Hopper,grace@test.com,\"['COBOL']\",Systems engineer.,,\r\n"
).encode("utf-8")

with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    records = base / "records"; records.mkdir()
    indexes = base / "indexes"; indexes.mkdir()
    requirements = base / "requirements"; requirements.mkdir()
    (indexes / "record_index.json").write_text("{}", encoding="utf-8")

    with patch.object(store, "RECORDS_DIR", records), \
         patch.object(store, "RECORD_INDEX_PATH", indexes / "record_index.json"), \
         patch.object(store, "log_event"), \
         patch.object(csv_ingest, "RECORDS_DIR", records), \
         patch.object(csv_ingest, "REQUIREMENTS_DIR", requirements), \
         patch.object(csv_ingest, "check_and_generate_review_cases", return_value=[]):
        prog = CSVIngestProgress()
        stream_ingest_file(csv_content, "test.csv", prog)

    print("=== CSV plain-text ===")
    print(f"  rows_seen:    {prog.rows_seen}")
    print(f"  processed:    {prog.processed}")
    print(f"  jobs_created: {prog.jobs_created}")
    print(f"  failed:       {prog.failed}")
    print(f"  done:         {prog.done}")
    if prog.errors:
        print(f"  errors:       {prog.errors}")
    cand_files = list(records.glob("*.json"))
    print(f"  records saved:{len(cand_files)}")
    print(f"  jobs saved:   {len(list(requirements.glob('*.json')))}")
    if cand_files:
        sample = json.loads(cand_files[0].read_text(encoding="utf-8"))
        print(f"  sample name:  {sample['identity']['primary_name']}")
        print(f"  sample skills:{sample['profile']['technologies_used']}")

# ── Test 2: bad schema ─────────────────────────────────────────────────────────
bad_csv = b"foo;bar\nx;y\n"
prog2 = CSVIngestProgress()
stream_ingest_file(bad_csv, "bad.csv", prog2)
print("\n=== Bad CSV (unknown schema) ===")
print(f"  done:    {prog2.done}")
print(f"  failed:  {prog2.failed}")
print(f"  error:   {prog2.errors[0]['error'] if prog2.errors else 'none'}")

# ── Test 3: Excel ──────────────────────────────────────────────────────────────
from openpyxl import Workbook
wb = Workbook(); ws = wb.active
ws.append(["candidate_name","email","skills","career_objective","job_position_name","skills_required","responsibilities.1"])
ws.append(["Alan Turing","alan@test.com","['Python','ML']","Computes.","ML Engineer","['Python']","Build models."])
payload = io.BytesIO(); wb.save(payload)

with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    records = base / "records"; records.mkdir()
    indexes = base / "indexes"; indexes.mkdir()
    requirements = base / "requirements"; requirements.mkdir()
    (indexes / "record_index.json").write_text("{}", encoding="utf-8")

    with patch.object(store, "RECORDS_DIR", records), \
         patch.object(store, "RECORD_INDEX_PATH", indexes / "record_index.json"), \
         patch.object(store, "log_event"), \
         patch.object(csv_ingest, "RECORDS_DIR", records), \
         patch.object(csv_ingest, "REQUIREMENTS_DIR", requirements), \
         patch.object(csv_ingest, "check_and_generate_review_cases", return_value=[]):
        prog3 = CSVIngestProgress()
        stream_ingest_file(payload.getvalue(), "bulk.xlsx", prog3)

    print("\n=== Excel (.xlsx) ===")
    print(f"  rows_seen:    {prog3.rows_seen}")
    print(f"  processed:    {prog3.processed}")
    print(f"  jobs_created: {prog3.jobs_created}")
    print(f"  failed:       {prog3.failed}")
    print(f"  done:         {prog3.done}")
    if prog3.errors:
        print(f"  errors:       {prog3.errors}")
    cand_files = list(records.glob("*.json"))
    if cand_files:
        sample = json.loads(cand_files[0].read_text(encoding="utf-8"))
        print(f"  sample name:  {sample['identity']['primary_name']}")
        print(f"  sample skills:{sample['profile']['technologies_used']}")

# ── Test 4: real intake CSV ────────────────────────────────────────────────────
real_csv = Path("intake/resume_data.csv")
if real_csv.exists():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        records = base / "records"; records.mkdir()
        indexes = base / "indexes"; indexes.mkdir()
        requirements = base / "requirements"; requirements.mkdir()
        (indexes / "record_index.json").write_text("{}", encoding="utf-8")

        with patch.object(store, "RECORDS_DIR", records), \
             patch.object(store, "RECORD_INDEX_PATH", indexes / "record_index.json"), \
             patch.object(store, "log_event"), \
             patch.object(csv_ingest, "RECORDS_DIR", records), \
             patch.object(csv_ingest, "REQUIREMENTS_DIR", requirements), \
             patch.object(csv_ingest, "check_and_generate_review_cases", return_value=[]):
            prog4 = CSVIngestProgress()
            stream_ingest_file(real_csv.read_bytes(), real_csv.name, prog4)

        print(f"\n=== Real intake/resume_data.csv ===")
        print(f"  rows_seen:    {prog4.rows_seen}")
        print(f"  processed:    {prog4.processed}")
        print(f"  jobs_created: {prog4.jobs_created}")
        print(f"  failed:       {prog4.failed}")
        print(f"  done:         {prog4.done}")
        if prog4.errors:
            for e in prog4.errors[:3]:
                print(f"  error:        {e}")
else:
    print("\n(intake/resume_data.csv not found - skipped)")

print("\nAll CSV import tests done.")
