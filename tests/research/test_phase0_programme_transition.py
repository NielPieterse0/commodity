import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROGRAMME = ROOT / "research" / "programmes" / "002-henry-hub-fresh"


class Phase0ProgrammeTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.synthesis = json.loads(
            (PROGRAMME / "research-synthesis.json").read_text(encoding="utf-8")
        )
        self.designs = json.loads(
            (PROGRAMME / "experiment-designs.json").read_text(encoding="utf-8")
        )
        self.ledger = json.loads(
            (PROGRAMME / "feasibility-ledger.json").read_text(encoding="utf-8")
        )
        self.methodology = json.loads(
            (ROOT / "config" / "research_methodology.json").read_text(encoding="utf-8")
        )

    def test_phase0_baseline_classifies_every_design_once(self) -> None:
        transition = self.synthesis["phase_0_transition"]
        classification = transition["forecast_objective_classification"]
        rows = classification["designs"]
        design_ids = {item["design_id"] for item in self.designs["designs"]}
        self.assertEqual(len(rows), len(design_ids))
        self.assertEqual({row["design_id"] for row in rows}, design_ids)
        self.assertEqual(
            classification["counts"],
            {
                "forecast_candidate": 14,
                "contextual_evidence": 3,
                "unavailable_exact_replication": 4,
                "no_longer_worth_pursuing": 0,
            },
        )
        allowed = set(classification["counts"])
        self.assertTrue(all(row["forecast_role"] in allowed for row in rows))
        observed_counts = Counter(row["forecast_role"] for row in rows)
        normalized_counts = {
            role: observed_counts.get(role, 0) for role in classification["counts"]
        }
        self.assertEqual(normalized_counts, classification["counts"])
        self.assertEqual(self.ledger["decision_counts"], {"GO": 14, "HOLD": 7, "REDESIGN": 0})

    def test_phase0_preserves_old_scientific_boundary_and_agent_evidence(self) -> None:
        transition = self.synthesis["phase_0_transition"]
        prior = transition["previous_programme_baseline"]
        self.assertEqual(prior["internal_reproductions_completed"], 0)
        self.assertFalse(prior["outcome_effect_testing_performed"])
        self.assertFalse(prior["protected_confirmation_opened"])
        agent_a = transition["carried_forward"]["agent_a_work_316"]
        self.assertEqual(agent_a["verified_pr_head"], "0dc6f8a5d75ff30308cfbdd6e461b963a9890323")
        self.assertEqual(agent_a["preserved_branch_head"], "fc0f4049b5b1aa47f5d694dd6862b8298d1d9b22")
        agent_b = transition["carried_forward"]["agent_b_work_318"]
        self.assertTrue(agent_b["merged"])
        self.assertEqual(agent_b["implementation_pr"], 324)

    def test_preproof_research_uses_existing_exploratory_path_without_freeze(self) -> None:
        policy = self.methodology["preproof_exploratory_execution"]
        self.assertEqual(policy["mode"], "governed_exploratory_schema_v3")
        self.assertFalse(policy["preregistration_required"])
        self.assertEqual(
            policy["permitted_outcome_roles"], ["development", "rolling_research_oos"]
        )
        self.assertEqual(
            policy["protected_confirmation_roles"], ["reserved_confirmation", "sealed_confirmation"]
        )
        self.assertFalse(
            self.synthesis["phase_0_transition"]["critical_path"]["new_paid_data_acquisition"]
        )
        self.assertNotIn(
            "valid_preregistration", self.methodology["new_exploratory_execution_requires"]
        )
        execution_detail = next(
            item
            for item in self.methodology["governed_research_workflow_details"]
            if item["stage_id"] == "execute"
        )
        self.assertIn(
            "Schema-v3 exploratory execution uses the governed verified implementation/configuration and declared data roles; it does not require a preregistration freeze.",
            execution_detail["execution_rules"],
        )
        self.assertIn(
            "Confirmatory execution uses only the remotely frozen implementation/configuration and declared data roles.",
            execution_detail["execution_rules"],
        )
        retained = set(policy["required_controls"])
        self.assertTrue(
            {
                "point_in_time_semantics",
                "provenance",
                "dataset_reconstruction",
                "dataset_semantics",
                "immutable_data_assurance",
                "chronological_evaluation",
                "leakage_controls",
                "complete_search_history",
            }.issubset(retained)
        )


if __name__ == "__main__":
    unittest.main()
