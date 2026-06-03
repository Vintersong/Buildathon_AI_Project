import json
import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.schemas import CandidateExtraction, CandidateRecord, Compliance, Identity, Profile, Scores, State, RequirementRecord, RequirementCriteria


def make_record(**kwargs):
    record = CandidateRecord(
        created_at="2026-05-23T00:00:00Z",
        updated_at="2026-05-23T00:00:00Z",
        identity=Identity(primary_name="Ada Lovelace"),
        profile=Profile(
            seniority="Senior",
            years_of_experience=6,
            technologies_used=["Python"],
            languages_spoken=["English"],
            location="Remote",
        ),
        state=State(status="new"),
        compliance=Compliance(consent_basis="candidate_consent", source="document", retention_until="2099-01-01T00:00:00Z"),
        scores=Scores(extraction_confidence=0.9),
    )
    for key, value in kwargs.items():
        setattr(record, key, value)
    return record


def make_extraction(**overrides):
    data = {
        "name": "Ada Lovelace",
        "emails": ["ada@example.com"],
        "phones": [],
        "linkedin_url": None,
        "seniority": "Senior",
        "years_of_experience": 6,
        "study_degrees": ["Master"],
        "technologies_used": ["Python"],
        "languages_spoken": ["English"],
        "location": "Remote",
        "previous_jobs": ["ML Engineer - Example"],
        "projects_developed": ["Built ML platform"],
        "summary": "Senior ML engineer.",
        "extraction_confidence": 0.9,
        "review_flags": [],
    }
    data.update(overrides)
    return CandidateExtraction(**data)


class CaptureLLM:
    """Stand-in for core.llm.complete that records the messages it receives."""

    def __init__(self, response_text):
        self.response_text = response_text
        self.calls = []

    def __call__(self, messages, **kwargs):
        self.calls.append(messages)
        return self.response_text

    @property
    def last_prompt(self) -> str:
        return "\n".join(m["content"] for m in self.calls[-1])


