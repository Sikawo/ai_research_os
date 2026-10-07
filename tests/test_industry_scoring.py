import unittest

from Career_Job_Agent_Framework.deployments.industry.scoring import normalized_job_key, score_job


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.weights = {
            "scientific_domain_fit": 25,
            "technical_fit": 25,
            "drug_discovery_translational_fit": 15,
            "seniority_fit": 10,
            "required_qualification_coverage": 10,
            "location_compensation_fit": 5,
            "visa_feasibility": 5,
            "company_stability": 5,
        }
        self.penalties = {"sponsorship_explicitly_unavailable": 30}

    def test_strong_fit(self):
        result = score_job({key: 0.9 for key in self.weights}, self.weights, {}, self.penalties, 82, 68)
        self.assertEqual(result.tier, "tier_1")

    def test_penalty_demotes(self):
        result = score_job({key: 0.85 for key in self.weights}, self.weights, {"sponsorship_explicitly_unavailable": True}, self.penalties, 82, 68)
        self.assertNotEqual(result.tier, "tier_1")

    def test_missing_evidence_is_zero(self):
        result = score_job({}, self.weights, {}, self.penalties, 82, 68)
        self.assertEqual(result.final_score, 0)

    def test_duplicate_key_normalizes(self):
        self.assertEqual(
            normalized_job_key("Example Bio", "REQ1", "Senior  Scientist", "Example City, ST"),
            normalized_job_key(" example bio ", "req1", "senior scientist", "example city, st"),
        )


if __name__ == "__main__":
    unittest.main()
