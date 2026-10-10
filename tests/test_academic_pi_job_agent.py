"""Unit, integration, privacy, and Industry-regression tests for Academic PI."""

from __future__ import annotations

import json
from pathlib import Path

from Career_Job_Agent_Framework.core import (
    InMemoryStateStore,
    JsonFileStateStore,
    JobRecord,
    PrivacyGuard,
    SourceAuthority,
    VerificationResult,
    VerificationStatus,
    apply_verification,
    deduplicate_jobs,
    detect_material_changes,
    load_config_file,
    load_config_overlay,
    normalize_url,
)
from Career_Job_Agent_Framework.deployments.academic_pi import (
    AcademicPiService,
    CallableVerificationAdapter,
    MemoryReportAdapter,
    NoOpReportAdapter,
    StaticDiscoveryAdapter,
    StaticEmailAdapter,
    build_gatedsprint_handoff,
    generate_academic_queries,
    infer_independence,
    load_academic_config,
    normalize_academic_title,
    parse_academic_alert_result,
    plan_gmail_labels,
    render_daily_report,
    render_weekly_report,
    score_academic_fit,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = REPO_ROOT / "Career_Job_Agent_Framework" / "deployments" / "academic_pi"


def profile() -> dict[str, object]:
    return {
        "career_stage": {
            "target_independence": ["tenure_track_faculty", "independent_group_leader"]
        },
        "scientific_identity": {
            "primary_fields": ["virology"],
            "secondary_fields": ["immunology"],
            "research_questions": ["host defense"],
            "systems": ["organoids"],
            "methods": ["single-cell sequencing"],
            "translational_strengths": ["therapeutic discovery"],
        },
        "departments": {
            "strong_fit": ["Biology", "Immunology"],
            "plausible_fit": ["Microbiology"],
        },
        "evidence": {
            "cv_path": "PRIVATE_CV_REFERENCE",
            "publication_sources": ["PRIVATE_PUBLICATION_LEDGER"],
            "research_statement_path": "PRIVATE_RESEARCH_STATEMENT_REFERENCE",
            "additional_evidence_paths": ["PRIVATE_EVIDENCE_REFERENCE"],
        },
    }


def open_job(**overrides: object) -> JobRecord:
    values: dict[str, object] = {
        "title": "Assistant Professor of Biology",
        "institution": "Synthetic University",
        "organization": "Synthetic University",
        "department": "Biology",
        "location": "Example City, US",
        "country": "US",
        "official_job_id": "REQ-100",
        "official_url": "https://jobs.example.edu/REQ-100",
        "description": (
            "Tenure-track faculty will establish an independent research program in "
            "virology, use single-cell sequencing, receive startup support, and supervise "
            "graduate students."
        ),
        "search_scope": {"broad_search": False, "department_scope": ["Biology"]},
        "lifecycle_status": "open",
        "verification_status": VerificationStatus.VERIFIED_OPEN,
        "verification_confidence": 0.95,
        "last_verified": "2026-10-04T00:00:00Z",
        "deadline": "2026-12-01",
        "deadline_type": "fixed",
    }
    values.update(overrides)
    return JobRecord(**values)


def verifier(status: VerificationStatus = VerificationStatus.VERIFIED_OPEN):
    return CallableVerificationAdapter(
        lambda job: VerificationResult(
            status=status,
            source_url=job.official_url or "https://jobs.example.edu/verified",
            authority=SourceAuthority.OFFICIAL_DETAIL,
            confidence=0.95,
            verified_fields={
                "institution": job.institution or "Synthetic University",
                "title": job.title,
                "department": job.department,
                "deadline": job.deadline,
                "requirements": job.requirements,
            },
            evidence=["official institution page"],
        )
    )


def service_config(*, institutions: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "academic_pi": {"automation": {"auto_apply": False}, "query_budget": 8},
        "candidate_profile": profile(),
        "target_institutions": {"institutions": institutions or []},
        "configuration_provenance": {
            "framework_source": "synthetic/public-framework",
            "framework_resolution": "PASS",
            "deployment_config_source": "synthetic/private-overlay",
            "deployment_config_resolution": "PASS",
            "fallback_used": "no",
        },
    }


def test_title_normalization_us_and_exclusions() -> None:
    assert normalize_academic_title("Assistant Professor", "US").normalized_role_class == "tenure_track_faculty"
    assert normalize_academic_title("Postdoctoral Fellow", "US").normalized_role_class == "postdoc"


def test_country_specific_title_rules() -> None:
    assert normalize_academic_title("Lecturer", "UK").normalized_role_class == "likely_independent_pi"
    assert normalize_academic_title("W1 Professorship", "DE").normalized_role_class == "likely_independent_pi"


def test_independence_evidence_extraction() -> None:
    result = infer_independence(
        "Group Leader",
        "The appointee will establish an independent research program with startup funds and lab space.",
        "DE",
    )
    assert result.independence_class == "independent"
    assert "establish an independent research program" in result.evidence
    assert "startup support" in result.evidence


def test_gmail_alert_parses_multiple_jobs_and_labels_only_after_handling() -> None:
    parsed = parse_academic_alert_result(
        {
            "message_id": "message-1",
            "html": (
                '<a href="https://alerts.example/job/1">Assistant Professor of Biology</a>'
                '<a href="https://alerts.example/job/2">Independent Group Leader</a>'
            ),
        }
    )
    assert len(parsed.candidates) == 2
    assert not plan_gmail_labels(parsed).processed
    parsed.handled_candidate_ids.update(candidate.event_id for candidate in parsed.candidates)
    plan = plan_gmail_labels(parsed)
    assert plan.processed
    assert not plan.archive and not plan.delete


def test_url_normalization_removes_tracking_and_fragments() -> None:
    assert normalize_url("HTTPS://Jobs.Example.edu//role/?utm_source=x&id=7#top") == (
        "https://jobs.example.edu/role?id=7"
    )


def test_dedupe_email_aggregator_and_official_page() -> None:
    jobs = [
        open_job(official_url=None, discovery_urls=["https://alerts.example/r/1"], source_provenance=[{"source_id": "email"}]),
        open_job(official_url=None, discovery_urls=["https://board.example/r/1?utm_source=mail"], source_provenance=[{"source_id": "board"}]),
        open_job(source_provenance=[{"source_id": "official"}]),
    ]
    merged = deduplicate_jobs(jobs)
    assert len(merged) == 1
    assert {row["source_id"] for row in merged[0].source_provenance} == {"email", "board", "official"}


def test_same_title_different_department_stays_separate() -> None:
    first = open_job(department="Biology", official_job_id=None, official_url=None)
    second = open_job(department="Chemistry", official_job_id=None, official_url=None)
    assert len(deduplicate_jobs([first, second])) == 2


def test_repost_same_requisition_upserts_without_duplicate() -> None:
    state = InMemoryStateStore()
    first = apply_verification(
        open_job(deadline=None),
        VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            verified_fields={"deadline": "2026-11-01"},
        ),
    )
    extended = apply_verification(
        open_job(deadline=None),
        VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            verified_fields={"deadline": "2026-12-15"},
        ),
    )
    inserted = state.upsert_job(first)
    updated = state.upsert_job(extended)
    assert inserted.action == "inserted"
    assert updated.action == "updated"
    assert len(state.list_jobs()) == 1


