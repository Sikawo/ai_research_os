import copy
import unittest

from Career_Job_Agent_Framework.deployments.industry.reporting import (
    CurrentActiveConfig,
    OfficialVerification,
    VerificationOutcome,
    build_current_active_snapshot,
)
from Career_Job_Agent_Framework.deployments.industry.state_persistence import (
    ManualEvaluationPersistenceConfig,
    ManualOfficialVerification,
    PersistenceAction,
    persist_manual_evaluation,
    upsert_manual_evaluation,
)


def role(**overrides):
    value = {
        "tier": "tier_1",
        "fit_score": 84,
        "company": "Example Bio",
        "title": "Senior Scientist",
        "official_job_id": "REQ-101",
        "location": "Example City, ST",
        "salary": "$150,000-$175,000",
        "salary_verified": True,
        "workflow_status": "manual_review_complete",
        "strongest_match": "Strong experimental cell-biology fit.",
        "key_gap": "Direct platform experience is limited.",
        "official_url": "https://careers.example/jobs/REQ-101",
        "in_scope": True,
    }
    value.update(overrides)
    return value


def official_active():
    return ManualOfficialVerification(
        source="official_employer_page",
        outcome=VerificationOutcome.ACTIVE,
        verified_current_run=True,
    )


class MemoryStateAdapter:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.write_calls = 0

    def load_canonical_rows(self):
        return self.rows

    def write_canonical_rows(self, rows):
        self.rows = [dict(row) for row in rows]
        self.write_calls += 1


class ManualEvaluationStatePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.config = ManualEvaluationPersistenceConfig()

    def test_new_manually_evaluated_tier_1_is_inserted(self):
        rows = []
        result = upsert_manual_evaluation(rows, role(), official_active(), self.config)

        self.assertEqual(result.action, PersistenceAction.INSERTED)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tier"], "tier_1")
        self.assertEqual(rows[0]["official_status"], "active")
        self.assertTrue(rows[0]["official_verified_once"])

    def test_persistence_entrypoint_commits_through_existing_adapter(self):
        adapter = MemoryStateAdapter()

        result = persist_manual_evaluation(
            adapter, role(), official_active(), self.config
        )

        self.assertEqual(result.action, PersistenceAction.INSERTED)
        self.assertEqual(adapter.write_calls, 1)
        self.assertEqual(len(adapter.rows), 1)
        self.assertEqual(adapter.rows[0]["official_job_id"], "REQ-101")

    def test_persistence_entrypoint_does_not_write_a_skipped_role(self):
        adapter = MemoryStateAdapter()

        result = persist_manual_evaluation(
            adapter,
            role(tier="watchlist"),
            official_active(),
            self.config,
        )

        self.assertEqual(result.action, PersistenceAction.SKIPPED)
        self.assertEqual(adapter.write_calls, 0)
        self.assertEqual(adapter.rows, [])

    def test_new_manually_evaluated_tier_2_is_inserted(self):
        rows = []
        result = upsert_manual_evaluation(
            rows,
            role(tier="Tier 2", fit_score=73, official_job_id="REQ-202"),
            official_active(),
            self.config,
        )

        self.assertEqual(result.action, PersistenceAction.INSERTED)
        self.assertEqual(rows[0]["tier"], "tier_2")
        self.assertEqual(rows[0]["fit_score"], 73)

    def test_existing_role_is_updated_without_duplicate(self):
        rows = [
            role(
                company=" example bio ",
                official_job_id="req-101",
                fit_score=70,
                tier="tier_2",
                salary="$120,000",
                workflow_status="maybe",
                strongest_match="Old strength.",
                key_gap="Old gap.",
            )
        ]
        result = upsert_manual_evaluation(
            rows,
            role(
                fit_score=86,
                tier="tier_1",
                salary="$155,000-$180,000",
                workflow_status="needs_answers",
                strongest_match="Updated strength.",
                key_gap="Updated gap.",
            ),
            official_active(),
            self.config,
        )

        self.assertEqual(result.action, PersistenceAction.UPDATED)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fit_score"], 86)
        self.assertEqual(rows[0]["tier"], "tier_1")
        self.assertEqual(rows[0]["salary"], "$155,000-$180,000")
        self.assertEqual(rows[0]["workflow_status"], "needs_answers")
        self.assertEqual(rows[0]["strongest_match"], "Updated strength.")
        self.assertEqual(rows[0]["key_gap"], "Updated gap.")

    def test_tier_below_tier_2_is_not_persisted(self):
        rows = []
        result = upsert_manual_evaluation(
            rows, role(tier="watchlist", fit_score=64), official_active(), self.config
        )

        self.assertEqual(result.action, PersistenceAction.SKIPPED)
        self.assertEqual(rows, [])

    def test_linkedin_only_verification_is_not_persisted(self):
        rows = []
        verification = ManualOfficialVerification(
            source="linkedin",
            outcome=VerificationOutcome.ACTIVE,
            verified_current_run=True,
        )
        result = upsert_manual_evaluation(rows, role(), verification, self.config)

        self.assertEqual(result.action, PersistenceAction.SKIPPED)
        self.assertEqual(rows, [])

    def test_closed_official_posting_is_not_persisted_as_active(self):
        rows = []
        verification = ManualOfficialVerification(
            source="official_employer_page",
            outcome=VerificationOutcome.CLOSED,
            verified_current_run=True,
        )
        result = upsert_manual_evaluation(rows, role(), verification, self.config)

        self.assertEqual(result.action, PersistenceAction.SKIPPED)
        self.assertEqual(rows, [])

    def test_hard_blocked_role_is_not_actionable(self):
        rows = []
        result = upsert_manual_evaluation(
            rows,
            role(hard_blocked=True, hard_blockers=["required credential missing"]),
            official_active(),
            self.config,
        )

        self.assertEqual(result.action, PersistenceAction.SKIPPED)
        self.assertEqual(rows, [])

    def test_manual_persistence_does_not_change_scheduled_counts_or_alerts(self):
        rows = []
        scheduled_counts = {
            "new_jobs": 0,
            "materially_changed_jobs": 0,
            "new_tier_1": 0,
            "new_tier_2": 0,
        }
        counts_before = copy.deepcopy(scheduled_counts)

        result = upsert_manual_evaluation(rows, role(), official_active(), self.config)

        self.assertEqual(scheduled_counts, counts_before)
        self.assertEqual(result.scheduled_new_job_count_delta, 0)
        self.assertFalse(result.duplicate_daily_alert_required)
        self.assertFalse(result.application_submission_triggered)

    def test_manual_row_is_available_to_current_active_from_same_state(self):
        rows = []
        result = upsert_manual_evaluation(rows, role(), official_active(), self.config)

        snapshot = build_current_active_snapshot(
            rows,
            lambda _role: OfficialVerification(VerificationOutcome.ACTIVE),
            CurrentActiveConfig(),
        )

        self.assertEqual(result.action, PersistenceAction.INSERTED)
        self.assertEqual(len(snapshot.roles), 1)
        self.assertEqual(snapshot.roles[0].job_id, "REQ-101")

    def test_official_url_fallback_updates_existing_role(self):
        rows = [
            role(
                official_job_id="",
                official_url="https://careers.example/jobs/REQ-101/?source=old",
                fit_score=71,
                tier="tier_2",
            )
        ]
        result = upsert_manual_evaluation(
            rows,
            role(
                official_job_id="REQ-101",
                official_url="https://careers.example/jobs/REQ-101",
                fit_score=85,
            ),
            official_active(),
            self.config,
        )

        self.assertEqual(result.action, PersistenceAction.UPDATED)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fit_score"], 85)

    def test_company_title_location_fallback_updates_existing_role(self):
        rows = [
            role(
                official_job_id="",
                official_url="",
                company=" Example Bio ",
                title="Senior   Scientist",
                location="Example City, ST",
                fit_score=70,
            )
        ]
        result = upsert_manual_evaluation(
            rows,
            role(
                official_job_id="",
                official_url="",
                company="example bio",
                title="senior scientist",
                location="example city, st",
                fit_score=83,
            ),
            official_active(),
            self.config,
        )

        self.assertEqual(result.action, PersistenceAction.UPDATED)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fit_score"], 83)

    def test_configuration_mapping_loads_manual_persistence_flags(self):
        config = ManualEvaluationPersistenceConfig.from_root(
            {
                "state_persistence": {
                    "manual_evaluations": {
                        "enabled": True,
                        "upsert_actionable_tier_1_2": True,
                        "require_current_official_verification": True,
                    }
                }
            }
        )

        self.assertTrue(config.enabled)
        self.assertTrue(config.upsert_actionable_tier_1_2)
        self.assertTrue(config.require_current_official_verification)


if __name__ == "__main__":
    unittest.main()
