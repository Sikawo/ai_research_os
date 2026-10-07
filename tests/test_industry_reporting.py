import copy
import unittest

from Career_Job_Agent_Framework.deployments.industry.reporting import (
    CurrentActiveConfig,
    OfficialVerification,
    VerificationOutcome,
    build_daily_report_payload,
    render_chatgpt_digest,
    render_daily_report,
    render_gmail_digest,
    render_slack_digest,
)


def role(**overrides):
    value = {
        "tier": "tier_1",
        "fit_score": 82,
        "company": "Example Bio",
        "title": "Example Scientist",
        "official_job_id": "EX-101",
        "location": "Example City, ST",
        "salary": "$100,000-$120,000",
        "salary_verified": True,
        "workflow_status": "needs_answers",
        "strongest_match": "Strong cell-biology and screening experience.",
        "key_gap": "Direct functional-genomics depth is unclear.",
        "official_url": "https://careers.example/jobs/EX-101",
        "official_verified_once": True,
        "in_scope": True,
    }
    value.update(overrides)
    return value


class CurrentActiveReportingTests(unittest.TestCase):
    def setUp(self):
        self.config = CurrentActiveConfig()

    @staticmethod
    def active(_role):
        return OfficialVerification(VerificationOutcome.ACTIVE)

    def payload(self, roles, verifier=None, counts=None, config=None):
        return build_daily_report_payload(
            today_changes="[NO MATCH]\nNew qualified roles: 0",
            alert_counts=counts
            or {
                "new_jobs": 0,
                "materially_changed_jobs": 0,
                "new_tier_1": 0,
                "new_tier_2": 0,
            },
            canonical_roles=roles,
            verifier=verifier or self.active,
            config=config or self.config,
        )

    def test_no_new_jobs_includes_unchanged_active_tier_1(self):
        report = render_daily_report(self.payload([role()]))
        self.assertTrue(report.startswith("[NO MATCH]"))
        self.assertIn("CURRENT ACTIVE TIER 1/2", report)
        self.assertIn("EX-101", report)

    def test_active_tier_2_is_included(self):
        report = render_daily_report(
            self.payload([role(tier="tier_2", fit_score=74, official_job_id="T2")])
        )
        self.assertIn("Tier 2", report)
        self.assertIn("- 74 |", report)

    def test_closed_role_is_not_included(self):
        def closed(_role):
            return OfficialVerification(VerificationOutcome.CLOSED)

        report = render_daily_report(self.payload([role()], verifier=closed))
        self.assertTrue(report.endswith("CURRENT ACTIVE TIER 1/2\nNone."))
        self.assertNotIn("EX-101", report)

    def test_hard_blocked_role_is_not_included_or_reverified(self):
        calls = []

        def verifier(candidate):
            calls.append(candidate)
            return OfficialVerification(VerificationOutcome.ACTIVE)

        report = render_daily_report(
            self.payload([role(hard_blocked=True)], verifier=verifier)
        )
        self.assertEqual(calls, [])
        self.assertTrue(report.endswith("None."))

    def test_transient_failure_is_reported_without_mutating_prior_state(self):
        stored = role(official_status="active")
        before = copy.deepcopy(stored)

        def failed(_role):
            return OfficialVerification(
                VerificationOutcome.SOURCE_FAILURE, "maintenance page"
            )

        report = render_daily_report(self.payload([stored], verifier=failed))
        self.assertEqual(stored, before)
        self.assertIn("INCOMPLETE CHECKS / SOURCE FAILURES", report)
        self.assertIn("maintenance page", report)
        self.assertTrue(report.endswith("CURRENT ACTIVE TIER 1/2\nNone."))

    def test_sorting_and_deduplication(self):
        roles = [
            role(
                tier="tier_2",
                fit_score=79,
                company="Example D",
                official_job_id="4",
                title="Scientist D",
            ),
            role(fit_score=82, company="Example C", official_job_id="2", title="Scientist B"),
            role(fit_score=88, company="Example A", official_job_id="1", title="Scientist A"),
            role(
                fit_score=82,
                company="Example B",
                official_job_id="5",
                title="Scientist B2",
            ),
            role(fit_score=82, company="Example B", official_job_id="3", title="Scientist C"),
            role(
                fit_score=99,
                company=" example a ",
                official_job_id="1",
                title="Duplicate should not render",
            ),
        ]
        report = render_daily_report(self.payload(roles))
        positions = [
            report.index("| Example A | Scientist A |"),
            report.index("| Example B | Scientist B2 |"),
            report.index("| Example B | Scientist C |"),
            report.index("| Example C | Scientist B |"),
            report.index("| Example D | Scientist D |"),
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("Duplicate should not render", report)

    def test_no_active_roles_keeps_explicit_empty_section(self):
        self.assertTrue(
            render_daily_report(self.payload([])).endswith(
                "CURRENT ACTIVE TIER 1/2\nNone."
            )
        )

    def test_snapshot_does_not_change_alert_counts(self):
        counts = {
            "new_jobs": 0,
            "materially_changed_jobs": 0,
            "new_tier_1": 0,
            "new_tier_2": 0,
        }
        payload = self.payload([role()], counts=counts)
        self.assertEqual(dict(payload.alert_counts), counts)

    def test_all_channels_share_one_snapshot(self):
        calls = []

        def verifier(candidate):
            calls.append(candidate["official_job_id"])
            return OfficialVerification(VerificationOutcome.ACTIVE)

        payload = self.payload([role()], verifier=verifier)
        outputs = (
            render_daily_report(payload),
            render_chatgpt_digest(payload),
            render_gmail_digest(payload),
            render_slack_digest(payload),
        )
        self.assertEqual(calls, ["EX-101"])
        self.assertEqual(len(set(outputs)), 1)

    def test_disabled_feature_preserves_prior_output(self):
        calls = []

        def verifier(candidate):
            calls.append(candidate)
            return OfficialVerification(VerificationOutcome.ACTIVE)

        config = CurrentActiveConfig(enabled=False)
        payload = self.payload([role()], verifier=verifier, config=config)
        self.assertEqual(
            render_daily_report(payload), "[NO MATCH]\nNew qualified roles: 0"
        )
        self.assertEqual(calls, [])

    def test_config_mapping_loads_reporting_section(self):
        config = CurrentActiveConfig.from_reporting(
            {
                "current_active_tier_1_2": {
                    "enabled": True,
                    "heading": "CURRENT ACTIVE TIER 1/2",
                    "include_unchanged": True,
                    "reverify_official_status_each_daily_run": True,
                }
            }
        )
        self.assertTrue(config.enabled)
        self.assertEqual(config.heading, "CURRENT ACTIVE TIER 1/2")


if __name__ == "__main__":
    unittest.main()