def test_transient_verification_failure_never_closes_durable_job() -> None:
    state = InMemoryStateStore()
    state.upsert_job(open_job())
    transient = apply_verification(
        open_job(),
        VerificationResult(
            status=VerificationStatus.VERIFICATION_FAILED_TRANSIENT,
            error="temporary timeout",
        ),
    )
    state.upsert_job(transient)
    stored = state.list_jobs()[0]
    assert stored.lifecycle_status == "open"
    assert stored.verification_status == VerificationStatus.VERIFICATION_FAILED_TRANSIENT
    assert stored.extra["last_definitive_verification_status"] == "verified_open"


def test_explicit_official_closure_closes_job() -> None:
    closed = apply_verification(
        open_job(),
        VerificationResult(
            status=VerificationStatus.VERIFIED_CLOSED,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            confidence=1.0,
        ),
    )
    assert closed.lifecycle_status == "closed"
    assert closed.verification_status == VerificationStatus.VERIFIED_CLOSED


def test_closed_job_can_reopen_without_new_identity() -> None:
    state = InMemoryStateStore()
    closed = apply_verification(
        open_job(),
        VerificationResult(
            status=VerificationStatus.VERIFIED_CLOSED,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            confidence=1.0,
        ),
    )
    first = state.upsert_job(closed)
    reopened = apply_verification(
        closed,
        VerificationResult(
            status=VerificationStatus.VERIFIED_REOPENED,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            confidence=1.0,
        ),
    )
    second = state.upsert_job(reopened)
    assert first.job_id == second.job_id
    assert len(state.list_jobs()) == 1
    assert state.list_jobs()[0].lifecycle_status == "reopened"


