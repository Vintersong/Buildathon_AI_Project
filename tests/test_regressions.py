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


class FakeResponse:
    def __init__(self, text):
        self.text = text


class CapturingModel:
    def __init__(self, response_text):
        self.response_text = response_text
        self.prompts = []

    def generate_content(self, prompt, generation_config=None):
        self.prompts.append(prompt)
        return FakeResponse(self.response_text)


class FakeGenai:
    class GenerationConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs


class RegressionTests(unittest.TestCase):
    def test_quarantine_directories_are_created_and_redacted(self):
        from core import extract, ingest

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with patch.object(extract, "QUARANTINE_DIR", tmp_path):
                extract._quarantine_failed_output("Contact ada@example.com", "Call +40 722 111 222", "json_decode_error")
                payload = json.loads(next((tmp_path / "schema_failures").glob("*.json")).read_text())
                self.assertNotIn("ada@example.com", json.dumps(payload))
                self.assertNotIn("+40 722 111 222", json.dumps(payload))

            with patch.object(ingest, "QUARANTINE_DIR", tmp_path):
                ingest._quarantine_security(Path("C:/tmp/ada@example.com.pdf"), "path_not_allowed")
                payload = json.loads(next((tmp_path / "security_rejections").glob("*.json")).read_text())
                self.assertNotIn("ada@example.com", json.dumps(payload))

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

    def test_review_approval_records_consent_and_collapses_duplicate_reason_cases(self):
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
            queue_path = logs / "review_queue.json"
            queue_path.write_text(json.dumps([
                {"case_id": "case_a", "record_id": "cand_test", "reason": "missing_consent", "status": "open"},
                {"case_id": "case_b", "record_id": "cand_test", "reason": "missing_consent", "status": "open"},
                {"case_id": "case_c", "record_id": "cand_test", "reason": "low_extraction_confidence", "status": "open"},
            ]))
            record = make_record(
                state=State(status="pending_review"),
                compliance=Compliance(consent_basis=None, source="document", retention_until="2099-01-01T00:00:00Z", human_review_required=True),
            )
            (records / "cand_test.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")

            with patch.object(review, "REVIEW_QUEUE_PATH", queue_path), \
                patch.object(store, "RECORDS_DIR", records), \
                patch.object(store, "RECORD_INDEX_PATH", indexes / "record_index.json"):
                review.resolve_case("case_a", "approved", "tester")
                queue = json.loads(queue_path.read_text())
                saved = store.load_record("cand_test")

            statuses = {case["case_id"]: case["status"] for case in queue}
            self.assertEqual(statuses["case_a"], "resolved")
            self.assertEqual(statuses["case_b"], "resolved")
            self.assertEqual(statuses["case_c"], "open")
            self.assertEqual(saved.compliance.consent_basis, "uploaded_consent_proof")
            self.assertTrue(saved.compliance.human_review_required)

    def test_review_purge_archives_record_and_resolves_all_record_cases(self):
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
            queue_path = logs / "review_queue.json"
            queue_path.write_text(json.dumps([
                {"case_id": "case_a", "record_id": "cand_test", "reason": "missing_consent", "status": "open"},
                {"case_id": "case_b", "record_id": "cand_test", "reason": "low_extraction_confidence", "status": "open"},
            ]))
            record = make_record(
                state=State(status="pending_review"),
                compliance=Compliance(consent_basis=None, source="document", retention_until="2099-01-01T00:00:00Z", human_review_required=True),
            )
            (records / "cand_test.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")

            with patch.object(review, "REVIEW_QUEUE_PATH", queue_path), \
                patch.object(store, "RECORDS_DIR", records), \
                patch.object(store, "RECORD_INDEX_PATH", indexes / "record_index.json"):
                review.resolve_case("case_a", "purged", "tester")
                queue = json.loads(queue_path.read_text())
                saved = store.load_record("cand_test")

            self.assertTrue(all(case["status"] == "resolved" for case in queue))
            self.assertTrue(saved.state.archived)
            self.assertEqual(saved.state.status, "archived")
            self.assertFalse(saved.compliance.human_review_required)

    def test_matching_handles_missing_records_and_missing_scores(self):
        from core import match

        req = RequirementRecord(
            id="req_test",
            title="Senior ML Engineer",
            requirements=RequirementCriteria(must_have=["Python"], location="Remote", language=["English"]),
            scoring={"skills": {"weight": 0.5}, "experience": {"weight": 0.3}, "location": {"weight": 0.2}},
            created_at="2026-05-23T00:00:00Z",
            updated_at="2026-05-23T00:00:00Z",
        )
        record = make_record()

        with patch.object(match, "load_record", side_effect=lambda record_id: record if record_id == "cand_ok" else None):
            self.assertEqual(set(match.score_keywords(["cand_ok", "missing"], req)), {"cand_ok"})

        with patch.object(match, "_load_requirement", return_value=req), \
            patch.object(match, "_get_all_active_candidates", return_value=["cand_ok"]), \
            patch.object(match, "filter_candidates", return_value=["cand_ok"]), \
            patch.object(match, "score_keywords", return_value={}), \
            patch.object(match, "score_embeddings", return_value={}), \
            patch.object(match, "score_structured", return_value={}), \
            patch.object(match, "load_record", return_value=record):
            report = match.generate_shortlist("req_test", use_llm_rerank=False)
            self.assertEqual(report["shortlist"][0]["record_id"], "cand_ok")

    def test_data_region_none_is_not_region_violation(self):
        from core import compliance

        record = make_record()
        record.compliance.data_region = None
        with patch.object(compliance, "load_record", return_value=record), patch.object(compliance, "log_compliance"):
            reasons = [case["reason"] for case in compliance.evaluate_compliance("cand_test")]
            self.assertNotIn("data_region_violation", reasons)

        record.compliance.data_region = "US"
        with patch.object(compliance, "load_record", return_value=record), patch.object(compliance, "log_compliance"):
            reasons = [case["reason"] for case in compliance.evaluate_compliance("cand_test")]
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
            patch.object(maintenance, "extract_candidate_data", return_value=(extraction, {"external": False})), \
            patch.object(maintenance, "evaluate_compliance", return_value=[]), \
            patch.object(maintenance, "add_to_queue"):
            maintenance.bulk_refresh([{"record_id": "cand_test", "raw_text": "updated"}])
            self.assertEqual(record.profile.technologies_used, ["Python", "FastAPI", "Docker"])
            self.assertEqual(record.profile.previous_jobs, ["Engineer - A", "Lead - B"])

    def test_ingest_does_not_map_headline_to_seniority(self):
        from core import ingest, store

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            intake = base / "intake"
            records = base / "records"
            indexes = base / "indexes"
            intake.mkdir()
            records.mkdir()
            indexes.mkdir()
            source = intake / "cv.txt"
            source.write_text("Ada Lovelace\nSenior Python Engineer\nada@example.com", encoding="utf-8")
            manifest = indexes / "manifest.json"
            manifest.write_text("{}")
            (indexes / "record_index.json").write_text("{}")

            with patch.object(ingest, "INTAKE_DIR", intake), \
                patch.object(ingest, "MANIFEST_PATH", manifest), \
                patch.object(ingest, "DEFAULT_CONSENT_BASIS", "candidate_consent"), \
                patch.object(store, "RECORDS_DIR", records), \
                patch.object(store, "RECORD_INDEX_PATH", indexes / "record_index.json"), \
                patch.object(ingest, "extract_candidate_data", return_value=(make_extraction(), {"external": False})), \
                patch.object(ingest, "evaluate_compliance", return_value=[]), \
                patch.object(ingest, "add_to_queue"):
                record_id = ingest.ingest_file(source)
                saved = store.load_record(record_id)
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
        self.assertIn("Python", extraction.technologies_used)
        self.assertIn("English", extraction.languages_spoken)
        self.assertEqual(extraction.years_of_experience, 7)

    def test_requirement_id_traversal_rejected(self):
        from core import match

        with self.assertRaises(ValueError):
            match._load_requirement("../secret")

    def test_legacy_candidates_page_route_is_removed(self):
        import web.app as web_app

        self.assertNotIn("/candidates", {route.path for route in web_app.app.routes})

    def test_cv_preview_endpoint_returns_ui_shape(self):
        import web.app as web_app

        with patch("core.extract.extract_candidate_data", return_value=(make_extraction(), {"external": False})):
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
        from core import extract

        model_response = json.dumps({
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
        })
        model = CapturingModel(model_response)

        with patch.object(extract, "ENABLE_EXTERNAL_LLM", True), \
            patch.object(extract, "GEMINI_API_KEY", "test-key"), \
            patch.object(extract, "genai", FakeGenai), \
            patch.object(extract, "get_use_local_llm", return_value=False), \
            patch.object(extract, "get_extraction_model", return_value=model):
            extraction, model_info = extract.extract_candidate_data(
                "Ada Lovelace\nada@example.com\n+40 722 111 222\n"
                "https://www.linkedin.com/in/ada\nSenior Python Engineer with 7 years of experience"
            )

        prompt = model.prompts[0]
        for forbidden in ["Ada Lovelace", "ada@example.com", "+40 722 111 222", "linkedin.com/in/ada"]:
            self.assertNotIn(forbidden, prompt)
        self.assertIn("CANDIDATE_001", prompt)
        self.assertEqual(extraction.name, "Ada Lovelace")
        self.assertEqual(extraction.emails, ["ada@example.com"])
        self.assertTrue(model_info["anonymized"])

    def test_external_rerank_prompt_is_anonymized(self):
        from core import match

        record = make_record()
        record.profile.summary = "Ada Lovelace built private ML systems."
        record.identity.emails = ["ada@example.com"]
        req = RequirementRecord(
            id="req_test",
            title="Senior ML Engineer",
            requirements=RequirementCriteria(must_have=["Python"], location="Remote", language=["English"]),
            created_at="2026-05-23T00:00:00Z",
            updated_at="2026-05-23T00:00:00Z",
        )
        model = CapturingModel(json.dumps({"match_score": 0.9, "evidence": ["Strong Python"], "uncertainty_flags": []}))

        with patch.object(match, "ENABLE_EXTERNAL_LLM", True), \
            patch.object(match, "GEMINI_API_KEY", "test-key"), \
            patch.object(match, "genai", FakeGenai), \
            patch.object(match, "get_use_local_llm", return_value=False), \
            patch.object(match, "get_rerank_model", return_value=model), \
            patch.object(match, "_load_requirement", return_value=req), \
            patch.object(match, "_get_all_active_candidates", return_value=["cand_test"]), \
            patch.object(match, "filter_candidates", return_value=["cand_test"]), \
            patch.object(match, "score_keywords", return_value={"cand_test": 1.0}), \
            patch.object(match, "score_embeddings", return_value={"cand_test": 0.0}), \
            patch.object(match, "score_structured", return_value={"cand_test": {"experience": 1.0, "location": 1.0, "language": 1.0, "freshness": 1.0}}), \
            patch.object(match, "load_record", return_value=record):
            report = match.generate_shortlist("req_test", use_llm_rerank=True)

        prompt = model.prompts[0]
        self.assertEqual(report["shortlist"][0]["candidate_name"], "Ada Lovelace")
        self.assertIn("CANDIDATE_001", prompt)
        self.assertNotIn("Ada Lovelace", prompt)
        self.assertNotIn("ada@example.com", prompt)

    def test_external_outreach_prompt_is_anonymized_and_rehydrated(self):
        from core import outreach

        record = make_record()
        record.profile.summary = "Ada Lovelace built private ML systems."
        record.identity.emails = ["ada@example.com"]
        req = RequirementRecord(
            id="req_test",
            title="Senior ML Engineer",
            requirements=RequirementCriteria(must_have=["Python"]),
            created_at="2026-05-23T00:00:00Z",
            updated_at="2026-05-23T00:00:00Z",
        )
        model = CapturingModel("Hi CANDIDATE_001,\nYour Python background is relevant.")
        captured_cases = []

        with patch.object(outreach, "ENABLE_EXTERNAL_OUTREACH_LLM", True), \
            patch.object(outreach, "GEMINI_API_KEY", "test-key"), \
            patch.object(outreach, "genai", FakeGenai), \
            patch.object(outreach, "get_use_local_llm", return_value=False), \
            patch.object(outreach, "get_draft_model", return_value=model), \
            patch.object(outreach, "load_record", return_value=record), \
            patch.object(outreach, "_load_requirement", return_value=req), \
            patch.object(outreach, "add_to_queue", side_effect=lambda cases: captured_cases.extend(cases)):
            outreach.generate_draft("cand_test", "req_test")

        prompt = model.prompts[0]
        self.assertIn("CANDIDATE_001", prompt)
        self.assertNotIn("Ada Lovelace", prompt)
        self.assertNotIn("ada@example.com", prompt)
        self.assertIn("Hi Ada Lovelace", captured_cases[0]["draft_text"])
        self.assertNotIn("CANDIDATE_001", captured_cases[0]["draft_text"])

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

            review_case = {"case_id": "case_test", "record_id": "cand_test", "reason": "low_extraction_confidence"}
            with patch.object(store, "RECORDS_DIR", records), \
                patch.object(store, "RECORD_INDEX_PATH", indexes / "record_index.json"), \
                patch.object(store, "log_event"), \
                patch.object(csv_ingest, "RECORDS_DIR", records), \
                patch.object(csv_ingest, "REQUIREMENTS_DIR", requirements), \
                patch.object(csv_ingest, "evaluate_compliance", return_value=[review_case]), \
                patch.object(csv_ingest, "add_to_queue") as add_to_queue:
                progress = CSVIngestProgress()
                stream_ingest_file(payload.getvalue(), "bulk.xlsx", progress)

            self.assertTrue(progress.done)
            self.assertEqual(progress.failed, 0, progress.errors)
            self.assertEqual(progress.rows_seen, 1)
            self.assertEqual(progress.processed, 1)
            self.assertEqual(progress.jobs_created, 1)
            self.assertEqual(len(list(records.glob("*.json"))), 1)
            self.assertEqual(len(list(requirements.glob("*.json"))), 1)
            add_to_queue.assert_called_once_with([review_case])

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