def _write_jsonl(path: Path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


class RegressionTests(unittest.TestCase):
    def test_quarantine_extraction_failures_are_redacted(self):
        from core import extract

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with patch.object(extract, "QUARANTINE_DIR", tmp_path):
                extract._quarantine_failed_extraction(
                    "Ada Lovelace\nContact ada@example.com\nCall +40 722 111 222",
                    "json_decode_error",
                )
                files = list((tmp_path / "extraction_failures").glob("*.txt"))
                self.assertEqual(len(files), 1)
                body = files[0].read_text(encoding="utf-8")
                self.assertNotIn("ada@example.com", body)
                self.assertNotIn("+40 722 111 222", body)
                self.assertNotIn("Ada Lovelace", body)
                self.assertIn("json_decode_error", body)

    def test_save_record_persists_provenance_and_index(self):
        from core import store

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            records = base / "records"
            indexes = base / "indexes"
            records.mkdir()
            indexes.mkdir()
            with patch.object(store, "RECORDS_DIR", records), patch.object(store, "RECORD_INDEX_PATH", indexes / "record_index.json"):
                (indexes / "record_index.json").write_text("{}")
                record = make_record()
                event = {"event_id": "evt_test", "event_type": "test", "timestamp": "2026-05-23T00:00:00Z", "source": {}, "actor": {}}
                store.save_record("cand_test", record, event=event)
                saved = store.load_record("cand_test")
                self.assertEqual(saved.provenance[0]["event_id"], "evt_test")
                index = json.loads((indexes / "record_index.json").read_text())
                self.assertIn("cand_test", index)

    def test_candidate_api_recovers_records_missing_from_index(self):
        from core import store
        from web import app as web_app

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            records = base / "records"
            indexes = base / "indexes"
            records.mkdir()
            indexes.mkdir()
            (indexes / "record_index.json").write_text("{}")
            (records / "cand_unindexed.json").write_text(make_record().model_dump_json(indent=2), encoding="utf-8")

            with patch.object(web_app, "RECORDS_DIR", records), \
                patch.object(web_app, "RECORD_INDEX_PATH", indexes / "record_index.json"), \
                patch.object(store, "RECORDS_DIR", records):
                candidates = asyncio.run(web_app.list_candidates())

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["id"], "cand_unindexed")

    def test_review_resolve_approved_only_resolves_target_case(self):
        from core import review, store

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            records = base / "records"
            indexes = base / "indexes"
            logs = base / "logs"
            records.mkdir()
            indexes.mkdir()
            logs.mkdir()
            (indexes / "record_index.json").write_text("{}")
            queue_path = logs / "review_queue.jsonl"
            _write_jsonl(queue_path, [
                {"case_id": "case_a", "record_id": "cand_test", "reason": "missing_consent", "status": "open"},
                {"case_id": "case_b", "record_id": "cand_test", "reason": "low_extraction_confidence", "status": "open"},
            ])
            record = make_record(
                state=State(status="pending_review"),
                compliance=Compliance(consent_basis=None, source="document", retention_until="2099-01-01T00:00:00Z", human_review_required=True),
            )
            (records / "cand_test.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")

            with patch.object(review, "REVIEW_QUEUE_PATH", queue_path), \
                patch.object(store, "RECORDS_DIR", records), \
                patch.object(store, "RECORD_INDEX_PATH", indexes / "record_index.json"):
                review.resolve_case("case_a", resolved_by="tester", resolution="approved")
                cases = {c["case_id"]: c for c in review.get_all_review_cases()}
                saved = store.load_record("cand_test")

            self.assertEqual(cases["case_a"]["status"], "resolved")
            # Only the targeted case is resolved; siblings stay open.
            self.assertEqual(cases["case_b"]["status"], "open")
            # Hold remains because an open case still references the record.
            self.assertTrue(saved.compliance.human_review_required)

    def test_review_resolve_purge_archives_record_and_resolves_all_cases(self):
        from core import review, store

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            records = base / "records"
            indexes = base / "indexes"
            logs = base / "logs"
            records.mkdir()
            indexes.mkdir()
            logs.mkdir()
            (indexes / "record_index.json").write_text("{}")
            queue_path = logs / "review_queue.jsonl"
            _write_jsonl(queue_path, [
                {"case_id": "case_a", "record_id": "cand_test", "reason": "missing_consent", "status": "open"},
                {"case_id": "case_b", "record_id": "cand_test", "reason": "low_extraction_confidence", "status": "open"},
            ])
            record = make_record(
                state=State(status="pending_review"),
                compliance=Compliance(consent_basis=None, source="document", retention_until="2099-01-01T00:00:00Z", human_review_required=True),
            )
            (records / "cand_test.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")

            with patch.object(review, "REVIEW_QUEUE_PATH", queue_path), \
                patch.object(store, "RECORDS_DIR", records), \
                patch.object(store, "RECORD_INDEX_PATH", indexes / "record_index.json"):
                review.resolve_case("case_a", resolved_by="tester", resolution="purged")
                cases = review.get_all_review_cases()
                saved = store.load_record("cand_test")

            self.assertTrue(all(case["status"] == "resolved" for case in cases))
            self.assertTrue(saved.state.archived)
            self.assertEqual(saved.state.status, "archived")
            self.assertFalse(saved.compliance.human_review_required)

    def test_matching_handles_missing_records_and_missing_scores(self):
        from core import match

        record = make_record()
        with tempfile.TemporaryDirectory() as tmp:
            requirements = Path(tmp) / "requirements"
            requirements.mkdir()
            req = RequirementRecord(
                id="req_test",
                title="Senior ML Engineer",
                requirements=RequirementCriteria(must_have=["Python"], location="Remote", language=["English"]),
                created_at="2026-05-23T00:00:00Z",
                updated_at="2026-05-23T00:00:00Z",
            )
            (requirements / "req_test.json").write_text(req.model_dump_json(indent=2), encoding="utf-8")

            def _load(record_id):
                if record_id == "cand_ok":
                    return record
                raise KeyError(record_id)

            with patch.object(match, "REQUIREMENTS_DIR", requirements), \
                patch.object(match, "_EMBEDDINGS_AVAILABLE", False), \
                patch.object(match, "filter_candidates", return_value=["cand_ok", "cand_missing"]), \
                patch.object(match, "load_record", side_effect=_load):
                report = match.generate_shortlist("req_test", use_llm_rerank=False)

            ids = [r["record_id"] for r in report["results"]]
            self.assertIn("cand_ok", ids)
            self.assertNotIn("cand_missing", ids)

    def test_requirement_id_traversal_rejected(self):
        from core import match

        with self.assertRaises(ValueError):
            match.generate_shortlist("../secret")

    def test_delete_job_rejects_traversal_id(self):
        import web.app as web_app

        with self.assertRaises(Exception) as ctx:
            asyncio.run(web_app.delete_job("..\\config"))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 400)

    def test_api_token_is_enforced_when_configured(self):
        from fastapi.testclient import TestClient
        import web.app as web_app

        client = TestClient(web_app.app)
        with patch.dict("os.environ", {"TALENT_POOL_API_TOKEN": "test-token"}):
            self.assertEqual(client.get("/api/config").status_code, 401)
            self.assertEqual(client.get("/api/config", headers={"X-API-Token": "test-token"}).status_code, 200)

    def test_data_region_none_is_not_region_violation(self):
        from core import compliance, review

        record = make_record()
        record.compliance.data_region = None
        with patch.object(compliance, "log_compliance"), patch.object(review, "append_review_case"):
            reasons = [case["reason"] for case in compliance.check_and_generate_review_cases("cand_test", record)]
            self.assertNotIn("data_region_violation", reasons)

        record.compliance.data_region = "US"
        with patch.object(compliance, "log_compliance"), patch.object(review, "append_review_case"):
            reasons = [case["reason"] for case in compliance.check_and_generate_review_cases("cand_test", record)]
            self.assertIn("data_region_violation", reasons)

    def test_bulk_refresh_dedupes_without_reordering(self):
        from core import maintenance

        record = make_record()
        record.profile.technologies_used = ["Python", "FastAPI"]
        record.profile.previous_jobs = ["Engineer - A"]
        extraction = make_extraction(
            technologies_used=["FastAPI", "Docker"],
            previous_jobs=["Engineer - A", "Lead - B"],
        )

        with patch.object(maintenance, "load_record", return_value=record), \
            patch.object(maintenance, "save_record"), \
            patch.object(maintenance, "extract_candidate_data", return_value=(extraction, {"provider": "local"})), \
            patch.object(maintenance, "check_and_generate_review_cases", return_value=[]):
            result = maintenance.bulk_refresh([{"record_id": "cand_test", "raw_text": "updated"}])
            self.assertEqual(result["success"], 1)
            self.assertEqual(record.profile.technologies_used, ["Python", "FastAPI", "Docker"])
            self.assertEqual(record.profile.previous_jobs, ["Engineer - A", "Lead - B"])

    def test_ingest_does_not_map_headline_to_seniority(self):
        from core import ingest, store, review

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            intake = base / "intake"
            records = base / "records"
            indexes = base / "indexes"
            logs = base / "logs"
            quarantine = base / "quarantine"
            for directory in (intake, records, indexes, logs, quarantine):
                directory.mkdir()
            source = intake / "cv.txt"
            source.write_text("Ada Lovelace\nSenior Python Engineer\nada@example.com", encoding="utf-8")
            manifest = indexes / "manifest.json"
            manifest.write_text("{}")
            (indexes / "record_index.json").write_text("{}")

            with patch.object(ingest, "INTAKE_DIR", intake), \
                patch.object(ingest, "RECORDS_DIR", records), \
                patch.object(ingest, "QUARANTINE_DIR", quarantine), \
                patch.object(ingest, "INGEST_MANIFEST_PATH", manifest), \
                patch.object(store, "RECORDS_DIR", records), \
                patch.object(store, "RECORD_INDEX_PATH", indexes / "record_index.json"), \
                patch.object(review, "REVIEW_QUEUE_PATH", logs / "review_queue.jsonl"), \
                patch.object(ingest, "extract_candidate_data", return_value=(make_extraction(), {"provider": "local"})), \
                patch.object(ingest, "check_and_generate_review_cases", return_value=[]):
                result = ingest.ingest_file(source)
                saved = store.load_record(result["record_id"])
                self.assertIsNone(saved.profile.headline)
                self.assertEqual(saved.profile.seniority, "Senior")

    def test_heuristic_extraction(self):
        from core.extract import extract_candidate_data_heuristic

        extraction, model_info = extract_candidate_data_heuristic(
            "Ada Lovelace\nSenior ML Engineer with 7 years of experience\n"
            "ada@example.com\nhttps://www.linkedin.com/in/ada\n"
            "Skills: Python, PyTorch, FastAPI, Docker\nLanguages: English, Romanian\nLocation: Remote"
        )
        self.assertEqual(model_info["provider"], "local")
        self.assertIn("python", extraction.technologies_used)
        self.assertIn("English", extraction.languages_spoken)
        self.assertEqual(extraction.years_of_experience, 7)

    def test_cv_preview_endpoint_returns_ui_shape(self):
        import web.app as web_app

        with patch("core.extract.extract_candidate_data", return_value=(make_extraction(), {"provider": "local"})):
            response = asyncio.run(web_app.parse_cv_preview(web_app.CVPreviewBody(resumeText="Ada Lovelace Python")))

        self.assertEqual(response["candidate"]["name"], "Ada Lovelace")
        self.assertEqual(response["candidate"]["seniority"], "Senior")
        self.assertEqual(response["candidate"]["topSkills"], ["PYTHON"])
        self.assertEqual(response["candidate"]["complianceStatus"], "PENDING REVIEW")

    def test_maintenance_stale_endpoint_maps_candidates(self):
        import web.app as web_app

        record = make_record()
        record.state.last_refreshed_at = "2025-01-01T00:00:00Z"
        record.identity.linkedin_url = "https://www.linkedin.com/in/ada"

        with patch("core.maintenance.find_stale_candidates", return_value=["cand_test"]), \
            patch.object(web_app, "load_record", return_value=record):
            response = asyncio.run(web_app.list_stale_candidates(months=6))

        self.assertEqual(response["months"], 6)
        self.assertEqual(response["candidates"][0]["id"], "cand_test")
        self.assertEqual(response["candidates"][0]["linkedinUrl"], "https://www.linkedin.com/in/ada")

    def test_anonymize_candidate_text_replaces_direct_identifiers(self):
        from core.security import anonymize_candidate_text

        payload = anonymize_candidate_text(
            "Ada Lovelace\nEmail: ada@example.com\nPhone: +40 722 111 222\n"
            "LinkedIn: https://www.linkedin.com/in/ada\nPortfolio: https://ada.dev\n"
            "Address: 12 Example Street\nFile: C:\\Users\\Ada\\cv.pdf"
        )
        anonymized = payload.anonymized_text
        for forbidden in ["Ada Lovelace", "ada@example.com", "+40 722 111 222", "linkedin.com/in/ada", "https://ada.dev", "C:\\Users\\Ada\\cv.pdf"]:
            self.assertNotIn(forbidden, anonymized)
        self.assertIn("CANDIDATE_001", anonymized)
        self.assertIn("EMAIL_001", anonymized)
        self.assertIn("PHONE_001", anonymized)
        self.assertIn("LINKEDIN_001", anonymized)

    def test_external_extraction_sends_anonymized_text_only(self):
        from core import extract, llm

        capture = CaptureLLM(json.dumps({
            "name": "CANDIDATE_001",
            "emails": ["EMAIL_001"],
            "phones": ["PHONE_001"],
            "linkedin_url": "LINKEDIN_001",
            "seniority": "Senior",
            "years_of_experience": 7,
            "study_degrees": [],
            "technologies_used": ["Python"],
            "languages_spoken": ["English"],
            "location": "Remote",
            "previous_jobs": [],
            "projects_developed": [],
            "summary": "CANDIDATE_001 has Python experience.",
            "extraction_confidence": 0.8,
            "review_flags": [],
        }))

        with patch.object(extract, "ENABLE_EXTERNAL_LLM", True), \
            patch.object(llm, "llm_available", return_value=True), \
            patch.object(llm, "complete", capture):
            extraction, model_info = extract.extract_candidate_data(
                "Ada Lovelace\nada@example.com\n+40 722 111 222\n"
                "https://www.linkedin.com/in/ada\nSenior Python Engineer with 7 years of experience"
            )

        prompt = capture.last_prompt
        for forbidden in ["Ada Lovelace", "ada@example.com", "+40 722 111 222", "linkedin.com/in/ada"]:
            self.assertNotIn(forbidden, prompt)
        self.assertIn("CANDIDATE_001", prompt)
        self.assertEqual(extraction.name, "Ada Lovelace")  # name token rehydrated
        self.assertIn("EMAIL_001", extraction.emails)        # other PII stays tokenized
        self.assertTrue(model_info["anonymized"])

    def test_external_rerank_prompt_is_anonymized(self):
        from core import match, llm

        record = make_record()
        record.profile.summary = "Ada Lovelace built private ML systems."
        record.identity.emails = ["ada@example.com"]
        capture = CaptureLLM(json.dumps({"match_score": 0.9, "evidence": ["Strong Python"], "uncertainty_flags": []}))

        with tempfile.TemporaryDirectory() as tmp:
            requirements = Path(tmp) / "requirements"
            requirements.mkdir()
            req = RequirementRecord(
                id="req_test",
                title="Senior ML Engineer",
                requirements=RequirementCriteria(must_have=["Python"], location="Remote", language=["English"]),
                created_at="2026-05-23T00:00:00Z",
                updated_at="2026-05-23T00:00:00Z",
            )
            (requirements / "req_test.json").write_text(req.model_dump_json(indent=2), encoding="utf-8")

            with patch.object(match, "ENABLE_EXTERNAL_LLM", True), \
                patch.object(match, "REQUIREMENTS_DIR", requirements), \
                patch.object(match, "_EMBEDDINGS_AVAILABLE", False), \
                patch.object(match, "filter_candidates", return_value=["cand_test"]), \
                patch.object(match, "load_record", return_value=record), \
                patch.object(llm, "llm_available", return_value=True), \
                patch.object(llm, "complete", capture):
                report = match.generate_shortlist("req_test", use_llm_rerank=True)

        prompt = capture.last_prompt
        self.assertEqual(report["results"][0]["name"], "Ada Lovelace")
        self.assertIn("CANDIDATE_001", prompt)
        self.assertNotIn("Ada Lovelace", prompt)
        self.assertNotIn("ada@example.com", prompt)

    def test_external_outreach_prompt_is_anonymized_and_rehydrated(self):
        from core import outreach, llm, compliance, review

        record = make_record()
        record.profile.summary = "Ada Lovelace built private ML systems."
        record.identity.emails = ["ada@example.com"]
        job = {"title": "Senior ML Engineer", "requirements": {"must_have": ["Python"]}}
        capture = CaptureLLM("Hi CANDIDATE_001,\nYour Python background is relevant.")
        captured_cases = []

        with patch.object(outreach, "ENABLE_EXTERNAL_OUTREACH_LLM", True), \
            patch.object(outreach, "load_record", return_value=record), \
            patch.object(outreach, "_load_job", return_value=job), \
            patch.object(compliance, "record_block_reasons", return_value=[]), \
            patch.object(review, "append_review_case", side_effect=lambda case: captured_cases.append(case)), \
            patch.object(llm, "llm_available", return_value=True), \
            patch.object(llm, "complete", capture):
            outreach.generate_draft("cand_test", "req_test")

        prompt = capture.last_prompt
        self.assertIn("CANDIDATE_001", prompt)
        self.assertNotIn("Ada Lovelace", prompt)
        self.assertNotIn("ada@example.com", prompt)
        self.assertIn("Hi Ada Lovelace", captured_cases[0]["draft_text"])
        self.assertNotIn("CANDIDATE_001", captured_cases[0]["draft_text"])

    def test_agent_chat_does_not_call_hosted_llm_for_candidate_context(self):
        import web.app as web_app
        from core import llm

        record = make_record()
        record.identity.emails = ["ada@example.com"]
        record.identity.phones = ["+40 722 111 222"]
        record.identity.linkedin_url = "https://linkedin.com/in/ada"
        record.profile.summary = "Ada Lovelace built private ML systems."

        body = web_app._GeminiChatBody(
            messages=[web_app._ChatMessage(role="user", content="Which candidates know Python?")],
            context={"candidates": [], "jobs": [], "reviewTasks": []},
        )

        with patch.object(web_app, "_candidate_record_ids", return_value=["cand_test"]), \
            patch.object(web_app, "load_record", return_value=record), \
            patch.object(llm, "llm_available", return_value=True) as llm_available, \
            patch.object(llm, "complete") as complete:
            response = asyncio.run(web_app.gemini_chat(body))

        llm_available.assert_not_called()
        complete.assert_not_called()
        self.assertIn("Ada Lovelace", response["text"])
        self.assertNotIn("ada@example.com", response["text"])
        self.assertNotIn("+40 722 111 222", response["text"])
        self.assertNotIn("linkedin.com/in/ada", response["text"])

    def test_agent_create_job_requires_confirmation_before_mutation(self):
        import web.app as web_app

        body = web_app._GeminiChatBody(
            messages=[
                web_app._ChatMessage(
                    role="user",
                    content="Create a Senior Python Engineer role in Remote with Python and FastAPI",
                )
            ],
            context={"candidates": [], "jobs": [], "reviewTasks": []},
        )

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            requirements = base / "requirements"
            proposals = base / "agent_proposals"
            requirements.mkdir()
            web_app._AGENT_PROPOSALS.clear()
            with patch.object(web_app, "REQUIREMENTS_DIR", requirements), \
                patch.object(web_app, "AGENT_PROPOSALS_DIR", proposals), \
                patch.object(web_app, "log_event"):
                response = asyncio.run(web_app.gemini_chat(body))
                self.assertEqual(response["actions"], [])
                self.assertEqual(len(response["proposals"]), 1)
                self.assertEqual(list(requirements.glob("*.json")), [])

                proposal_id = response["proposals"][0]["id"]
                proposal_file = proposals / f"{proposal_id}.json"
                self.assertTrue(proposal_file.exists())

                # Simulate a backend restart: disk-backed proposals should still confirm.
                web_app._AGENT_PROPOSALS.clear()
                confirmed = asyncio.run(web_app.confirm_agent_action(proposal_id))
                self.assertFalse(proposal_file.exists())

            self.assertEqual(confirmed["actions"][0]["type"], "job_created")
            created_files = list(requirements.glob("req_*.json"))
            self.assertEqual(len(created_files), 1)
            created = json.loads(created_files[0].read_text(encoding="utf-8"))
            self.assertEqual(created["title"], "Senior Python Engineer")
            web_app._AGENT_PROPOSALS.clear()

    def test_agent_confirm_rejects_traversal_proposal_id(self):
        import web.app as web_app

        with self.assertRaises(web_app.HTTPException) as ctx:
            asyncio.run(web_app.confirm_agent_action("../secret"))

        self.assertEqual(ctx.exception.status_code, 400)

    def test_legacy_candidates_page_route_is_removed(self):
        import web.app as web_app

        self.assertNotIn("/candidates", {route.path for route in web_app.app.routes})

    def test_spreadsheet_import_route_is_mounted(self):
        import web.app as web_app

        self.assertIn("/api/intake/csv", {route.path for route in web_app.app.routes})

    def test_spreadsheet_import_rejects_unknown_csv_schema_loudly(self):
        from core.csv_ingest import CSVIngestProgress, stream_ingest_file

        progress = CSVIngestProgress()
        stream_ingest_file(b"foo;bar\nx;y\n", "bad.csv", progress)

        self.assertTrue(progress.done)
        self.assertEqual(progress.failed, 1)
        self.assertIn("No recognized candidate or job columns", progress.errors[0]["error"])

    def test_spreadsheet_header_fallback_is_lowercase(self):
        from core import csv_ingest

        self.assertEqual(csv_ingest._norm_header("Skills"), "skills")
        self.assertEqual(csv_ingest._norm_header("Positions"), "positions")
        self.assertEqual(csv_ingest._norm_header("Custom_Header"), "custom_header")

    def test_utc_now_iso_is_parseable_zulu_time(self):
        from datetime import datetime
        from core.time_utils import utc_now_iso

        value = utc_now_iso()
        self.assertTrue(value.endswith("Z"))
        self.assertNotIn("+00:00Z", value)
        datetime.fromisoformat(value.replace("Z", "+00:00"))

    def test_spreadsheet_import_enforces_row_limit(self):
        from core import csv_ingest
        from core.csv_ingest import CSVIngestProgress, stream_ingest_file

        progress = CSVIngestProgress()
        payload = b"candidate_name,skills\nAda,Python\nGrace,COBOL\n"
        with patch.object(csv_ingest, "_MAX_SPREADSHEET_ROWS", 1):
            stream_ingest_file(payload, "bulk.csv", progress)

        self.assertTrue(progress.done)
        self.assertEqual(progress.failed, 1)
        self.assertIn("row limit exceeded", progress.errors[0]["error"])

    def test_spreadsheet_imports_excel_candidate_job_and_review_case(self):
        from core import csv_ingest, store
        from core.csv_ingest import CSVIngestProgress, stream_ingest_file
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append([
            "candidate_name",
            "email",
            "skills",
            "career_objective",
            "job_position_name",
            "skills_required",
            "responsibilities.1",
        ])
        sheet.append([
            "Ada Lovelace",
            "ada@example.com",
            "['Python', 'FastAPI']",
            "Builds analytical engines.",
            "Python Engineer",
            "['Python']",
            "Build APIs.",
        ])
        payload = io.BytesIO()
        workbook.save(payload)

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            records = base / "records"
            indexes = base / "indexes"
            requirements = base / "requirements"
            records.mkdir()
            indexes.mkdir()
            requirements.mkdir()
            (indexes / "record_index.json").write_text("{}", encoding="utf-8")

            with patch.object(store, "RECORDS_DIR", records), \
                patch.object(store, "RECORD_INDEX_PATH", indexes / "record_index.json"), \
                patch.object(store, "log_event"), \
                patch.object(csv_ingest, "RECORDS_DIR", records), \
                patch.object(csv_ingest, "REQUIREMENTS_DIR", requirements), \
                patch.object(csv_ingest, "check_and_generate_review_cases") as review_check:
                progress = CSVIngestProgress()
                stream_ingest_file(payload.getvalue(), "bulk.xlsx", progress)

            self.assertTrue(progress.done)
            self.assertEqual(progress.failed, 0, progress.errors)
            self.assertEqual(progress.rows_seen, 1)
            self.assertEqual(progress.processed, 1)
            self.assertEqual(progress.jobs_created, 1)
            self.assertEqual(len(list(records.glob("*.json"))), 1)
            self.assertEqual(len(list(requirements.glob("*.json"))), 1)
            review_check.assert_called_once()

    def test_candidate_role_eval_normalizes_labels_and_scores_invalid_predictions(self):
        from core.candidate_role_eval import normalize_match_label
        from tools.eval_candidates import CandidateRoleEvalExample, build_report

        self.assertEqual(normalize_match_label("Match"), "match")
        self.assertEqual(normalize_match_label("no match"), "no_match")
        self.assertIsNone(normalize_match_label("maybe"))

        examples = [
            CandidateRoleEvalExample(2, "Python engineer", "Python role", "match"),
            CandidateRoleEvalExample(3, "Sales manager", "Python role", "no_match"),
        ]
        report = build_report(examples, ["match", "maybe"], target=0.8)

        self.assertEqual(report["accuracy"], 0.5)
        self.assertFalse(report["pass"])
        self.assertEqual(report["per_class"]["match"]["accuracy"], 1.0)
        self.assertEqual(report["per_class"]["no_match"]["accuracy"], 0.0)
        self.assertEqual(report["failed_examples"][0]["predicted"], "invalid")

    def test_candidate_role_eval_dataset_validation(self):
        from tools.eval_candidates import load_eval_dataset

        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "bad.csv"
            bad_path.write_text("candidate_profile,ground_truth_label\nAda,match\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                load_eval_dataset(bad_path)

            good_path = Path(tmp) / "good.csv"
            good_path.write_text(
                "candidate_profile,role_description,ground_truth_label\n"
                "\"Senior Python engineer with 6 years of experience\","
                "\"Python role requiring 5 years of experience\","
                "match\n",
                encoding="utf-8",
            )
            examples = load_eval_dataset(good_path)

        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0].ground_truth_label, "match")

    def test_candidate_role_eval_script_returns_pass_fail_codes(self):
        from tools import eval_candidates

        with tempfile.TemporaryDirectory() as tmp:
            pass_path = Path(tmp) / "pass.csv"
            pass_path.write_text(
                "candidate_profile,role_description,ground_truth_label\n"
                "\"Senior Python engineer with 6 years of experience in FastAPI and AWS\","
                "\"Senior role requiring 5 years of experience with Python, FastAPI, and AWS\","
                "match\n"
                "\"Junior React developer with 1 year of experience\","
                "\"Senior role requiring 5 years of experience with Python, FastAPI, and AWS\","
                "no_match\n",
                encoding="utf-8",
            )
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(eval_candidates.main(["--data", str(pass_path), "--compact"]), 0)

            fail_path = Path(tmp) / "fail.csv"
            fail_path.write_text(
                "candidate_profile,role_description,ground_truth_label\n"
                "\"Senior Python engineer with 6 years of experience in FastAPI and AWS\","
                "\"Senior role requiring 5 years of experience with Python, FastAPI, and AWS\","
                "no_match\n",
                encoding="utf-8",
            )
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(eval_candidates.main(["--data", str(fail_path), "--compact"]), 1)

    def test_match_candidate_to_role_returns_binary_eval_label(self):
        from core.candidate_role_eval import match_candidate_to_role

        self.assertEqual(
            match_candidate_to_role(
                "Senior data engineer with 6 years of experience in Spark, Airflow, Python, SQL, and AWS.",
                "Data Engineer role requiring 4+ years of experience with Spark, Airflow, Python, SQL, and AWS.",
            ),
            "match",
        )
        self.assertEqual(
            match_candidate_to_role(
                "Junior frontend developer with 1 year of experience in React and CSS.",
                "Data Engineer role requiring 4+ years of experience with Spark, Airflow, Python, SQL, and AWS.",
            ),
            "no_match",
        )


if __name__ == "__main__":
    unittest.main()