def test_material_change_detection_ignores_formatting_but_detects_deadline() -> None:
    old = open_job(title="Assistant Professor - Biology", deadline="2026-11-01")
    formatted = open_job(title="Assistant Professor: Biology", deadline="2026-11-01")
    assert not [change for change in detect_material_changes(old, formatted) if change.field == "title"]
    changed = open_job(deadline="2026-12-01")
    assert "deadline" in {change.field for change in detect_material_changes(old, changed)}


def test_broad_faculty_search_has_no_keyword_absence_penalty() -> None:
    broad = {
        "raw_title": "Open Rank Faculty",
        "department": "Biology",
        "description": "Applications are invited from all areas of biology.",
        "search_scope": {"broad_search": True, "department_scope": ["Biology"]},
        "independence": {"class": "independent"},
        "status": {"verification_status": "verified_open", "verification_confidence": 0.9},
    }
    narrow = {**broad, "search_scope": {"broad_search": False, "department_scope": ["Biology"]}}
    broad_result = score_academic_fit(broad, profile())
    narrow_result = score_academic_fit(narrow, profile())
    assert broad_result.fit_score > narrow_result.fit_score
    assert not any("no direct primary-field" in gap for gap in broad_result.meaningful_gaps)


def test_hard_blocker_is_separate_from_raw_fit_score() -> None:
    job = {
        "raw_title": "Postdoctoral Fellow in Virology",
        "description": "Virology, host defense, organoids, and single-cell sequencing.",
        "status": {"verification_status": "verified_open", "verification_confidence": 1.0},
        "department": "Biology",
    }
    result = score_academic_fit(job, profile())
    assert result.fit_score > 0
    assert result.tier == "BLOCKED"
    assert result.hard_blockers


def test_unknown_salary_and_startup_stay_unknown() -> None:
    job = open_job(position={})
    assert job.position.get("salary_min") is None
    assert job.position.get("startup_information") is None


def test_manual_evaluation_upserts_without_discovery_run() -> None:
    state = InMemoryStateStore()
    inserted = state.upsert_job(open_job())
    service = AcademicPiService(config=service_config(), state_store=state, verification_connector=verifier())
    evaluated = service.evaluate(inserted.job_id or "")
    assert evaluated.canonical_id == inserted.job_id
    assert len(state.list_jobs()) == 1
    assert state.list_runs() == []


def test_rejected_role_stays_rejected_after_rediscovery() -> None:
    state = InMemoryStateStore()
    inserted = state.upsert_job(open_job())
    service = AcademicPiService(config=service_config(), state_store=state, verification_connector=verifier())
    service.reject(inserted.job_id or "", reason="not interested")
    rediscovery = AcademicPiService(
        config=service_config(),
        state_store=state,
        discovery_connectors=[StaticDiscoveryAdapter("official", [open_job()])],
        verification_connector=verifier(),
    )
    result = rediscovery.daily()
    assert result.metrics["new_jobs"] == 0
    assert state.list_jobs()[0].rejected
    assert rediscovery.active() == []


def test_private_config_resolution_precedence(tmp_path: Path) -> None:
    env_dir = tmp_path / "env"
    existing_dir = tmp_path / "existing"
    local_dir = tmp_path / "local"
    example_dir = tmp_path / "example"
    for directory, marker in (
        (env_dir, "environment"),
        (existing_dir, "existing"),
        (local_dir, "local"),
        (example_dir, "example"),
    ):
        directory.mkdir()
        (directory / "marker.yaml").write_text(f"value: {marker}\n", encoding="utf-8")
    merged = load_config_overlay(
        {"public": True},
        environ={"ACADEMIC_PI_PRIVATE_CONFIG_DIR": str(env_dir)},
        existing_private_dirs=[existing_dir],
        local_dir=local_dir,
        example_dir=example_dir,
        allow_example=True,
    )
    assert merged["marker"]["value"] == "environment"
    assert merged["_config"]["overlay_kind"] == "environment"


def test_example_profile_runs_without_private_config(monkeypatch) -> None:
    monkeypatch.delenv("ACADEMIC_PI_PRIVATE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CAREER_JOB_AGENT_PRIVATE_CONFIG_DIR", raising=False)
    config = load_academic_config(allow_example=True)
    assert config["candidate_profile"]["scientific_identity"]["primary_fields"] == ["FIELD_A", "FIELD_B"]
    result = AcademicPiService(config=config).dry_run()
    assert "[NO MATCH]" in result.report
    assert result.submitted_applications == 0


