"""Validate the preregistered bundle required before confirmatory human review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


MIN_PROJECTS = 3
MIN_QUESTIONS = 60
MIN_REVIEWERS = 2
MIN_QUESTIONS_PER_PROJECT = 10
REQUIRED_METHODS = {"pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def question_text(question: dict[str, Any]) -> str:
    return str(question.get("question") or question.get("text") or question.get("query") or "").strip()


def validate(bundle: dict[str, Any], *, root: Path) -> dict[str, Any]:
    failures: list[str] = []
    projects = bundle.get("projects") or []
    questions = bundle.get("questions") or []
    reviewers = bundle.get("reviewers") or []
    files = bundle.get("files") or []
    methods = set(bundle.get("methods") or [])
    if not isinstance(projects, list) or len(projects) < MIN_PROJECTS:
        failures.append(f"freeze must contain at least {MIN_PROJECTS} projects")
    if not isinstance(questions, list) or len(questions) < MIN_QUESTIONS:
        failures.append(f"freeze must contain at least {MIN_QUESTIONS} questions")
    if not isinstance(reviewers, list) or len(reviewers) < MIN_REVIEWERS:
        failures.append(f"freeze must name at least {MIN_REVIEWERS} independent reviewers")
    if methods != REQUIRED_METHODS:
        failures.append("freeze methods must exactly match: " + ", ".join(sorted(REQUIRED_METHODS)))
    if not str(bundle.get("model") or "").strip():
        failures.append("freeze must lock model")
    if not str(bundle.get("prompt_version") or "").strip():
        failures.append("freeze must lock prompt_version")
    if bundle.get("random_seed") in (None, ""):
        failures.append("freeze must lock random_seed")

    project_id_list = [
        str(project.get("project_id") or project.get("id") or "").strip()
        for project in projects
        if isinstance(project, dict)
    ]
    if len(project_id_list) != len(projects) or len(project_id_list) != len(set(project_id_list)) or not all(project_id_list):
        failures.append("project ids must be non-empty and unique")
    project_ids = set(project_id_list)
    question_project_ids = {
        str(question.get("project_id") or "").strip()
        for question in questions
        if str(question.get("project_id") or "").strip()
    }
    if project_ids and question_project_ids and not question_project_ids.issubset(project_ids):
        failures.append("questions reference projects missing from freeze.projects")
    if project_ids:
        question_counts = {project_id: 0 for project_id in project_ids if project_id}
        for question in questions if isinstance(questions, list) else []:
            project_id = str(question.get("project_id") or "").strip()
            if project_id in question_counts:
                question_counts[project_id] += 1
        thin_projects = [project_id for project_id, count in sorted(question_counts.items()) if count < MIN_QUESTIONS_PER_PROJECT]
        if thin_projects:
            failures.append(
                f"each project must have at least {MIN_QUESTIONS_PER_PROJECT} questions: "
                + ", ".join(thin_projects[:10])
            )

    question_ids = [str(question.get("question_id") or question.get("id") or "").strip() for question in questions if isinstance(question, dict)]
    if len(question_ids) != len(questions) or len(question_ids) != len(set(question_ids)) or not all(question_ids):
        failures.append("question ids must be non-empty and unique")
    question_indices = []
    for question in questions if isinstance(questions, list) else []:
        try:
            question_indices.append(int(question["question_index"]))
        except (KeyError, TypeError, ValueError):
            failures.append("questions must include numeric question_index")
            break
    if len(question_indices) != len(set(question_indices)):
        failures.append("question_index values must be unique")
    question_text_by_index: dict[int, str] = {}
    for question in questions if isinstance(questions, list) else []:
        text = question_text(question)
        if not text:
            failures.append("questions must include non-empty question text")
            break
        try:
            question_text_by_index[int(question["question_index"])] = text
        except (KeyError, TypeError, ValueError):
            pass

    missing_fact_questions = [
        str(question.get("question_id") or question.get("id") or index + 1)
        for index, question in enumerate(questions)
        if not question.get("gold_facts")
    ]
    if missing_fact_questions:
        failures.append("questions without gold_facts: " + ", ".join(missing_fact_questions[:10]))

    reviewer_ids = [str(reviewer.get("reviewer_id") or reviewer.get("id") or "").strip() for reviewer in reviewers]
    if len(reviewer_ids) != len(reviewers) or len(reviewer_ids) != len(set(reviewer_ids)) or not all(reviewer_ids):
        failures.append("reviewer ids must be non-empty and unique")
    reviewer_user_ids = []
    for reviewer in reviewers if isinstance(reviewers, list) else []:
        try:
            reviewer_user_ids.append(int(reviewer["user_id"]))
        except (KeyError, TypeError, ValueError):
            failures.append("reviewers must include numeric user_id")
            break
    if len(reviewer_user_ids) != len(set(reviewer_user_ids)):
        failures.append("reviewer user_id values must be unique")
    if any(reviewer.get("involved_in_development") for reviewer in reviewers):
        failures.append("reviewers must not be marked involved_in_development")
    bad_permissions = [
        str(reviewer.get("reviewer_id") or reviewer.get("id") or index + 1)
        for index, reviewer in enumerate(reviewers if isinstance(reviewers, list) else [])
        if not (
            reviewer.get("can_read") is False
            and reviewer.get("can_evaluate") is True
            and not reviewer.get("can_write")
            and not reviewer.get("can_review")
            and not reviewer.get("can_manage")
        )
    ]
    if bad_permissions:
        failures.append("reviewers must have only can_evaluate=true: " + ", ".join(bad_permissions[:10]))

    file_checks = []
    root_resolved = root.resolve()
    for entry in files:
        relative = str(entry.get("path") or "").strip() if isinstance(entry, dict) else ""
        expected = str(entry.get("sha256") or "").strip() if isinstance(entry, dict) else ""
        path = (root / relative).resolve()
        inside_root = bool(relative) and not Path(relative).is_absolute() and path.is_relative_to(root_resolved)
        exists = inside_root and path.is_file()
        actual = sha256_file(path) if exists else None
        ok = inside_root and exists and bool(expected) and actual == expected
        file_checks.append({"path": relative, "inside_root": inside_root, "exists": exists, "sha256_matches": ok})
        if not ok:
            failures.append(f"file hash mismatch or missing: {relative}")
    if not file_checks:
        failures.append("freeze must contain hash-checked files")

    return {
        "passed": not failures,
        "failures": failures,
        "project_count": len(projects) if isinstance(projects, list) else 0,
        "question_count": len(questions) if isinstance(questions, list) else 0,
        "question_indices": sorted(question_indices),
        "question_text_by_index": {str(key): value for key, value in sorted(question_text_by_index.items())},
        "reviewer_count": len(reviewers) if isinstance(reviewers, list) else 0,
        "reviewer_user_ids": sorted(reviewer_user_ids),
        "methods": sorted(methods),
        "file_checks": file_checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("freeze", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    result = validate(json.loads(args.freeze.read_text(encoding="utf-8")), root=args.root)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
