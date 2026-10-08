"""Synthetic regression tests for the Industry Resume AI/ATS sidecar."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


TEST_DIR = Path(__file__).resolve().parent
FIXTURE = TEST_DIR / "fixtures" / "industry-resume-e2e.json"
BUNDLE_ROOT = TEST_DIR / "fixtures" / "industry-resume-e2e-files"
VALIDATOR = TEST_DIR.parent / "scripts" / "validate_industry_resume_analysis.py"
sys.path.insert(0, str(VALIDATOR.parent))
from validate_industry_resume_analysis import build_audit_package  # noqa: E402


def load_fixture() -> dict[str, Any]:
    with FIXTURE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run_path(path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--analysis", str(path), *extra],
        text=True,
        capture_output=True,
        check=False,
    )


def run_analysis(analysis: dict[str, Any], *extra: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        bundle = root / "bundle"
        shutil.copytree(BUNDLE_ROOT, bundle)
        run_copy = json.loads(json.dumps(analysis))
        audit_output = next(
            (
                item
                for item in run_copy.get("outputs", [])
                if item.get("artifact_type") == "MARKDOWN_AUDIT_PACKAGE"
            ),
            None,
        )
        canonical_audit = BUNDLE_ROOT / "outputs" / "industry-resume-audit.md"
        if (
            isinstance(audit_output, dict)
            and audit_output.get("relative_path") == "outputs/industry-resume-audit.md"
            and audit_output.get("sha256") == sha256_uri(canonical_audit)
        ):
            audit = bundle / "outputs" / "industry-resume-audit.md"
            audit.write_text(build_audit_package(run_copy), encoding="utf-8")
            audit_output["sha256"] = sha256_uri(audit)
        path = root / "analysis.json"
        path.write_text(json.dumps(run_copy), encoding="utf-8")
        return run_path(path, "--bundle-root", str(bundle), *extra)


def run_raw(raw: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "analysis.json"
        path.write_text(raw, encoding="utf-8")
        return run_path(path)


def issue_ids(completed: subprocess.CompletedProcess[str]) -> set[str]:
    return {issue["check_id"] for issue in json.loads(completed.stdout)["issues"]}


def sha256_uri(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def replace_scalar(value: Any, old: str, new: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if item == old:
                value[key] = new
            else:
                replace_scalar(item, old, new)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if item == old:
                value[index] = new
            else:
                replace_scalar(item, old, new)


def run_modified_current_resume(
    analysis: dict[str, Any], transform: Any
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        bundle = root / "bundle"
        shutil.copytree(BUNDLE_ROOT, bundle)
        run_copy = json.loads(json.dumps(analysis))
        current_source = next(
            item
            for item in run_copy["sources"]
            if item["source_id"] == run_copy["run"]["current_resume_source_id"]
        )
        current_path = bundle / current_source["relative_path"]
        old_hash = current_source["sha256"]
        current_path.write_text(
            transform(current_path.read_text(encoding="utf-8")), encoding="utf-8"
        )
        new_hash = sha256_uri(current_path)
        replace_scalar(run_copy, old_hash, new_hash)

        audit_output = next(
            item
            for item in run_copy["outputs"]
            if item["artifact_type"] == "MARKDOWN_AUDIT_PACKAGE"
        )
        audit_path = bundle / audit_output["relative_path"]
        audit_path.write_text(build_audit_package(run_copy), encoding="utf-8")
        audit_output["sha256"] = sha256_uri(audit_path)

        analysis_path = root / "analysis.json"
        analysis_path.write_text(json.dumps(run_copy), encoding="utf-8")
        return run_path(analysis_path, "--bundle-root", str(bundle))


def run_modified_resume_pair(
    analysis: dict[str, Any], baseline_transform: Any, current_transform: Any
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        bundle = root / "bundle"
        shutil.copytree(BUNDLE_ROOT, bundle)
        run_copy = json.loads(json.dumps(analysis))
        source_transforms = {
            "BASELINE_RESUME": baseline_transform,
            "CURRENT_RESUME": current_transform,
        }
        for source_type, transform in source_transforms.items():
            source = next(
                item
                for item in run_copy["sources"]
                if item["source_type"] == source_type
            )
            path = bundle / source["relative_path"]
            old_hash = source["sha256"]
            path.write_text(transform(path.read_text(encoding="utf-8")), encoding="utf-8")
            replace_scalar(run_copy, old_hash, sha256_uri(path))

        audit_output = next(
            item
            for item in run_copy["outputs"]
            if item["artifact_type"] == "MARKDOWN_AUDIT_PACKAGE"
        )
        audit_path = bundle / audit_output["relative_path"]
        audit_path.write_text(build_audit_package(run_copy), encoding="utf-8")
        audit_output["sha256"] = sha256_uri(audit_path)

        analysis_path = root / "analysis.json"
        analysis_path.write_text(json.dumps(run_copy), encoding="utf-8")
        return run_path(analysis_path, "--bundle-root", str(bundle))


def requirement_record(analysis: dict[str, Any], field: str, requirement_id: str) -> dict[str, Any]:
    return next(item for item in analysis[field] if item.get("requirement_id") == requirement_id)


def gate_record(analysis: dict[str, Any], gate_id: str) -> dict[str, Any]:
    return next(item for item in analysis["gate_results"] if item["gate_id"] == gate_id)


def dimension_record(analysis: dict[str, Any], dimension: str) -> dict[str, Any]:
    return next(
        item
        for item in analysis["audits"]["hiring_manager"]["dimension_results"]
        if item["dimension"] == dimension
    )


def disable_gate(analysis: dict[str, Any], gate_id: str) -> None:
    config_keys = {
        "GATE_0": "jd_decomposition",
        "GATE_1": "eligibility",
        "GATE_2": "evidence_mapping",
        "GATE_3": "semantic_alignment",
        "GATE_4": "ats_parse",
        "GATE_5": "ai_recruiter",
        "GATE_6": "recruiter_scan",
        "GATE_7": "hiring_manager",
    }
    audit_fields = {
        "GATE_4": ("ats_parse",),
        "GATE_5": ("ai_recruiter",),
        "GATE_6": ("human_recruiter", "top_third"),
        "GATE_7": ("hiring_manager",),
    }
    analysis["config"]["gates"][config_keys[gate_id]] = False
    gate_record(analysis, gate_id).update(enabled=False, status="NOT_RUN", blocking=False)
    analysis["evaluator_runs"] = [
        item for item in analysis["evaluator_runs"] if item["gate_id"] != gate_id
    ]
    for field in audit_fields.get(gate_id, ()):
        analysis["audits"][field] = None
    if gate_id == "GATE_3":
        analysis["semantic_alignments"] = []
    if gate_id == "GATE_1":
        analysis["eligibility_results"] = []
    if gate_id == "GATE_5":
        analysis["qualification_results"] = []
        analysis["metrics"]["required_qualifications"] = {
            "met": 0,
            "partial": 0,
            "not_found": 0,
            "total": 0,
        }
        analysis["metrics"]["preferred_qualifications"] = {
            "met": 0,
            "partial": 0,
            "not_found": 0,
            "total": 0,
        }
        analysis["metrics"]["critical_missing_requirement_ids"] = []


class IndustryResumeValidationTests(unittest.TestCase):
    maxDiff = None

    def assert_pass(self, completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["result"], "PASS")
        self.assertEqual(payload["error_count"], 0)
        self.assertIn("Industry Resume analysis: PASS", completed.stderr)
        return payload

    def assert_fails_with(
        self, completed: subprocess.CompletedProcess[str], check_id: str
    ) -> dict[str, Any]:
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["result"], "FAIL")
        self.assertIn(check_id, issue_ids(completed))
        return payload

    def test_contract_e2e_fixture_cli_outputs_and_privacy_minimized_dashboard(self) -> None:
        """Exercise a golden mocked contract run, not an LLM generation pipeline."""

        completed = run_path(
            FIXTURE,
            "--bundle-root",
            str(BUNDLE_ROOT),
            "--dashboard",
        )
        payload = self.assert_pass(completed)
        dashboard = payload["dashboard"]
        self.assertIn("Overall status: PASS_WITH_WARNINGS", dashboard)
        self.assertIn("REQ-004", dashboard)
        self.assertIn("## Evidence Strength", dashboard)
        self.assertIn("- TRUE_GAP: 2", dashboard)
        self.assertIn("## Highest-Priority Supported Improvements", dashboard)
        self.assertIn("GAP-002 / REQ-002: add_if_true", dashboard)

        analysis = load_fixture()
        sources = {item["source_id"]: item for item in analysis["sources"]}
        evidence = {item["id"]: item for item in analysis["evidence_items"]}
        outputs = {item["artifact_type"]: item for item in analysis["outputs"]}

        self.assertEqual(
            {item["relative_path"] for item in analysis["sources"]},
            {
                "sources/job-description.txt",
                "sources/baseline-resume.txt",
                "sources/candidate-evidence-profile.txt",
                "outputs/final-resume.txt",
            },
        )
        self.assertEqual(
            {item["relative_path"] for item in analysis["outputs"]},
            {"outputs/final-resume.txt", "outputs/industry-resume-audit.md"},
        )
        for record in (*analysis["sources"], *analysis["outputs"]):
            artifact_path = BUNDLE_ROOT / record["relative_path"]
            self.assertTrue(artifact_path.is_file())
            self.assertEqual(record["sha256"], sha256_uri(artifact_path))

        jd_text = (BUNDLE_ROOT / sources["SRC-JD"]["relative_path"]).read_text(
            encoding="utf-8"
        )
        final_text = (BUNDLE_ROOT / outputs["FINAL_RESUME"]["relative_path"]).read_text(
            encoding="utf-8"
        )
        audit_text = (
            BUNDLE_ROOT / outputs["MARKDOWN_AUDIT_PACKAGE"]["relative_path"]
        ).read_text(encoding="utf-8")
        for requirement in analysis["requirements"]:
            with self.subTest(requirement=requirement["id"]):
                self.assertIn(requirement["source_text"], jd_text)
                self.assertIn(requirement["id"], audit_text)
                self.assertTrue(
                    any(
                        item["requirement_id"] == requirement["id"]
                        for item in analysis["evidence_items"]
                    )
                )

        resume_gap = next(
            item for item in analysis["gaps"] if item["category"] == "RESUME_GAP"
        )
        source_evidence = evidence[resume_gap["evidence_item_ids"][0]]
        current_evidence = next(
            item
            for item in analysis["evidence_items"]
            if item["requirement_id"] == resume_gap["requirement_id"]
            and item["source_id"] == analysis["run"]["current_resume_source_id"]
            and set(item["candidate_fact_ids"]) == set(source_evidence["candidate_fact_ids"])
        )
        self.assertIn(current_evidence["source_excerpt"], final_text)
        for gap in analysis["gaps"]:
            if gap["category"] != "TRUE_GAP":
                continue
            requirement = next(
                item for item in analysis["requirements"] if item["id"] == gap["requirement_id"]
            )
            for term in requirement["exact_terms"]:
                self.assertNotIn(term.casefold(), final_text.casefold())

        for result in analysis["qualification_results"]:
            for evidence_id in result["evidence_item_ids"]:
                self.assertEqual(
                    evidence[evidence_id]["source_id"],
                    analysis["run"]["current_resume_source_id"],
                )
        self.assertEqual(analysis["audits"]["ats_parse"]["status"], "PASS")
        self.assertEqual(analysis["audits"]["ats_parse"]["extraction_method"], "TEXT_INPUT")
        self.assertEqual(analysis["audits"]["integrity"]["status"], "PASS")
        self.assertIn("Generated deterministically from the hash-bound structured sidecar", audit_text)
        for item in analysis["evidence_items"]:
            self.assertIn(item["recommended_action"], audit_text)

        sensitive_values = [source["label"] for source in analysis["sources"]]
        sensitive_values.extend(fact["statement"] for fact in analysis["candidate_facts"])
        sensitive_values.extend(
            item["source_excerpt"]
            for item in analysis["evidence_items"]
            if item["source_excerpt"] is not None
        )
        sensitive_values.extend(
            claim["resume_excerpt"] for claim in analysis["claim_provenance"]
        )
        for sensitive in sensitive_values:
            with self.subTest(sensitive=sensitive[:40]):
                self.assertNotIn(sensitive, dashboard)

        self.assertEqual(
            {item["artifact_type"] for item in analysis["outputs"]},
            {"FINAL_RESUME", "MARKDOWN_AUDIT_PACKAGE"},
        )
        self.assertEqual(
            next(
                item["sha256"]
                for item in analysis["outputs"]
                if item["artifact_type"] == "FINAL_RESUME"
            ),
            analysis["run"]["current_resume_hash"],
        )
        for artifact in analysis["outputs"]:
            path = Path(artifact["relative_path"])
            self.assertFalse(path.is_absolute())
            self.assertNotIn("..", path.parts)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "dashboard.md"
            completed = run_path(
                FIXTURE,
                "--bundle-root",
                str(BUNDLE_ROOT),
                "--dashboard",
                str(output),
            )
            payload = self.assert_pass(completed)
            self.assertTrue(payload["dashboard_written"])
            self.assertNotIn("dashboard", payload)
            self.assertIn("# Industry Resume Audit Summary", output.read_text(encoding="utf-8"))

    def test_bundle_root_detects_tampered_and_missing_created_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            shutil.copytree(BUNDLE_ROOT, bundle)
            final_resume = bundle / "outputs" / "final-resume.txt"
            final_resume.write_text(
                final_resume.read_text(encoding="utf-8") + "\nTampered.\n",
                encoding="utf-8",
            )
            self.assert_fails_with(
                run_path(FIXTURE, "--bundle-root", str(bundle)),
                "INDUSTRY_RESUME.BUNDLE_HASH",
            )

        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            shutil.copytree(BUNDLE_ROOT, bundle)
            (bundle / "outputs" / "industry-resume-audit.md").unlink()
            self.assert_fails_with(
                run_path(FIXTURE, "--bundle-root", str(bundle)),
                "INDUSTRY_RESUME.BUNDLE_FILE",
            )

    def test_bundle_rejects_resolved_output_file_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            shutil.copytree(BUNDLE_ROOT, bundle)
            alias = bundle / "outputs" / "audit-alias.md"
            alias.symlink_to("industry-resume-audit.md")
            analysis = load_fixture()
            audit_output = next(
                item
                for item in analysis["outputs"]
                if item["artifact_type"] == "MARKDOWN_AUDIT_PACKAGE"
            )
            analysis["outputs"].append(
                {
                    "artifact_type": "DASHBOARD",
                    "relative_path": "outputs/audit-alias.md",
                    "format": "MD",
                    "sha256": audit_output["sha256"],
                    "status": "CREATED",
                }
            )
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
            self.assert_fails_with(
                run_path(analysis_path, "--bundle-root", str(bundle)),
                "INDUSTRY_RESUME.BUNDLE_PATH",
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            shutil.copytree(BUNDLE_ROOT, bundle)
            case_alias = bundle / "OUTPUTS" / "industry-resume-audit.md"
            canonical = bundle / "outputs" / "industry-resume-audit.md"
            if case_alias.exists() and case_alias.samefile(canonical):
                analysis = load_fixture()
                audit_output = next(
                    item
                    for item in analysis["outputs"]
                    if item["artifact_type"] == "MARKDOWN_AUDIT_PACKAGE"
                )
                analysis["outputs"].append(
                    {
                        "artifact_type": "DASHBOARD",
                        "relative_path": "OUTPUTS/industry-resume-audit.md",
                        "format": "MD",
                        "sha256": audit_output["sha256"],
                        "status": "CREATED",
                    }
                )
                analysis_path = root / "analysis.json"
                analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
                self.assert_fails_with(
                    run_path(analysis_path, "--bundle-root", str(bundle)),
                    "INDUSTRY_RESUME.BUNDLE_PATH",
                )

    def test_final_release_requires_bundle_root(self) -> None:
        self.assert_fails_with(
            run_path(FIXTURE),
            "INDUSTRY_RESUME.BUNDLE_ROOT_REQUIRED",
        )

    def test_explicit_level_three_evidence_allows_met(self) -> None:
        analysis = load_fixture()
        result = requirement_record(analysis, "qualification_results", "REQ-001")
        evidence = next(item for item in analysis["evidence_items"] if item["id"] == "EV-001")
        self.assertEqual(result["classification"], "MET")
        self.assertEqual(evidence["relationship_to_requirement"], "DIRECT")
        self.assertGreaterEqual(evidence["evidence_level"], 2)
        self.assert_pass(run_analysis(analysis))

    def test_qualification_excerpt_and_location_must_match_cited_current_evidence(self) -> None:
        for field, fabricated in (
            ("evidence_excerpt", "Fabricated current-resume excerpt."),
            ("evidence_location", "Fabricated resume section"),
        ):
            with self.subTest(field=field):
                analysis = load_fixture()
                requirement_record(analysis, "qualification_results", "REQ-001")[field] = fabricated
                self.assert_fails_with(
                    run_analysis(analysis),
                    "INDUSTRY_RESUME.QUALIFICATION_PROVENANCE",
                )

    def test_adjacent_experience_cannot_be_classified_met(self) -> None:
        analysis = load_fixture()
        requirement_record(analysis, "qualification_results", "REQ-003")["classification"] = "MET"
        self.assert_fails_with(
            run_analysis(analysis), "INDUSTRY_RESUME.QUALIFICATION_CLASSIFICATION"
        )

    def test_hidden_verified_experience_requires_resume_gap(self) -> None:
        analysis = load_fixture()
        analysis["gaps"] = [item for item in analysis["gaps"] if item["requirement_id"] != "REQ-002"]
        self.assert_fails_with(run_analysis(analysis), "INDUSTRY_RESUME.RESUME_GAP")

    def test_not_met_cannot_contradict_direct_evidence(self) -> None:
        analysis = load_fixture()
        requirement_record(analysis, "eligibility_results", "REQ-001")["classification"] = "not_met"
        self.assert_fails_with(run_analysis(analysis), "INDUSTRY_RESUME.ELIGIBILITY")

    def test_compound_requirement_facets_are_reciprocal_and_acyclic(self) -> None:
        analysis = load_fixture()
        parent = next(item for item in analysis["requirements"] if item["id"] == "REQ-001")
        parent.update(compound=True, facet_ids=["REQ-002", "REQ-005"])
        for facet_id in parent["facet_ids"]:
            next(item for item in analysis["requirements"] if item["id"] == facet_id)[
                "parent_requirement_id"
            ] = "REQ-001"
        self.assert_pass(run_analysis(analysis))

        child = next(item for item in analysis["requirements"] if item["id"] == "REQ-002")
        child["parent_requirement_id"] = "REQ-002"
        self.assert_fails_with(
            run_analysis(analysis), "INDUSTRY_RESUME.REQUIREMENT_STRUCTURE"
        )

    def test_evidence_levels_and_targets_are_bounded_at_four(self) -> None:
        analysis = load_fixture()
        analysis["evidence_items"][0]["evidence_level"] = 5
        analysis["config"]["required_min_level_target"] = 5
        completed = run_analysis(analysis)
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        self.assertIn("INDUSTRY_RESUME.EVIDENCE_TARGET", issue_ids(completed))
        self.assertIn("INDUSTRY_RESUME.EVIDENCE_LEVEL", issue_ids(completed))

    def test_non_absent_evidence_cannot_claim_no_relationship(self) -> None:
        analysis = load_fixture()
        evidence = next(item for item in analysis["evidence_items"] if item["id"] == "EV-003")
        evidence.update(
            status="strong",
            evidence_level=4,
            relationship_to_requirement="NONE",
        )
        analysis["metrics"]["evidence_strength"] = {
            "level_3_4": 4,
            "level_2": 1,
            "level_0_1": 0,
            "total": 5,
        }
        self.assert_fails_with(
            run_analysis(analysis), "INDUSTRY_RESUME.EVIDENCE_CONSISTENCY"
        )

    def test_true_gap_cannot_be_rewritten_as_met(self) -> None:
        analysis = load_fixture()
        analysis["claim_provenance"].append(
            {
                "resume_claim_id": "CLAIM-FABRICATED",
                "requirement_ids": ["REQ-004"],
                "resume_source_id": "SRC-CURRENT",
                "resume_hash": analysis["run"]["current_resume_hash"],
                "resume_location": "Summary",
                "resume_excerpt": "Claimed unsupported technology-transfer experience.",
                "candidate_fact_ids": ["FACT-001"],
                "evidence_item_ids": ["EV-001"],
                "support_status": "SUPPORTED",
                "represents_requirement_as_met": True,
                "revision_relationship": "INTRODUCED",
                "baseline_resume_source_id": None,
                "baseline_resume_hash": None,
                "baseline_resume_excerpt": None,
            }
        )
        self.assert_fails_with(run_analysis(analysis), "INDUSTRY_RESUME.TRUE_GAP")

    def test_ats_reading_order_failure_requires_failure_propagation(self) -> None:
        analysis = load_fixture()
        analysis["audits"]["ats_parse"]["reading_order"] = "FAIL"
        self.assert_fails_with(run_analysis(analysis), "INDUSTRY_RESUME.ATS_STATUS")

        analysis["audits"]["ats_parse"]["status"] = "FAIL"
        gate_record(analysis, "GATE_4").update(status="FAIL", blocking=True)
        analysis["run"]["overall_status"] = "FAIL"
        self.assert_pass(run_analysis(analysis))

    def test_invented_metric_requires_integrity_failure(self) -> None:
        analysis = load_fixture()
        analysis["audits"]["integrity"]["invented_metric_claim_ids"] = ["CLAIM-001"]
        self.assert_fails_with(run_analysis(analysis), "INDUSTRY_RESUME.INTEGRITY_STATUS")

        analysis["audits"]["integrity"]["status"] = "FAIL"
        gate_record(analysis, "GATE_8").update(status="FAIL", blocking=True)
        analysis["run"]["overall_status"] = "FAIL"
        self.assert_pass(run_analysis(analysis))

    def test_explicit_seniority_directness_drift_and_caveat_integrity_fields(self) -> None:
        fields = (
            "inflated_seniority_claim_ids",
            "unsupported_direct_experience_claim_ids",
            "semantic_drift_claim_ids",
            "caveat_loss_claim_ids",
        )
        for field in fields:
            with self.subTest(field=field):
                analysis = load_fixture()
                analysis["audits"]["integrity"][field] = ["CLAIM-001"]
                self.assert_fails_with(
                    run_analysis(analysis), "INDUSTRY_RESUME.INTEGRITY_STATUS"
                )

    def test_duplicate_concept_findings_require_integrity_warning(self) -> None:
        analysis = load_fixture()
        analysis["audits"]["integrity"]["duplicated_concept_findings"] = [
            "Assay-development wording repeats without adding evidence."
        ]
        self.assert_fails_with(
            run_analysis(analysis), "INDUSTRY_RESUME.INTEGRITY_STATUS"
        )

        analysis["audits"]["integrity"]["status"] = "PASS_WITH_WARNINGS"
        gate_record(analysis, "GATE_8")["status"] = "PASS_WITH_WARNINGS"
        self.assert_pass(run_analysis(analysis))

    def test_evaluator_retry_and_one_schema_repair_exhaustion_must_propagate(self) -> None:
        over_repaired = load_fixture()
        over_repaired["evaluator_runs"][1].update(
            schema_repair_attempted=True,
            schema_repair_count=2,
        )
        self.assert_fails_with(
            run_analysis(over_repaired), "INDUSTRY_RESUME.EVALUATOR_REPAIR"
        )

        analysis = load_fixture()
        evaluator = next(
            item for item in analysis["evaluator_runs"] if item["gate_id"] == "GATE_5"
        )
        evaluator.update(
            status="FAILED",
            attempt_count=2,
            retry_count=1,
            schema_repair_attempted=True,
            schema_repair_count=1,
            completed_artifacts_preserved=True,
            failure_type="STRUCTURED_OUTPUT",
            failure_reason="Structured output remained invalid after one repair.",
        )
        self.assert_fails_with(
            run_analysis(analysis), "INDUSTRY_RESUME.EVALUATOR_PROPAGATION"
        )

        analysis["audits"]["ai_recruiter"]["status"] = "FAIL"
        gate_record(analysis, "GATE_5").update(status="FAIL", blocking=True)
        analysis["run"]["overall_status"] = "FAIL"
        self.assert_pass(run_analysis(analysis))

    def test_top_third_mismatch_requires_recruiter_scan_failure(self) -> None:
        analysis = load_fixture()
        analysis["audits"]["top_third"]["target_role_represented"] = False
        self.assert_fails_with(run_analysis(analysis), "INDUSTRY_RESUME.RECRUITER_SCAN_STATUS")

        analysis["audits"]["top_third"]["status"] = "FAIL"
        gate_record(analysis, "GATE_6").update(status="FAIL", blocking=True)
        analysis["run"]["overall_status"] = "FAIL"
        self.assert_pass(run_analysis(analysis))

    def test_gate6_strong_requires_early_terminology_and_skimability(self) -> None:
        for field in ("relevant_terms_visible_early", "easy_to_skim"):
            with self.subTest(field=field):
                analysis = load_fixture()
                analysis["audits"]["human_recruiter"][field] = False
                self.assert_fails_with(
                    run_analysis(analysis), "INDUSTRY_RESUME.RECRUITER_SCAN_STATUS"
                )

                analysis["audits"]["human_recruiter"].update(
                    rating="ACCEPTABLE", status="PASS_WITH_WARNINGS"
                )
                gate_record(analysis, "GATE_6")["status"] = "PASS_WITH_WARNINGS"
                self.assert_pass(run_analysis(analysis))

    def test_gate6_requires_three_capabilities_and_five_top_domains(self) -> None:
        for rating in ("STRONG", "ACCEPTABLE"):
            for audit_field, list_field, retained_count in (
                ("human_recruiter", "top_capabilities", 2),
                ("top_third", "top_domains", 4),
            ):
                with self.subTest(
                    rating=rating,
                    audit=audit_field,
                    field=list_field,
                ):
                    analysis = load_fixture()
                    status = "PASS" if rating == "STRONG" else "PASS_WITH_WARNINGS"
                    analysis["audits"][audit_field].update(
                        rating=rating,
                        status=status,
                    )
                    analysis["audits"][audit_field][list_field] = analysis["audits"][
                        audit_field
                    ][list_field][:retained_count]
                    gate_record(analysis, "GATE_6")["status"] = status
                    self.assert_fails_with(
                        run_analysis(analysis),
                        "INDUSTRY_RESUME.RECRUITER_SCAN_STATUS",
                    )

    def test_gate7_dimensions_fail_closed_on_missing_duplicate_or_invalid_na(self) -> None:
        missing = load_fixture()
        missing["audits"]["hiring_manager"]["dimension_results"].pop()
        self.assert_fails_with(
            run_analysis(missing), "INDUSTRY_RESUME.HIRING_MANAGER_DIMENSIONS"
        )

        duplicate = load_fixture()
        duplicate["audits"]["hiring_manager"]["dimension_results"].append(
            dict(dimension_record(duplicate, "depth"))
        )
        self.assert_fails_with(
            run_analysis(duplicate), "INDUSTRY_RESUME.HIRING_MANAGER_DIMENSIONS"
        )

        invalid_na = load_fixture()
        invalid_na["audits"]["hiring_manager"]["target_context"] = "NON_RESEARCH"
        dimension_record(invalid_na, "ownership").update(
            applicability="NOT_APPLICABLE", rating=None
        )
        self.assert_fails_with(
            run_analysis(invalid_na), "INDUSTRY_RESUME.HIRING_MANAGER_APPLICABILITY"
        )

    def test_scientifically_inaccurate_term_replacement_is_rejected(self) -> None:
        analysis = load_fixture()
        alignment = requirement_record(analysis, "semantic_alignments", "REQ-003")
        alignment.update(
            candidate_term="lentiviral vector production",
            industry_wording="HIV infection studies",
            relationship="NOT_EQUIVALENT",
            approved_for_revision=True,
        )
        self.assert_fails_with(run_analysis(analysis), "INDUSTRY_RESUME.SEMANTIC_EQUIVALENCE")

    def test_required_synthetic_regression_variations_validate(self) -> None:
        variations: list[tuple[str, dict[str, Any], Any]] = []

        no_preferred = load_fixture()
        for requirement in no_preferred["requirements"]:
            if requirement["priority"] == "preferred":
                requirement["priority"] = "contextual"
        no_preferred["target"]["preferred_requirement_ids"] = []
        no_preferred["metrics"]["preferred_qualifications"] = {
            "met": 0,
            "partial": 0,
            "not_found": 0,
            "total": 0,
        }
        variations.append(
            (
                "no preferred qualifications",
                no_preferred,
                lambda value: self.assertFalse(
                    any(item["priority"] == "preferred" for item in value["requirements"])
                ),
            )
        )

        duties = load_fixture()
        requirement = next(item for item in duties["requirements"] if item["id"] == "REQ-001")
        requirement["source_text"] = "Lead cross-functional assay development."
        duties["target"]["responsibilities"] = [
            "lead cross-functional assay development",
            "optimize experimental processes",
        ]
        variations.append(
            (
                "required qualification embedded in duties",
                duties,
                lambda value: self.assertEqual(
                    next(item for item in value["requirements"] if item["id"] == "REQ-001")[
                        "priority"
                    ],
                    "required",
                ),
            )
        )

        research_biotech = load_fixture()
        research_biotech["target"].update(
            function="Biotechnology research and development",
            therapeutic_areas=["synthetic therapeutic area"],
        )
        research_biotech["sources"][0]["label"] = "Synthetic research-biotech role"
        variations.append(
            (
                "research biotech",
                research_biotech,
                lambda value: self.assertTrue(
                    all(
                        item["applicability"] == "APPLICABLE"
                        for item in value["audits"]["hiring_manager"]["dimension_results"]
                    )
                ),
            )
        )

        non_research = load_fixture()
        non_research["target"].update(
            job_title="Pharma Operations Partner",
            seniority="Individual contributor",
            function="Non-research pharmaceutical operations",
        )
        non_research["audits"]["hiring_manager"]["target_context"] = "NON_RESEARCH"
        scientific_only = {
            "depth",
            "mechanistic_thinking",
            "development",
            "rigor",
            "innovation",
            "translation",
            "output_relevance",
        }
        for dimension in non_research["audits"]["hiring_manager"]["dimension_results"]:
            if dimension["dimension"] in scientific_only:
                dimension.update(
                    applicability="NOT_APPLICABLE",
                    rating=None,
                    evidence="Scientific-only dimension is not applicable to this target role.",
                )
        non_research["audits"]["hiring_manager"]["technical_depth"] = None
        variations.append(
            (
                "non-research pharma with scientific N/A",
                non_research,
                lambda value: self.assertEqual(
                    {
                        item["dimension"]
                        for item in value["audits"]["hiring_manager"]["dimension_results"]
                        if item["applicability"] == "NOT_APPLICABLE"
                    },
                    scientific_only,
                ),
            )
        )

        for title in ("Scientist", "Senior Scientist"):
            seniority = load_fixture()
            seniority["target"]["job_title"] = f"{title}, Assay Development"
            seniority["target"]["seniority"] = title
            seniority["audits"]["human_recruiter"]["evidence"] = (
                f"The first third consistently signals the {title} target without inflation."
            )
            variations.append(
                (
                    f"{title} without seniority inflation",
                    seniority,
                    lambda value, expected=title: self.assertEqual(
                        (
                            value["target"]["seniority"],
                            value["audits"]["integrity"]["inflated_seniority_claim_ids"],
                        ),
                        (expected, []),
                    ),
                )
            )

        minimal_leadership = load_fixture()
        dimension_record(minimal_leadership, "leadership")["rating"] = "ACCEPTABLE"
        minimal_leadership["audits"]["hiring_manager"].update(
            rating="ACCEPTABLE", status="PASS_WITH_WARNINGS"
        )
        gate_record(minimal_leadership, "GATE_7")["status"] = "PASS_WITH_WARNINGS"
        variations.append(
            (
                "minimal leadership",
                minimal_leadership,
                lambda value: self.assertEqual(
                    dimension_record(value, "leadership")["rating"], "ACCEPTABLE"
                ),
            )
        )

        no_metrics = load_fixture()
        no_metrics["candidate_facts"][0]["notes"] = (
            "No quantitative outcome was supplied; qualitative scope is retained."
        )
        variations.append(
            (
                "no quantitative metrics",
                no_metrics,
                lambda value: self.assertTrue(
                    all(
                        not any(character.isdigit() for character in claim["resume_excerpt"])
                        for claim in value["claim_provenance"]
                    )
                ),
            )
        )

        academic_cv = load_fixture()
        profile = next(item for item in academic_cv["sources"] if item["source_id"] == "SRC-PROFILE")
        profile.update(source_type="CV", label="Synthetic academic CV evidence")
        next(
            item for item in academic_cv["evidence_items"] if item["id"] == "EV-002-SOURCE"
        )["source_type"] = "cv"
        variations.append(
            (
                "academic CV evidence",
                academic_cv,
                lambda value: self.assertEqual(
                    next(
                        item
                        for item in value["sources"]
                        if item["source_id"] == "SRC-PROFILE"
                    )["source_type"],
                    "CV",
                ),
            )
        )

        for name, analysis, meaningful_assertion in variations:
            with self.subTest(variation=name):
                meaningful_assertion(analysis)
                self.assert_pass(run_analysis(analysis))

    def test_gate_failure_must_be_blocking_and_propagate_to_overall_status(self) -> None:
        analysis = load_fixture()
        gate_record(analysis, "GATE_2").update(status="FAIL", blocking=False)
        self.assert_fails_with(run_analysis(analysis), "INDUSTRY_RESUME.STATUS_PROPAGATION")

    def test_non_failed_gate_cannot_be_marked_blocking(self) -> None:
        analysis = load_fixture()
        disable_gate(analysis, "GATE_6")
        gate_record(analysis, "GATE_6")["blocking"] = True
        self.assert_fails_with(
            run_analysis(analysis), "INDUSTRY_RESUME.STATUS_PROPAGATION"
        )

    def test_candidate_evidence_sources_require_authority_and_type_consistency(self) -> None:
        unauthorized_fact = load_fixture()
        unauthorized_fact["candidate_facts"][0]["source_id"] = "SRC-JD"
        self.assert_fails_with(
            run_analysis(unauthorized_fact), "INDUSTRY_RESUME.EVIDENCE_AUTHORITY"
        )

        unauthorized_evidence = load_fixture()
        current = next(
            item for item in unauthorized_evidence["sources"] if item["source_id"] == "SRC-CURRENT"
        )
        current["candidate_evidence_allowed"] = False
        self.assert_fails_with(
            run_analysis(unauthorized_evidence), "INDUSTRY_RESUME.EVIDENCE_AUTHORITY"
        )

        mismatched_type = load_fixture()
        next(item for item in mismatched_type["evidence_items"] if item["id"] == "EV-001")[
            "source_type"
        ] = "cv"
        self.assert_fails_with(
            run_analysis(mismatched_type), "INDUSTRY_RESUME.EVIDENCE_SOURCE_TYPE"
        )

        for field in ("source_location", "source_excerpt"):
            with self.subTest(field=field):
                missing_provenance = load_fixture()
                next(
                    item
                    for item in missing_provenance["evidence_items"]
                    if item["id"] == "EV-001"
                )[field] = None
                self.assert_fails_with(
                    run_analysis(missing_provenance), "INDUSTRY_RESUME.PROVENANCE"
                )

        tampered_fact_hash = load_fixture()
        tampered_fact_hash["candidate_facts"][0]["source_hash"] = (
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        self.assert_fails_with(
            run_analysis(tampered_fact_hash), "INDUSTRY_RESUME.PROVENANCE"
        )

        tampered_evidence_hash = load_fixture()
        tampered_evidence_hash["evidence_items"][0]["source_hash"] = (
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        self.assert_fails_with(
            run_analysis(tampered_evidence_hash), "INDUSTRY_RESUME.PROVENANCE"
        )

    def test_candidate_truth_sources_are_authoritative_upstream_and_not_jd_aliases(self) -> None:
        non_authoritative = load_fixture()
        profile = next(
            item
            for item in non_authoritative["sources"]
            if item["source_id"] == "SRC-PROFILE"
        )
        profile["content_authority"] = False
        self.assert_fails_with(
            run_analysis(non_authoritative), "INDUSTRY_RESUME.EVIDENCE_AUTHORITY"
        )

        current_resume_fact = load_fixture()
        current = next(
            item
            for item in current_resume_fact["sources"]
            if item["source_id"] == "SRC-CURRENT"
        )
        fact = next(
            item
            for item in current_resume_fact["candidate_facts"]
            if item["fact_id"] == "FACT-002"
        )
        fact.update(
            source_id="SRC-CURRENT",
            source_hash=current["sha256"],
            source_location="Experience, role two",
        )
        claim = next(
            item
            for item in current_resume_fact["claim_provenance"]
            if item["resume_claim_id"] == "CLAIM-002"
        )
        claim["evidence_item_ids"] = ["EV-002-RESUME"]
        self.assert_fails_with(
            run_analysis(current_resume_fact), "INDUSTRY_RESUME.PROVENANCE_CIRCULAR"
        )

        jd_alias = load_fixture()
        jd = next(item for item in jd_alias["sources"] if item["source_id"] == "SRC-JD")
        profile = next(
            item for item in jd_alias["sources"] if item["source_id"] == "SRC-PROFILE"
        )
        profile.update(relative_path=jd["relative_path"], sha256=jd["sha256"])
        fact = next(
            item for item in jd_alias["candidate_facts"] if item["fact_id"] == "FACT-002"
        )
        fact["source_hash"] = jd["sha256"]
        evidence = next(
            item for item in jd_alias["evidence_items"] if item["id"] == "EV-002-SOURCE"
        )
        evidence.update(
            source_hash=jd["sha256"],
            source_excerpt="Apply design of experiments to process optimization.",
        )
        self.assert_fails_with(run_analysis(jd_alias), "INDUSTRY_RESUME.SOURCE_ALIAS")

        current_alias = load_fixture()
        current = next(
            item for item in current_alias["sources"] if item["source_id"] == "SRC-CURRENT"
        )
        profile = next(
            item for item in current_alias["sources"] if item["source_id"] == "SRC-PROFILE"
        )
        profile.update(relative_path=current["relative_path"], sha256=current["sha256"])
        fact = next(
            item
            for item in current_alias["candidate_facts"]
            if item["fact_id"] == "FACT-002"
        )
        fact.update(
            statement="Applied design of experiments to optimize a multivariable process.",
            source_hash=current["sha256"],
        )
        evidence = next(
            item
            for item in current_alias["evidence_items"]
            if item["id"] == "EV-002-SOURCE"
        )
        evidence.update(
            source_hash=current["sha256"],
            source_excerpt="Applied design of experiments to optimize a multivariable process.",
        )
        self.assert_fails_with(
            run_analysis(current_alias), "INDUSTRY_RESUME.SOURCE_ALIAS"
        )

        extracted_alias = load_fixture()
        profile = next(
            item for item in extracted_alias["sources"] if item["source_id"] == "SRC-PROFILE"
        )
        jd = next(
            item for item in extracted_alias["sources"] if item["source_id"] == "SRC-JD"
        )
        profile.update(
            extracted_text_relative_path=jd["relative_path"],
            extracted_text_sha256=jd["sha256"],
        )
        self.assert_fails_with(
            run_analysis(extracted_alias), "INDUSTRY_RESUME.SOURCE_ALIAS"
        )

    def test_claim_revision_relationship_cannot_hide_circular_provenance(self) -> None:
        analysis = load_fixture()
        claim = next(
            item
            for item in analysis["claim_provenance"]
            if item["resume_claim_id"] == "CLAIM-002"
        )
        baseline = next(
            item for item in analysis["sources"] if item["source_id"] == "SRC-BASELINE"
        )
        claim.update(
            revision_relationship="UNCHANGED",
            baseline_resume_source_id=baseline["source_id"],
            baseline_resume_hash=baseline["sha256"],
            baseline_resume_excerpt=claim["resume_excerpt"],
        )
        self.assert_fails_with(
            run_analysis(analysis), "INDUSTRY_RESUME.BUNDLE_CLAIM_BASELINE"
        )

        strengthened = load_fixture()
        claim = next(
            item
            for item in strengthened["claim_provenance"]
            if item["resume_claim_id"] == "CLAIM-002"
        )
        claim.update(
            revision_relationship="STRENGTHENED",
            baseline_resume_source_id=baseline["source_id"],
            baseline_resume_hash=baseline["sha256"],
            baseline_resume_excerpt=claim["resume_excerpt"],
        )
        self.assert_fails_with(
            run_analysis(strengthened), "INDUSTRY_RESUME.REVISION_PROVENANCE"
        )

        omitted = load_fixture()
        omitted["claim_provenance"] = [
            item
            for item in omitted["claim_provenance"]
            if item["resume_claim_id"] != "CLAIM-002"
        ]
        self.assert_fails_with(
            run_analysis(omitted), "INDUSTRY_RESUME.CLAIM_COVERAGE"
        )

        relabeled = load_fixture()
        claim = next(
            item
            for item in relabeled["claim_provenance"]
            if item["resume_claim_id"] == "CLAIM-002"
        )
        claim.update(
            requirement_ids=["REQ-003"],
            resume_location="Research, project three",
            resume_excerpt="Applied related analytical methods in an academic setting.",
            candidate_fact_ids=["FACT-003"],
            evidence_item_ids=["EV-003"],
            represents_requirement_as_met=False,
            revision_relationship="UNCHANGED",
            baseline_resume_source_id=baseline["source_id"],
            baseline_resume_hash=baseline["sha256"],
            baseline_resume_excerpt="Applied related analytical methods in an academic setting.",
        )
        self.assert_fails_with(
            run_analysis(relabeled), "INDUSTRY_RESUME.CLAIM_COVERAGE"
        )

    def test_revision_diff_requires_atomic_claim_and_removal_coverage(self) -> None:
        deleted_name = run_modified_current_resume(
            load_fixture(), lambda text: text.replace("Synthetic Candidate\n", "", 1)
        )
        self.assert_fails_with(deleted_name, "INDUSTRY_RESUME.CLAIM_COVERAGE")

        duplicated_unchanged_line = run_modified_current_resume(
            load_fixture(),
            lambda text: text
            + "\n- Presented technical decisions to partner teams and senior reviewers.\n",
        )
        self.assert_fails_with(
            duplicated_unchanged_line, "INDUSTRY_RESUME.CLAIM_COVERAGE"
        )

        unchanged_block = (
            "- Applied related analytical methods in an academic setting.\n"
            "- Presented technical decisions to partner teams and senior reviewers.\n"
        )
        cross_section_move = run_modified_current_resume(
            load_fixture(),
            lambda text: text.replace(unchanged_block, "", 1).replace(
                "Summary\n", unchanged_block + "\nSummary\n", 1
            ),
        )
        self.assert_fails_with(cross_section_move, "INDUSTRY_RESUME.CLAIM_COVERAGE")

        reordered_within_section = run_modified_current_resume(
            load_fixture(),
            lambda text: text.replace(
                unchanged_block,
                (
                    "- Presented technical decisions to partner teams and senior reviewers.\n"
                    "- Applied related analytical methods in an academic setting.\n"
                ),
                1,
            ),
        )
        self.assert_pass(reordered_within_section)

        def blank_separated_headings(text: str) -> str:
            return text.replace("Summary\n", "Summary\n\n", 1).replace(
                "Experience\n", "Experience\n\n", 1
            )

        blank_line_formatting_only = run_modified_resume_pair(
            load_fixture(), blank_separated_headings, blank_separated_headings
        )
        self.assert_pass(blank_line_formatting_only)

        def move_between_blank_separated_sections(text: str) -> str:
            formatted = blank_separated_headings(text)
            return formatted.replace(unchanged_block, "", 1).replace(
                "Summary\n\n", "Summary\n\n" + unchanged_block + "\n", 1
            )

        blank_line_cross_section_move = run_modified_resume_pair(
            load_fixture(),
            blank_separated_headings,
            move_between_blank_separated_sections,
        )
        self.assert_fails_with(
            blank_line_cross_section_move, "INDUSTRY_RESUME.CLAIM_COVERAGE"
        )

        def add_same_title_employers(text: str) -> str:
            return text.replace(
                "Experience\n",
                "Experience\nCompany A\nSenior Scientist\n",
                1,
            ).replace(
                "- Presented technical decisions to partner teams and senior reviewers.\n",
                (
                    "Company B\nSenior Scientist\n"
                    "- Presented technical decisions to partner teams and senior reviewers.\n"
                ),
                1,
            )

        same_title_employer_formatting = run_modified_resume_pair(
            load_fixture(), add_same_title_employers, add_same_title_employers
        )
        self.assert_pass(same_title_employer_formatting)

        def move_between_same_title_employers(text: str) -> str:
            formatted = add_same_title_employers(text)
            moved_line = "- Applied related analytical methods in an academic setting.\n"
            presented_line = (
                "- Presented technical decisions to partner teams and senior reviewers.\n"
            )
            return formatted.replace(moved_line, "", 1).replace(
                presented_line, presented_line + moved_line, 1
            )

        same_title_cross_employer_move = run_modified_resume_pair(
            load_fixture(),
            add_same_title_employers,
            move_between_same_title_employers,
        )
        self.assert_fails_with(
            same_title_cross_employer_move, "INDUSTRY_RESUME.CLAIM_COVERAGE"
        )

        def add_blank_separated_same_title_employers(text: str) -> str:
            return text.replace(
                "Experience\n",
                "Experience\n\nCompany A\n\nSenior Scientist\n\n",
                1,
            ).replace(
                "- Presented technical decisions to partner teams and senior reviewers.\n",
                (
                    "\nCompany B\n\nSenior Scientist\n\n"
                    "- Presented technical decisions to partner teams and senior reviewers.\n"
                ),
                1,
            )

        blank_separated_employer_formatting = run_modified_resume_pair(
            load_fixture(),
            add_blank_separated_same_title_employers,
            add_blank_separated_same_title_employers,
        )
        self.assert_pass(blank_separated_employer_formatting)

        def move_between_blank_separated_same_title_employers(text: str) -> str:
            formatted = add_blank_separated_same_title_employers(text)
            moved_line = "- Applied related analytical methods in an academic setting.\n"
            presented_line = (
                "- Presented technical decisions to partner teams and senior reviewers.\n"
            )
            return formatted.replace(moved_line, "", 1).replace(
                presented_line, presented_line + moved_line, 1
            )

        blank_separated_same_title_move = run_modified_resume_pair(
            load_fixture(),
            add_blank_separated_same_title_employers,
            move_between_blank_separated_same_title_employers,
        )
        self.assert_fails_with(
            blank_separated_same_title_move, "INDUSTRY_RESUME.CLAIM_COVERAGE"
        )

        def add_nested_markdown_employers(text: str) -> str:
            return text.replace(
                "Experience\n",
                "Experience\n- Company A — Senior Scientist\n",
                1,
            ).replace(
                "- Led", "  - Led", 1
            ).replace(
                "- Applied", "  - Applied"
            ).replace(
                "- Presented technical decisions to partner teams and senior reviewers.\n",
                (
                    "- Company B — Senior Scientist\n"
                    "  - Presented technical decisions to partner teams and senior reviewers.\n"
                ),
                1,
            )

        nested_markdown_employer_formatting = run_modified_resume_pair(
            load_fixture(),
            add_nested_markdown_employers,
            add_nested_markdown_employers,
        )
        self.assert_pass(nested_markdown_employer_formatting)

        def move_between_nested_markdown_employers(text: str) -> str:
            formatted = add_nested_markdown_employers(text)
            moved_line = "  - Applied related analytical methods in an academic setting.\n"
            presented_line = (
                "  - Presented technical decisions to partner teams and senior reviewers.\n"
            )
            return formatted.replace(moved_line, "", 1).replace(
                presented_line, presented_line + moved_line, 1
            )

        nested_markdown_cross_employer_move = run_modified_resume_pair(
            load_fixture(),
            add_nested_markdown_employers,
            move_between_nested_markdown_employers,
        )
        self.assert_fails_with(
            nested_markdown_cross_employer_move, "INDUSTRY_RESUME.CLAIM_COVERAGE"
        )

        def add_plus_nested_markdown_employers(text: str) -> str:
            return add_nested_markdown_employers(text).replace(
                "- Company", "+ Company"
            ).replace("  - ", "  + ")

        plus_nested_markdown_formatting = run_modified_resume_pair(
            load_fixture(),
            add_plus_nested_markdown_employers,
            add_plus_nested_markdown_employers,
        )
        self.assert_pass(plus_nested_markdown_formatting)

        def move_between_plus_nested_markdown_employers(text: str) -> str:
            formatted = add_plus_nested_markdown_employers(text)
            moved_line = "  + Applied related analytical methods in an academic setting.\n"
            presented_line = (
                "  + Presented technical decisions to partner teams and senior reviewers.\n"
            )
            return formatted.replace(moved_line, "", 1).replace(
                presented_line, presented_line + moved_line, 1
            )

        plus_nested_markdown_cross_employer_move = run_modified_resume_pair(
            load_fixture(),
            add_plus_nested_markdown_employers,
            move_between_plus_nested_markdown_employers,
        )
        self.assert_fails_with(
            plus_nested_markdown_cross_employer_move,
            "INDUSTRY_RESUME.CLAIM_COVERAGE",
        )

        one_claim_for_multiple_changes = load_fixture()
        baseline = next(
            item
            for item in one_claim_for_multiple_changes["sources"]
            if item["source_id"] == "SRC-BASELINE"
        )
        current = next(
            item
            for item in one_claim_for_multiple_changes["sources"]
            if item["source_id"] == "SRC-CURRENT"
        )
        preserved = [
            item
            for item in one_claim_for_multiple_changes["claim_provenance"]
            if item["revision_relationship"] == "UNCHANGED"
        ]
        one_claim_for_multiple_changes["claim_provenance"] = [
            {
                "resume_claim_id": "CLAIM-ALL",
                "requirement_ids": ["REQ-001", "REQ-002", "REQ-005"],
                "resume_source_id": "SRC-CURRENT",
                "resume_hash": current["sha256"],
                "resume_location": "Entire current resume",
                "resume_excerpt": (
                    BUNDLE_ROOT / current["relative_path"]
                ).read_text(encoding="utf-8"),
                "candidate_fact_ids": ["FACT-001", "FACT-002", "FACT-005"],
                "evidence_item_ids": [
                    "EV-001",
                    "EV-002-SOURCE",
                    "EV-002-RESUME",
                    "EV-005",
                ],
                "support_status": "SUPPORTED",
                "represents_requirement_as_met": True,
                "revision_relationship": "INTRODUCED",
                "baseline_resume_source_id": None,
                "baseline_resume_hash": None,
                "baseline_resume_excerpt": None,
            },
            *preserved,
        ]
        one_claim_for_multiple_changes["removed_claims"] = [
            {
                "removal_id": "REMOVE-SUMMARY",
                "requirement_ids": ["REQ-001", "REQ-005"],
                "baseline_resume_source_id": baseline["source_id"],
                "baseline_resume_hash": baseline["sha256"],
                "baseline_excerpt": "Assay-development scientist with cross-functional technical leadership.",
                "reason": "Authorized replacement by a supported summary claim.",
                "authorization_verified": True,
            },
            {
                "removal_id": "REMOVE-EXPERIENCE",
                "requirement_ids": ["REQ-001"],
                "baseline_resume_source_id": baseline["source_id"],
                "baseline_resume_hash": baseline["sha256"],
                "baseline_excerpt": "Led cross-functional assay development from design through validation.",
                "reason": "Authorized replacement by a supported experience claim.",
                "authorization_verified": True,
            },
        ]
        self.assert_fails_with(
            run_analysis(one_claim_for_multiple_changes),
            "INDUSTRY_RESUME.CLAIM_COVERAGE",
        )

        invalid_removal = load_fixture()
        invalid_removal["removed_claims"] = [
            {
                "removal_id": "REMOVE-FABRICATED",
                "requirement_ids": ["REQ-001"],
                "baseline_resume_source_id": baseline["source_id"],
                "baseline_resume_hash": baseline["sha256"],
                "baseline_excerpt": "Fabricated deletion absent from the baseline resume.",
                "reason": "Synthetic negative fixture.",
                "authorization_verified": True,
            }
        ]
        self.assert_fails_with(
            run_analysis(invalid_removal),
            "INDUSTRY_RESUME.BUNDLE_CLAIM_BASELINE",
        )

    def test_candidate_fact_statement_is_bound_to_authoritative_source_bytes(self) -> None:
        analysis = load_fixture()
        next(
            item
            for item in analysis["candidate_facts"]
            if item["fact_id"] == "FACT-002"
        )["statement"] = "Fabricated candidate fact absent from the bound source."
        self.assert_fails_with(
            run_analysis(analysis), "INDUSTRY_RESUME.BUNDLE_CANDIDATE_FACT"
        )

    def test_bundle_binds_evidence_and_claim_excerpts_to_the_current_resume(self) -> None:
        fabricated_evidence = load_fixture()
        next(
            item
            for item in fabricated_evidence["evidence_items"]
            if item["id"] == "EV-001"
        )["source_excerpt"] = "Fabricated current-resume evidence excerpt."
        self.assert_fails_with(
            run_analysis(fabricated_evidence),
            "INDUSTRY_RESUME.BUNDLE_EVIDENCE",
        )

        fabricated_claim = load_fixture()
        next(
            item
            for item in fabricated_claim["claim_provenance"]
            if item["resume_claim_id"] == "CLAIM-001"
        )["resume_excerpt"] = "Fabricated current-resume claim excerpt."
        self.assert_fails_with(
            run_analysis(fabricated_claim),
            "INDUSTRY_RESUME.BUNDLE_CLAIM",
        )

    def test_revised_resume_requires_claim_provenance(self) -> None:
        analysis = load_fixture()
        analysis["claim_provenance"] = []
        self.assert_fails_with(run_analysis(analysis), "INDUSTRY_RESUME.PROVENANCE")

        falsified_unchanged = load_fixture()
        falsified_unchanged["run"].update(
            revisions_applied=False,
            revision_cycle=0,
            authorization_verified=False,
        )
        falsified_unchanged["claim_provenance"] = []
        falsified_unchanged["removed_claims"] = []
        self.assert_fails_with(
            run_analysis(falsified_unchanged),
            "INDUSTRY_RESUME.REVISION_PROVENANCE",
        )

    def test_claim_proof_must_crosslink_and_bind_the_current_resume(self) -> None:
        unrelated = load_fixture()
        claim = next(
            item
            for item in unrelated["claim_provenance"]
            if item["resume_claim_id"] == "CLAIM-001"
        )
        claim.update(candidate_fact_ids=["FACT-005"], evidence_item_ids=["EV-005"])
        self.assert_fails_with(
            run_analysis(unrelated), "INDUSTRY_RESUME.PROVENANCE_CROSSLINK"
        )

        uncovered_requirement = load_fixture()
        next(
            item
            for item in uncovered_requirement["claim_provenance"]
            if item["resume_claim_id"] == "CLAIM-001"
        )["requirement_ids"].append("REQ-005")
        self.assert_fails_with(
            run_analysis(uncovered_requirement),
            "INDUSTRY_RESUME.PROVENANCE_CROSSLINK",
        )

        stale = load_fixture()
        next(
            item
            for item in stale["claim_provenance"]
            if item["resume_claim_id"] == "CLAIM-001"
        )["resume_hash"] = (
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        self.assert_fails_with(run_analysis(stale), "INDUSTRY_RESUME.PROVENANCE")

    def test_evidence_references_cannot_cross_requirement_boundaries(self) -> None:
        analysis = load_fixture()
        requirement_record(analysis, "eligibility_results", "REQ-003")[
            "evidence_item_ids"
        ] = ["EV-001"]
        self.assert_fails_with(
            run_analysis(analysis), "INDUSTRY_RESUME.EVIDENCE_CROSSLINK"
        )

    def test_not_met_and_required_not_found_preserve_one_true_gap(self) -> None:
        false_flag = load_fixture()
        requirement_record(false_flag, "eligibility_results", "REQ-004")["true_gap"] = False
        self.assert_fails_with(run_analysis(false_flag), "INDUSTRY_RESUME.TRUE_GAP")

        missing_gap = load_fixture()
        missing_gap["gaps"] = [
            item for item in missing_gap["gaps"] if item["requirement_id"] != "REQ-004"
        ]
        self.assert_fails_with(run_analysis(missing_gap), "INDUSTRY_RESUME.TRUE_GAP")

        duplicate_gap = load_fixture()
        extra = dict(
            next(item for item in duplicate_gap["gaps"] if item["requirement_id"] == "REQ-004")
        )
        extra["gap_id"] = "GAP-004-DUPLICATE"
        duplicate_gap["gaps"].append(extra)
        self.assert_fails_with(
            run_analysis(duplicate_gap), "INDUSTRY_RESUME.GAP_TAXONOMY"
        )

    def test_non_supported_current_claim_requires_integrity_failure_propagation(self) -> None:
        analysis = load_fixture()
        next(
            item
            for item in analysis["claim_provenance"]
            if item["resume_claim_id"] == "CLAIM-001"
        )["support_status"] = "BLOCKED"
        self.assert_fails_with(
            run_analysis(analysis), "INDUSTRY_RESUME.CLAIM_STATUS_PROPAGATION"
        )

        analysis["audits"]["integrity"]["unsupported_claim_ids"] = ["CLAIM-001"]
        analysis["audits"]["integrity"]["status"] = "FAIL"
        gate_record(analysis, "GATE_8").update(status="FAIL", blocking=True)
        analysis["run"]["overall_status"] = "FAIL"
        self.assert_pass(run_analysis(analysis))

    def test_enabled_and_disabled_gate_audits_are_coherent(self) -> None:
        audit_fields = {
            "GATE_4": ("ats_parse",),
            "GATE_5": ("ai_recruiter",),
            "GATE_6": ("human_recruiter", "top_third"),
            "GATE_7": ("hiring_manager",),
        }
        for gate_id, fields in audit_fields.items():
            with self.subTest(gate_id=gate_id, state="disabled-valid"):
                analysis = load_fixture()
                if gate_id == "GATE_4":
                    analysis["run"]["operation"] = "IMPLEMENT"
                preserved = {field: analysis["audits"][field] for field in fields}
                disable_gate(analysis, gate_id)
                self.assertTrue(all(analysis["audits"][field] is None for field in fields))
                self.assert_pass(run_analysis(analysis))

            with self.subTest(gate_id=gate_id, state="disabled-with-audit"):
                analysis["audits"][fields[0]] = preserved[fields[0]]
                self.assert_fails_with(
                    run_analysis(analysis), "INDUSTRY_RESUME.AUDIT_CONFIG"
                )

        enabled_missing = load_fixture()
        enabled_missing["audits"]["hiring_manager"] = None
        self.assert_fails_with(
            run_analysis(enabled_missing), "INDUSTRY_RESUME.AUDIT_COMPLETENESS"
        )

    def test_candidate_only_gates_bind_the_exact_current_resume(self) -> None:
        mutations = (
            ("ats_parse", "resume_hash", "INDUSTRY_RESUME.CURRENT_RESUME"),
            (
                "ai_recruiter",
                "evaluated_resume_hash",
                "INDUSTRY_RESUME.RECRUITER_SOURCE_BOUNDARY",
            ),
            (
                "human_recruiter",
                "evaluated_resume_hash",
                "INDUSTRY_RESUME.AUDIT_SOURCE_BOUNDARY",
            ),
            (
                "top_third",
                "evaluated_resume_source_id",
                "INDUSTRY_RESUME.AUDIT_SOURCE_BOUNDARY",
            ),
            (
                "hiring_manager",
                "evaluated_resume_hash",
                "INDUSTRY_RESUME.AUDIT_SOURCE_BOUNDARY",
            ),
            (
                "integrity",
                "evaluated_resume_source_id",
                "INDUSTRY_RESUME.AUDIT_SOURCE_BOUNDARY",
            ),
        )
        for audit_field, binding_field, check_id in mutations:
            with self.subTest(audit=audit_field, field=binding_field):
                analysis = load_fixture()
                analysis["audits"][audit_field][binding_field] = (
                    "SRC-BASELINE"
                    if binding_field.endswith("source_id")
                    else "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                )
                self.assert_fails_with(run_analysis(analysis), check_id)

    def test_model_backed_gate_evaluator_coverage_includes_zero_two_and_three(self) -> None:
        for gate_id in ("GATE_0", "GATE_2", "GATE_3"):
            with self.subTest(gate_id=gate_id, state="missing"):
                analysis = load_fixture()
                analysis["evaluator_runs"] = [
                    item for item in analysis["evaluator_runs"] if item["gate_id"] != gate_id
                ]
                self.assert_fails_with(
                    run_analysis(analysis), "INDUSTRY_RESUME.EVALUATOR_COVERAGE"
                )

            with self.subTest(gate_id=gate_id, state="disabled"):
                analysis = load_fixture()
                disable_gate(analysis, gate_id)
                self.assert_pass(run_analysis(analysis))

    def test_gate_owned_record_toggles_are_not_cosmetic(self) -> None:
        for gate_id, field in (
            ("GATE_1", "eligibility_results"),
            ("GATE_3", "semantic_alignments"),
            ("GATE_5", "qualification_results"),
        ):
            with self.subTest(gate_id=gate_id, state="cleared"):
                analysis = load_fixture()
                disable_gate(analysis, gate_id)
                self.assertEqual(analysis[field], [])
                self.assert_pass(run_analysis(analysis))

            with self.subTest(gate_id=gate_id, state="retained"):
                retained = load_fixture()
                records = retained[field]
                disable_gate(retained, gate_id)
                retained[field] = records
                self.assert_fails_with(
                    run_analysis(retained), "INDUSTRY_RESUME.GATE_DATA"
                )

    def test_target_summary_references_and_priority_sets_are_exact(self) -> None:
        wrong_priority = load_fixture()
        wrong_priority["target"]["required_requirement_ids"].remove("REQ-004")
        self.assert_fails_with(run_analysis(wrong_priority), "INDUSTRY_RESUME.TARGET")

        unknown = load_fixture()
        unknown["target"]["screen_out_requirement_ids"].append("REQ-UNKNOWN")
        self.assert_fails_with(run_analysis(unknown), "INDUSTRY_RESUME.TARGET")

        stale_source = load_fixture()
        next(item for item in stale_source["sources"] if item["source_id"] == "SRC-JD")[
            "is_current"
        ] = False
        self.assert_fails_with(
            run_analysis(stale_source), "INDUSTRY_RESUME.TARGET_SOURCE"
        )

        stale_requirement = load_fixture()
        stale_requirement["requirements"][0]["source_hash"] = (
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        self.assert_fails_with(
            run_analysis(stale_requirement), "INDUSTRY_RESUME.REQUIREMENT_SOURCE"
        )

    def test_gate_zero_requires_nonempty_screenable_requirement_decomposition(self) -> None:
        empty = load_fixture()
        empty["requirements"] = []
        self.assert_fails_with(run_analysis(empty), "INDUSTRY_RESUME.SCHEMA")

        non_screenable = load_fixture()
        for requirement in non_screenable["requirements"]:
            requirement["screenable"] = False
        self.assert_fails_with(
            run_analysis(non_screenable), "INDUSTRY_RESUME.JD_DECOMPOSITION"
        )

    def test_gate5_status_is_derived_from_qualification_classifications(self) -> None:
        analysis = load_fixture()
        analysis["audits"]["ai_recruiter"]["status"] = "PASS"
        gate_record(analysis, "GATE_5")["status"] = "PASS"
        self.assert_fails_with(
            run_analysis(analysis), "INDUSTRY_RESUME.AI_RECRUITER_STATUS"
        )

    def test_malformed_schema_shape_never_crashes_semantic_validation(self) -> None:
        analysis = load_fixture()
        analysis["audits"]["ai_recruiter"]["qualification_requirement_ids"] = [{}]
        completed = run_analysis(analysis)
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        self.assertEqual(len(completed.stdout.splitlines()), 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["result"], "FAIL")
        self.assertIn("INDUSTRY_RESUME.SCHEMA", issue_ids(completed))

    def test_final_resume_hash_and_output_package_contract(self) -> None:
        stale = load_fixture()
        stale["outputs"][0]["sha256"] = (
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        self.assert_fails_with(run_analysis(stale), "INDUSTRY_RESUME.OUTPUT_BINDING")

        missing_package = load_fixture()
        missing_package["outputs"] = [
            item
            for item in missing_package["outputs"]
            if item["artifact_type"] != "MARKDOWN_AUDIT_PACKAGE"
        ]
        self.assert_fails_with(
            run_analysis(missing_package), "INDUSTRY_RESUME.OUTPUT_COMPLETENESS"
        )

        structured_disabled = load_fixture()
        structured_disabled["config"]["save_structured_audits"] = False
        self.assert_fails_with(
            run_analysis(structured_disabled), "INDUSTRY_RESUME.STRUCTURED_SIDECAR"
        )

        markdown_disabled = load_fixture()
        markdown_disabled["config"]["save_markdown_audits"] = False
        markdown_disabled["outputs"] = [markdown_disabled["outputs"][0]]
        self.assert_pass(run_analysis(markdown_disabled))

        aliased = load_fixture()
        aliased["outputs"][1]["relative_path"] = aliased["outputs"][0]["relative_path"]
        aliased["outputs"][1]["format"] = "MD"
        self.assert_fails_with(run_analysis(aliased), "INDUSTRY_RESUME.OUTPUT_PATH")

        wrong_audit_format = load_fixture()
        wrong_audit_format["outputs"][1]["format"] = "TXT"
        self.assert_fails_with(run_analysis(wrong_audit_format), "INDUSTRY_RESUME.SCHEMA")

        source_aliased_audit = load_fixture()
        baseline = next(
            item
            for item in source_aliased_audit["sources"]
            if item["source_id"] == "SRC-BASELINE"
        )
        source_aliased_audit["outputs"][1].update(
            relative_path=baseline["relative_path"],
            format="MD",
            sha256=baseline["sha256"],
        )
        self.assert_fails_with(
            run_analysis(source_aliased_audit), "INDUSTRY_RESUME.OUTPUT_PATH"
        )

        extracted_source_alias = load_fixture()
        audit_output = next(
            item
            for item in extracted_source_alias["outputs"]
            if item["artifact_type"] == "MARKDOWN_AUDIT_PACKAGE"
        )
        profile = next(
            item
            for item in extracted_source_alias["sources"]
            if item["source_id"] == "SRC-PROFILE"
        )
        profile.update(
            extracted_text_relative_path=audit_output["relative_path"],
            extracted_text_sha256=audit_output["sha256"],
        )
        self.assert_fails_with(
            run_analysis(extracted_source_alias), "INDUSTRY_RESUME.OUTPUT_PATH"
        )

    def test_markdown_audit_package_contains_contract_ids_and_gap_classes(self) -> None:
        golden_audit = (
            BUNDLE_ROOT / "outputs" / "industry-resume-audit.md"
        ).read_text(encoding="utf-8")
        fabricated_packages = {
            "empty": "# Fabricated audit package\n",
            "token-only": (
                "REQ-001 REQ-002 REQ-003 REQ-004 REQ-005 "
                "TRUE_GAP RESUME_GAP POSITIONING_GAP\n"
                "Gate 0 PASS Gate 1 PASS_WITH_WARNINGS Gate 2 PASS_WITH_WARNINGS "
                "Gate 3 PASS_WITH_WARNINGS Gate 4 PASS Gate 5 PASS_WITH_WARNINGS "
                "Gate 6 PASS Gate 7 PASS Gate 8 PASS\n"
            ),
            "headed-token-shell": (
                "# Synthetic Audit\n\n"
                "## JD Analysis\nRequired: REQ-001 REQ-002 REQ-004; "
                "Preferred: REQ-003 REQ-005\n\n"
                "## Requirement Evidence Matrix\n"
                "REQ-001 REQ-002 REQ-003 REQ-004 REQ-005 "
                "TRUE_GAP RESUME_GAP POSITIONING_GAP\n\n"
                "## Gate Results\n"
                "- Gate 0 JD decomposition: PASS\n"
                "- Gate 1 eligibility: PASS_WITH_WARNINGS\n"
                "- Gate 2 evidence mapping: PASS_WITH_WARNINGS\n"
                "- Gate 3 semantic alignment: PASS_WITH_WARNINGS\n"
                "- Gate 4 ATS extraction: PASS\n"
                "- Gate 5 AI recruiter: PASS_WITH_WARNINGS\n"
                "- Gate 6 recruiter scan: PASS\n"
                "- Gate 7 hiring manager: PASS\n"
                "- Gate 8 integrity: PASS\n"
            ),
            "missing-heading": golden_audit.replace(
                "## Job Description Analysis", "Job Description Analysis"
            ),
            "near-requirement-id": golden_audit.replace("REQ-001", "REQ-0010"),
            "near-gap-class": golden_audit.replace("TRUE_GAP", "NOT_TRUE_GAP"),
        }
        for case, content in fabricated_packages.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                bundle = root / "bundle"
                shutil.copytree(BUNDLE_ROOT, bundle)
                audit = bundle / "outputs" / "industry-resume-audit.md"
                audit.write_text(content, encoding="utf-8")
                analysis = load_fixture()
                next(
                    item
                    for item in analysis["outputs"]
                    if item["artifact_type"] == "MARKDOWN_AUDIT_PACKAGE"
                )["sha256"] = sha256_uri(audit)
                analysis_path = root / "analysis.json"
                analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
                self.assert_fails_with(
                    run_path(analysis_path, "--bundle-root", str(bundle)),
                    "INDUSTRY_RESUME.BUNDLE_AUDIT_PACKAGE",
                )

    def test_markdown_audit_rejects_noncanonical_heading_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            shutil.copytree(BUNDLE_ROOT, bundle)
            audit = bundle / "outputs" / "industry-resume-audit.md"
            audit.write_text(
                audit.read_text(encoding="utf-8")
                .replace("## Job Description Analysis", "## JD Analysis")
                .replace(
                    "## Requirement Evidence Matrix",
                    "## Requirement–Evidence Matrix",
                )
                .replace("## Gate Results", "## Deterministic Audit Results"),
                encoding="utf-8",
            )
            analysis = load_fixture()
            next(
                item
                for item in analysis["outputs"]
                if item["artifact_type"] == "MARKDOWN_AUDIT_PACKAGE"
            )["sha256"] = sha256_uri(audit)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
            self.assert_fails_with(
                run_path(analysis_path, "--bundle-root", str(bundle)),
                "INDUSTRY_RESUME.BUNDLE_AUDIT_PACKAGE",
            )

    def test_markdown_audit_gate_statuses_match_the_structured_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            shutil.copytree(BUNDLE_ROOT, bundle)
            audit = bundle / "outputs" / "industry-resume-audit.md"
            original = audit.read_text(encoding="utf-8")
            mutated = original.replace(
                "| GATE_8 | Integrity | true | PASS | false | 0 |",
                "| GATE_8 | Integrity | true | FAIL | true | 1 |",
            )
            self.assertNotEqual(original, mutated)
            audit.write_text(mutated, encoding="utf-8")
            analysis = load_fixture()
            next(
                item
                for item in analysis["outputs"]
                if item["artifact_type"] == "MARKDOWN_AUDIT_PACKAGE"
            )["sha256"] = sha256_uri(audit)
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
            self.assert_fails_with(
                run_path(analysis_path, "--bundle-root", str(bundle)),
                "INDUSTRY_RESUME.BUNDLE_AUDIT_PACKAGE",
            )

    def test_canonical_audit_binds_all_outputs_without_leaking_gate_findings(self) -> None:
        analysis = load_fixture()
        base_rendering = build_audit_package(analysis)
        audit_output = next(
            item
            for item in analysis["outputs"]
            if item["artifact_type"] == "MARKDOWN_AUDIT_PACKAGE"
        )
        audit_output["sha256"] = "sha256:" + hashlib.sha256(
            base_rendering.encode("utf-8")
        ).hexdigest()
        self.assertEqual(base_rendering, build_audit_package(analysis))
        analysis["outputs"].append(
            {
                "artifact_type": "DASHBOARD",
                "relative_path": "outputs/dashboard.md",
                "format": "MD",
                "sha256": None,
                "status": "NOT_CREATED",
            }
        )
        self.assertNotEqual(base_rendering, build_audit_package(analysis))
        self.assert_pass(run_analysis(analysis))

        private_finding = load_fixture()
        finding = "Synthetic Candidate; first evaluator attempt FAIL, retry passed."
        gate_record(private_finding, "GATE_1")["findings"].append(finding)
        gate_record(private_finding, "GATE_8")["name"] = (
            "Integrity — Synthetic Candidate"
        )
        rendered = build_audit_package(private_finding)
        self.assertNotIn(finding, rendered)
        self.assertNotIn("Synthetic Candidate", rendered)
        self.assert_pass(run_analysis(private_finding))

        protected_audit_values = load_fixture()
        protected_audit_values["audits"]["ats_parse"].update(
            extraction_method="OCR",
            ocr_used=True,
            ocr_reason="Synthetic Candidate",
        )
        protected_audit_values["audits"]["human_recruiter"]["top_capabilities"][
            0
        ] = "Synthetic Candidate"
        protected_audit_values["audits"]["top_third"]["top_domains"][
            0
        ] = "Synthetic Candidate"
        rendered = build_audit_package(protected_audit_values)
        self.assertNotIn("Synthetic Candidate", rendered)
        self.assert_pass(run_analysis(protected_audit_values))

        markdown_injection = load_fixture()
        injected = "![tracking](https://example.invalid/pixel)"
        markdown_injection["requirements"][0]["exact_terms"][0] = injected
        rendered = build_audit_package(markdown_injection)
        self.assertNotIn(injected, rendered)
        self.assertIn(r"\!\[tracking\]\(https://example.invalid/pixel\)", rendered)
        self.assert_pass(run_analysis(markdown_injection))

    def test_ats_requires_actual_extraction_order_comparison_and_ocr_reason(self) -> None:
        for field in ("actual_extraction_performed", "logical_order_compared"):
            with self.subTest(field=field):
                analysis = load_fixture()
                analysis["audits"]["ats_parse"][field] = False
                self.assert_fails_with(
                    run_analysis(analysis), "INDUSTRY_RESUME.ATS_EXECUTION"
                )

        ocr = load_fixture()
        ocr["audits"]["ats_parse"].update(
            extraction_method="OCR", ocr_used=True, ocr_reason=None
        )
        self.assert_fails_with(run_analysis(ocr), "INDUSTRY_RESUME.ATS_EXECUTION")
        ocr["audits"]["ats_parse"]["ocr_reason"] = "Digital extraction was unreadable."
        self.assert_pass(run_analysis(ocr))

        suffix_bypass = load_fixture()
        suffix_bypass["outputs"][0]["format"] = "OTHER"
        self.assert_fails_with(
            run_analysis(suffix_bypass), "INDUSTRY_RESUME.OUTPUT_FORMAT"
        )

    def test_privacy_and_opaque_score_contracts(self) -> None:
        for local_path in (
            "file:" + "///synthetic/private/job-description.txt",
            "/etc/passwd",
            "/Volumes/SyntheticDrive/resume.docx",
            "C:\\Synthetic\\resume.docx",
            "C:/Synthetic/resume.docx",
            "\\\\synthetic-server\\share\\resume.docx",
            "redacted_path=/etc/passwd",
            "redacted_path:/etc/passwd",
            "source=[/etc/passwd]",
            "path,/" + "home/synthetic/resume.docx",
            "source;/private/tmp/resume.docx",
            "[/etc/synthetic]",
            "(/etc/synthetic)",
            "“/private/tmp/synthetic”",
            "(C:\\Synthetic\\resume.docx)",
            "{\\\\synthetic-server\\share\\resume.docx}",
            "'~/synthetic/resume.docx'",
            "~synthetic/private/resume.docx",
            "label:C:\\Synthetic\\resume.docx",
            "label:\\\\synthetic-server\\share\\resume.docx",
            "label:~/synthetic/resume.docx",
            "label-C:\\Synthetic\\resume.docx",
            "label-\\\\synthetic-server\\share\\resume.docx",
            "label-~/synthetic/resume.docx",
            "📁/" + "Users/synthetic/resume.docx",
            "→/private/tmp/synthetic",
            "$/" + "home/synthetic/resume.docx",
            "label-/etc/passwd",
            "label)/etc/passwd",
            "x—/etc/passwd",
            "label-/" + "users/synthetic/resume.docx",
            "label-/volumes/synthetic/resume.docx",
            "label)/mnt/synthetic/resume.docx",
            "label-/data/synthetic/resume.docx",
            "📁/custom/synthetic/resume.docx",
            "path)/custom/synthetic/resume.docx",
            "source)/nfs/synthetic/resume.docx",
            "x—/scratch/synthetic/resume.docx",
            "label-file:" + "///etc/passwd",
            "label.file:" + "///etc/passwd",
            "label.~/.ssh/id_rsa",
            "label.\\Users\\synthetic\\resume.docx",
            "path.\\custom\\synthetic\\resume.docx",
            "source_\\nfs\\synthetic\\resume.docx",
            "x.\\Windows\\System32\\file.dll",
            "\\Users/synthetic/resume.docx",
            "\\Windows/System32/file.dll",
            "\\\\synthetic-server/share/resume.docx",
            "path=\\custom",
            "path=\\frac",
            "path=\\sum_i",
            "label=\\custom",
            "redacted_path=\\custom",
            "\\custom",
            "value,\\custom",
            "value;\\custom",
            "(\\custom)",
            "\\Program Files\\App",
            "label-\\Program Files\\App",
            "\\Windows",
            "label-\\Windows",
            "//synthetic-server/share/resume.docx",
            "\\Users\\synthetic\\resume.docx",
        ):
            with self.subTest(local_path=local_path):
                analysis = load_fixture()
                analysis["sources"][0]["label"] = local_path
                self.assert_fails_with(run_analysis(analysis), "INDUSTRY_RESUME.PRIVACY")

        for ordinary_text in (
            "Research / Development role",
            "細胞/組織研究",
            "α/β signaling",
            "résumé/CV",
            "(A)/(B)",
            "dose (mg)/(kg)",
            "Ca²⁺/Mg²⁺ balance",
            "Na⁺/K⁺ ATPase",
            "e\u0301/foo comparison",
            "signal×/control ratio",
            "(A)/B comparison",
            "dose (mg)/kg",
            "OD(600)/OD(450)",
            "pre-/post-treatment response",
            "\"A\"/\"B\" comparison",
            "[Ca]/Mg ratio",
            "A·/B comparison",
            "dose (mg)/kg/day",
            "dose (mg)/mL/min",
            "pre-/post-treatment/follow-up",
            "mean±/SD/range",
            "A→/B comparison",
            "A°/B comparison",
            "A$/B comparison",
            "±/SD",
            "→/B",
            "°/B",
            "95% CI: ±/SD",
            "approximately ~5/day",
            "~1/2 maximal response",
            "A~B/C relationship",
            "signal~control/reference",
            "model~dose/response",
            "x~normal/error",
            "model\\beta\\gamma notation",
            "LaTeX \\alpha notation",
            "LaTeX \\custom notation",
            "\\alpha notation",
            "mean \\pm SD",
            "5 \\times 10^6 cells",
            "ratio \\frac{A}{B}",
            "n \\neq 0",
            "\\bar{x}",
            "\\sum_i x_i",
            "\\int_0^1 x dx",
            "A \\rightarrow B",
            "\\begin{matrix}A & B\\end{matrix}",
            "mean \\\\ SD",
            "LaTeX row \\\\ next",
            "(A)/B.txt comparison",
        ):
            with self.subTest(ordinary_text=ordinary_text):
                analysis = load_fixture()
                analysis["sources"][0]["label"] = ordinary_text
                self.assert_pass(run_analysis(analysis))

        url = load_fixture()
        url["sources"][0]["label"] = "https://example.invalid/synthetic-job"
        self.assert_pass(run_analysis(url))

        opaque = load_fixture()
        opaque["overall_match_score"] = 93
        self.assert_fails_with(run_analysis(opaque), "INDUSTRY_RESUME.OPAQUE_SCORE")

        wrong_workflow_version = load_fixture()
        wrong_workflow_version["workflow_version"] = "Synthetic Candidate"
        self.assert_fails_with(
            run_analysis(wrong_workflow_version), "INDUSTRY_RESUME.SCHEMA"
        )

    def test_sprint_and_gatedsprint_mode_boundaries(self) -> None:
        sprint = load_fixture()
        sprint["run"].update(
            execution_policy="SPRINT_SELF_DRIVING",
            operation="SELF_DRIVING",
            approval_ledger_created=False,
            authorization_verified=False,
        )
        self.assert_pass(run_analysis(sprint))

        sprint["run"]["approval_ledger_created"] = True
        self.assert_fails_with(run_analysis(sprint), "INDUSTRY_RESUME.MODE_BOUNDARY")

        gated = load_fixture()
        gated["run"]["operation"] = "DIAGNOSE"
        self.assert_fails_with(run_analysis(gated), "INDUSTRY_RESUME.MODE_BOUNDARY")

    def test_disabled_ai_ats_mode_is_backward_compatible(self) -> None:
        analysis = load_fixture()
        analysis["config"]["ai_ats_mode"] = False
        analysis["run"]["overall_status"] = "NOT_RUN"
        analysis["target"] = None
        for field in (
            "candidate_facts",
            "requirements",
            "evidence_items",
            "eligibility_results",
            "semantic_alignments",
            "qualification_results",
            "gaps",
            "gate_results",
            "evaluator_runs",
            "claim_provenance",
            "removed_claims",
        ):
            analysis[field] = []
        analysis["audits"] = None
        analysis["metrics"] = None
        analysis["outputs"] = [
            item for item in analysis["outputs"] if item["artifact_type"] == "FINAL_RESUME"
        ]
        self.assert_pass(run_analysis(analysis))

        nonempty_removals = json.loads(json.dumps(analysis))
        baseline = next(
            item
            for item in nonempty_removals["sources"]
            if item["source_id"] == "SRC-BASELINE"
        )
        nonempty_removals["removed_claims"] = [
            {
                "removal_id": "REMOVE-DISABLED",
                "requirement_ids": [],
                "baseline_resume_source_id": baseline["source_id"],
                "baseline_resume_hash": baseline["sha256"],
                "baseline_excerpt": "Synthetic Candidate",
                "reason": "Must be rejected while the mode is disabled.",
                "authorization_verified": True,
            }
        ]
        self.assert_fails_with(
            run_analysis(nonempty_removals),
            "INDUSTRY_RESUME.BACKWARD_COMPATIBILITY",
        )

    def test_duplicate_keys_and_nonfinite_numbers_are_input_errors(self) -> None:
        raw = FIXTURE.read_text(encoding="utf-8")
        duplicate = raw.replace(
            '"schema_version": "1.0.0",',
            '"schema_version": "1.0.0", "schema_version": "1.0.0",',
            1,
        )
        nonfinite = raw.replace('"revision_cycle": 2', '"revision_cycle": NaN', 1)
        for malformed in (duplicate, nonfinite):
            with self.subTest(malformed=malformed[:80]):
                completed = run_raw(malformed)
                self.assertEqual(completed.returncode, 2, completed.stderr + completed.stdout)
                self.assertIn("INPUT.JSON", issue_ids(completed))

    def test_invalid_invocation_is_machine_readable_exit_two(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["check"], "invocation")
        self.assertIn("INPUT.ARGUMENT", issue_ids(completed))


if __name__ == "__main__":
    unittest.main()