def test_tracked_file_privacy_guard_finds_configured_private_data(tmp_path: Path) -> None:
    public_file = tmp_path / "public.txt"
    public_file.write_text("Synthetic public fixture plus PERSON_TO_BLOCK", encoding="utf-8")
    guard = PrivacyGuard(forbidden_literals=["PERSON_TO_BLOCK"])
    assert guard.scan_files([public_file])
    synthetic_assignment = "api_" + "key=" + "abcdefghijklmnop"
    assert guard.scan_text(synthetic_assignment)


def test_json_state_store_is_durable_and_read_back_validated(tmp_path: Path) -> None:
    path = tmp_path / "private-state" / "academic.json"
    state = JsonFileStateStore(path)
    state.upsert_job(open_job())
    restored = JsonFileStateStore(path)
    assert len(restored.list_jobs()) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_query_generation_is_budgeted_and_includes_broad_institution_queries() -> None:
    queries = generate_academic_queries(
        profile(),
        [{"id": "web", "enabled": True, "query_cap": 6}],
        [{"name": "Synthetic Institute", "enabled": True, "priority": 1, "domains": ["example.edu"]}],
        {"total": 6, "per_source": 6},
    )
    assert len(queries) <= 6
    assert len({(query.source_id, query.text.casefold().replace('"', "")) for query in queries}) == len(queries)
    assert any(query.broad_search and "site:example.edu" in query.text for query in queries)


def test_daily_and_weekly_report_contracts() -> None:
    daily = render_daily_report([])
    weekly = render_weekly_report([])
    for heading in (
        "## Action Required",
        "## CURRENT ACTIVE TIER 1",
        "## CURRENT ACTIVE TIER 2",
        "## Applications",
    ):
        assert heading in daily
    assert "[NO MATCH]" in daily
    for heading in (
        "## SOURCE COVERAGE AUDIT",
        "## TARGET-INSTITUTION COVERAGE AUDIT",
        "## EMAIL BACKLOG / PARSE ERRORS",
        "## APPLICATION STATUS",
    ):
        assert heading in weekly

    rendered = render_weekly_report([open_job(tier="Tier 1", fit_score=88)])
    for layer in (
        "Scientific fit:",
        "Opportunity quality:",
        "QOL fit:",
        "Eligibility:",
        "Verification confidence:",
    ):
        assert layer in rendered


def test_gatedsprint_handoff_is_evidence_backed_and_never_authorizes_submission() -> None:
    job = open_job(evaluation={"fit_score": 88, "tier": "Tier 1", "strongest_matches": ["virology"]})
    handoff = build_gatedsprint_handoff(
        job,
        evidence=[
            {
                "ref": "E-1",
                "strength": "direct",
                "claim": "direct evidence",
                "authorized": True,
            }
        ],
    )
    assert handoff["job"]["official_url"] == job.official_url
    assert handoff["candidate_evidence"]["evidence_refs"][0]["ref"] == "E-1"
    assert handoff["application"]["submission_authorized"] is False
    assert "submission_performed" not in handoff["application"]


def test_integration_three_sources_converge_to_one_canonical_job() -> None:
    rows = [
        open_job(official_url=None, source_provenance=[{"source_id": "email"}]),
        open_job(official_url=None, source_provenance=[{"source_id": "aggregator"}]),
        open_job(source_provenance=[{"source_id": "official"}]),
    ]
    state = InMemoryStateStore()
    service = AcademicPiService(
        config=service_config(),
        state_store=state,
        discovery_connectors=[StaticDiscoveryAdapter("multi", rows)],
        verification_connector=verifier(),
    )
    result = service.daily()
    assert len(state.list_jobs()) == 1
    assert result.metrics["new_jobs"] == 1
    assert result.metrics["deduped_candidates"] == 1


def test_integration_temporary_official_outage_preserves_prior_state() -> None:
    state = InMemoryStateStore()
    state.upsert_job(open_job(tier="Tier 1", fit_score=90))
    service = AcademicPiService(
        config=service_config(),
        state_store=state,
        discovery_connectors=[StaticDiscoveryAdapter("official", [open_job()])],
        verification_connector=verifier(VerificationStatus.VERIFICATION_FAILED_TRANSIENT),
    )
    service.daily()
    stored = state.list_jobs()[0]
    assert stored.lifecycle_status == "open"
    assert stored.verification_status == VerificationStatus.VERIFICATION_FAILED_TRANSIENT
    assert stored.extra["last_definitive_verification_status"] == "verified_open"


def test_integration_ambiguous_european_group_leader_routes_to_review() -> None:
    state = InMemoryStateStore()
    service = AcademicPiService(
        config=service_config(),
        state_store=state,
        discovery_connectors=[
            StaticDiscoveryAdapter(
                "euraxess",
                [
                    open_job(
                        title="Group Leader",
                        country="DE",
                        description="Lead collaborative projects within the center.",
                    )
                ],
            )
        ],
        verification_connector=verifier(),
    )
    service.daily()
    stored = state.list_jobs()[0]
    assert stored.independence_class == "ambiguous"
    assert stored.manual_review_state == "needs_review"


