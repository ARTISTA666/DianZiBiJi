from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_human_review_freeze.py"
SPEC = importlib.util.spec_from_file_location("validate_human_review_freeze", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def complete_bundle(root: Path) -> dict:
    corpus = root / "corpus.json"
    corpus.write_text('{"frozen": true}\n', encoding="utf-8")
    return {
        "methods": ["pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"],
        "model": "deepseek-v4-flash",
        "prompt_version": "confirmatory-review-v1",
        "random_seed": 20260716,
        "projects": [{"project_id": f"P{i}"} for i in range(1, 4)],
        "questions": [
            {
                "question_id": f"Q{i:02d}",
                "question_index": i,
                "question": f"Frozen question {i}?",
                "project_id": f"P{(i % 3) + 1}",
                "gold_facts": [f"fact-{i}"],
            }
            for i in range(60)
        ],
        "reviewers": [
            {
                "reviewer_id": "R1",
                "user_id": 2,
                "involved_in_development": False,
                "can_read": False,
                "can_evaluate": True,
                "can_write": False,
                "can_review": False,
                "can_manage": False,
            },
            {
                "reviewer_id": "R2",
                "user_id": 3,
                "involved_in_development": False,
                "can_read": False,
                "can_evaluate": True,
                "can_write": False,
                "can_review": False,
                "can_manage": False,
            },
        ],
        "files": [{"path": "corpus.json", "sha256": MODULE.sha256_file(corpus)}],
    }


class ValidateHumanReviewFreezeTests(unittest.TestCase):
    def test_accepts_complete_confirmatory_freeze_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = MODULE.validate(complete_bundle(root), root=root)

            self.assertTrue(result["passed"])
            self.assertEqual(result["project_count"], 3)
            self.assertEqual(result["question_count"], 60)
            self.assertEqual(result["question_indices"], list(range(60)))
            self.assertEqual(result["reviewer_user_ids"], [2, 3])
            self.assertEqual(result["methods"], ["bm25_rag", "kg_enhanced_rag", "project_rag", "pure_llm", "structured_query"])

    def test_rejects_internal_single_project_development_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = complete_bundle(root)
            bundle["projects"] = bundle["projects"][:1]
            bundle["questions"] = bundle["questions"][:20]
            bundle["reviewers"] = bundle["reviewers"][:1]

            result = MODULE.validate(bundle, root=root)

            self.assertFalse(result["passed"])
            self.assertIn("freeze must contain at least 3 projects", result["failures"])
            self.assertIn("freeze must contain at least 60 questions", result["failures"])
            self.assertIn("freeze must name at least 2 independent reviewers", result["failures"])

    def test_rejects_duplicate_questions_and_bad_reviewer_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = complete_bundle(root)
            bundle["questions"][1]["question_id"] = bundle["questions"][0]["question_id"]
            bundle["reviewers"][0]["can_write"] = True

            result = MODULE.validate(bundle, root=root)

            self.assertFalse(result["passed"])
            self.assertIn("question ids must be non-empty and unique", result["failures"])
            self.assertIn("reviewers must have only can_evaluate=true: R1", result["failures"])

    def test_rejects_reviewer_access_to_unblinded_project_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = complete_bundle(root)
            bundle["reviewers"][0]["can_read"] = True

            result = MODULE.validate(bundle, root=root)

            self.assertFalse(result["passed"])
            self.assertIn("reviewers must have only can_evaluate=true: R1", result["failures"])

    def test_rejects_empty_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = complete_bundle(root)
            bundle["projects"][0]["project_id"] = ""
            bundle["questions"][0]["question_id"] = ""
            bundle["reviewers"][0]["reviewer_id"] = ""

            result = MODULE.validate(bundle, root=root)

            self.assertFalse(result["passed"])
            self.assertIn("project ids must be non-empty and unique", result["failures"])
            self.assertIn("question ids must be non-empty and unique", result["failures"])
            self.assertIn("reviewer ids must be non-empty and unique", result["failures"])

    def test_rejects_missing_reviewer_user_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = complete_bundle(root)
            bundle["reviewers"][0].pop("user_id")

            result = MODULE.validate(bundle, root=root)

            self.assertFalse(result["passed"])
            self.assertIn("reviewers must include numeric user_id", result["failures"])

    def test_rejects_missing_question_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = complete_bundle(root)
            bundle["questions"][0].pop("question_index")

            result = MODULE.validate(bundle, root=root)

            self.assertFalse(result["passed"])
            self.assertIn("questions must include numeric question_index", result["failures"])

    def test_rejects_missing_question_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = complete_bundle(root)
            bundle["questions"][0].pop("question")

            result = MODULE.validate(bundle, root=root)

            self.assertFalse(result["passed"])
            self.assertIn("questions must include non-empty question text", result["failures"])

    def test_rejects_project_without_enough_questions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = complete_bundle(root)
            for question in bundle["questions"][:55]:
                question["project_id"] = "P1"

            result = MODULE.validate(bundle, root=root)

            self.assertFalse(result["passed"])
            self.assertTrue(any("each project must have at least 10 questions" in failure for failure in result["failures"]))

    def test_rejects_unfrozen_experiment_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = complete_bundle(root)
            bundle["methods"] = ["project_rag", "kg_enhanced_rag"]
            bundle.pop("model")
            bundle.pop("prompt_version")
            bundle.pop("random_seed")

            result = MODULE.validate(bundle, root=root)

            self.assertFalse(result["passed"])
            self.assertIn(
                "freeze methods must exactly match: bm25_rag, kg_enhanced_rag, project_rag, pure_llm, structured_query",
                result["failures"],
            )
            self.assertIn("freeze must lock model", result["failures"])
            self.assertIn("freeze must lock prompt_version", result["failures"])
            self.assertIn("freeze must lock random_seed", result["failures"])

    def test_rejects_extra_unfrozen_method(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = complete_bundle(root)
            bundle["methods"].append("new_agent_mode")

            result = MODULE.validate(bundle, root=root)

            self.assertFalse(result["passed"])
            self.assertIn(
                "freeze methods must exactly match: bm25_rag, kg_enhanced_rag, project_rag, pure_llm, structured_query",
                result["failures"],
            )

    def test_rejects_hash_file_outside_freeze_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / "outside-corpus.json"
            outside.write_text('{"frozen": true}\n', encoding="utf-8")
            bundle = complete_bundle(root)
            bundle["files"] = [{"path": f"../{outside.name}", "sha256": MODULE.sha256_file(outside)}]

            result = MODULE.validate(bundle, root=root)

            self.assertFalse(result["passed"])
            self.assertIn(f"file hash mismatch or missing: ../{outside.name}", result["failures"])
            self.assertFalse(result["file_checks"][0]["inside_root"])


if __name__ == "__main__":
    unittest.main()
