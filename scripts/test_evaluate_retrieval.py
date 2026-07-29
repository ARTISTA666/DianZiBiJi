from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("evaluate_retrieval.py")
SPEC = importlib.util.spec_from_file_location("evaluate_retrieval", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RetrievalEvaluationTests(unittest.TestCase):
    def test_rrf_rewards_items_present_in_both_rankings(self):
        ranking, scores = MODULE.reciprocal_rank_fusion(
            [["chunk-a", "chunk-b"], ["chunk-b", "chunk-c"]]
        )

        self.assertEqual(ranking[0], "chunk-b")
        self.assertGreater(scores["chunk-b"], scores["chunk-a"])

    def test_evidence_ranking_keeps_irrelevant_position_and_deduplicates_facts(self):
        question = {
            "id": "Q1",
            "facts": [
                {"label": "A", "aliases": ["alpha"]},
                {"label": "B", "aliases": ["beta"]},
            ],
        }
        evidence = {
            "e0": MODULE.Evidence("e0", "chunk", "unrelated", "a.txt"),
            "e1": MODULE.Evidence("e1", "chunk", "alpha and beta", "b.txt"),
            "e2": MODULE.Evidence("e2", "graph", "alpha", "relation"),
        }

        run, trace = MODULE.evidence_ranking_to_fact_run(
            "bm25", question, ["e0", "e1", "e2"], evidence
        )
        ranked = [item for item, _ in sorted(run.items(), key=lambda item: -item[1])]

        self.assertTrue(ranked[0].startswith("Q1:I:bm25"))
        self.assertEqual(ranked[1:], ["Q1:F01", "Q1:F02", "Q1:I:bm25:00003"])
        self.assertEqual([row["evidence_rank"] for row in trace], [2, 2])

    def test_ir_measures_calculates_expected_metrics(self):
        qrels = {"Q1": {"Q1:F01": 1, "Q1:F02": 1}}
        run = {
            "Q1": {
                "Q1:I:test:00001": 3.0,
                "Q1:F01": 2.0,
                "Q1:F02": 1.0,
            }
        }
        runs = {mode: run for mode in MODULE.MODES}

        aggregate, _ = MODULE.calculate_metrics(qrels, runs)

        self.assertEqual(aggregate[0]["Recall@1"], 0.0)
        self.assertEqual(aggregate[0]["Recall@3"], 1.0)
        self.assertEqual(aggregate[0]["MRR"], 0.5)

    def test_ablation_delta_uses_full_condition_as_baseline(self):
        rows = [
            {"mode": "full", "Recall@1": 0.5, "Recall@3": 0.5, "Recall@5": 0.5, "Recall@10": 0.5, "MRR": 0.4, "nDCG@10": 0.3},
            {"mode": "without_graph", "Recall@1": 0.5, "Recall@3": 0.4, "Recall@5": 0.4, "Recall@10": 0.3, "MRR": 0.3, "nDCG@10": 0.2},
        ]

        result = MODULE.ablation_delta_rows(rows)

        self.assertEqual(result[0]["delta_Recall@10"], 0.0)
        self.assertEqual(result[1]["delta_Recall@10"], -0.2)
        self.assertEqual(result[1]["delta_MRR"], -0.1)


if __name__ == "__main__":
    unittest.main()