def test_integration_deadline_change_updates_one_row_and_logs_change() -> None:
    state = InMemoryStateStore()
    state.upsert_job(open_job(deadline="2026-11-01"))
    service = AcademicPiService(
        config=service_config(),
        state_store=state,
        discovery_connectors=[StaticDiscoveryAdapter("official", [open_job(deadline="2026-12-01")])],
        verification_connector=verifier(),
    )
    result = service.daily()
    assert len(state.list_jobs()) == 1
    assert state.list_jobs()[0].deadline == "2026-12-01"
    assert result.metrics["material_changes"] >= 1
    assert any(change.field == "deadline" for change in state.list_changes())


def test_integration_closed_then_reopened_preserves_history() -> None:
    state = InMemoryStateStore()
    state.upsert_job(open_job())
    closed_service = AcademicPiService(
        config=service_config(),
        state_store=state,
        discovery_connectors=[StaticDiscoveryAdapter("official", [open_job()])],
        verification_connector=verifier(VerificationStatus.VERIFIED_CLOSED),
    )
    closed_service.daily()
    reopened_service = AcademicPiService(
        config=service_config(),
        state_store=state,
        discovery_connectors=[StaticDiscoveryAdapter("official", [open_job()])],
        verification_connector=verifier(VerificationStatus.VERIFIED_REOPENED),
    )
    reopened_service.daily()
    assert len(state.list_jobs()) == 1
    assert state.list_jobs()[0].lifecycle_status == "reopened"
    assert {change.field for change in state.list_changes()} & {"lifecycle_status", "verification_status"}


def test_integration_email_ingestion_is_idempotent() -> None:
    email = StaticEmailAdapter(
        [
            {
                "message_id": "gmail-1",
                "body": "Assistant Professor of Biology https://jobs.example.edu/REQ-100",
            }
        ]
    )
    state = InMemoryStateStore()
    service = AcademicPiService(
        config=service_config(),
        state_store=state,
        email_connector=email,
        verification_connector=verifier(),
    )
    first = service.daily()
    second = service.daily()
    assert first.metrics["new_jobs"] == 1
    assert second.metrics["new_jobs"] == 0
    assert len(state.list_jobs()) == 1
    assert first.label_plans[0].processed


def test_integration_zero_job_institution_scan_is_successful_coverage() -> None:
    state = InMemoryStateStore()
    service = AcademicPiService(
        config=service_config(
            institutions=[
                {
                    "name": "Synthetic Institute",
                    "enabled": True,
                    "career_urls": ["https://example.edu/careers"],
                }
            ]
        ),
        state_store=state,
        discovery_connectors=[StaticDiscoveryAdapter("institution", [])],
    )
    service.daily()
    coverage = state.list_institution_coverage()
    assert len(coverage) == 1
    assert coverage[0].status == "success"


def test_report_delivery_counts_only_confirmed_delivery() -> None:
    confirmed = MemoryReportAdapter("memory")
    unconfirmed = NoOpReportAdapter()
    service = AcademicPiService(
        config=service_config(), report_connectors=[confirmed, unconfirmed]
    )
    result = service.daily()
    assert result.metrics["report_delivery_successes"] == 1
    assert result.metrics["report_delivery_failures"] == 1
    assert len(confirmed.reports) == 1


def test_public_examples_schemas_and_privacy_isolation() -> None:
    for schema in sorted((DEPLOYMENT / "schemas").glob("*.json")):
        parsed = json.loads(schema.read_text(encoding="utf-8"))
        assert parsed["$schema"].endswith("schema")
    for config in sorted((DEPLOYMENT / "config").glob("*.yaml")):
        assert load_config_file(config)
    public_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((DEPLOYMENT / "templates").glob("*.yaml"))
    )
    assert "/" + "Users/" not in public_text
    assert "@gmail.com" not in public_text
    assert "PRIVATE_CV_REFERENCE" not in public_text


def test_industry_contracts_remain_present_and_unchanged_in_shape() -> None:
    framework = REPO_ROOT / "Career_Job_Agent_Framework"
    daily = (framework / "contracts" / "daily_run.md").read_text(encoding="utf-8")
    state = (framework / "contracts" / "state_persistence.md").read_text(encoding="utf-8")
    assert "CURRENT ACTIVE TIER 1/2" in daily
    assert "Upsert; never blindly append" in state
