"""Drift-detection test: Python PROMPTS registry vs Rust hardcoded versions.

Guards against the Python prompt registry (``app.services.prompts.PROMPTS``)
and the Rust source files (``src/api/rag.rs``, ``src/api/agents.rs``) drifting
apart on prompt-version identifiers.  Each Python ``PromptSpec.version`` must
have a matching string literal somewhere in the corresponding Rust source.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Resolve paths relative to this test file so it works from any cwd.
# ---------------------------------------------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_RAG_RS = _BACKEND_ROOT / "src" / "api" / "rag.rs"
_AGENTS_RS = _BACKEND_ROOT / "src" / "api" / "agents.rs"

# Import the live Python registry.
import sys  # noqa: E402

sys.path.insert(0, str(_BACKEND_ROOT))
from app.services.prompts import PROMPTS  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_rust(path: Path) -> str:
    """Read a Rust source file, skipping if missing (graceful on CI)."""
    if not path.exists():
        pytest.skip(f"Rust source not found: {path}")
    return path.read_text(encoding="utf-8")


def _extract_rust_versions(source: str) -> set[str]:
    """Return all string literals that look like prompt version identifiers.

    Prompt versions follow the pattern ``<name>-v<N>[-<qualifier>]``
    (e.g. ``rag-v8-source-and-graph-citations``, ``agent-v5-citation-repair``).
    We match any ``"..."`` literal containing ``-v`` followed by a digit.
    """
    # Match quoted string literals containing "-v<digit>" (prompt version pattern).
    # Exclude obvious test fixtures like "test-v1".
    pattern = re.compile(r'"([a-z][\w-]*-v\d[\w-]*)"')
    return {m for m in pattern.findall(source) if not m.startswith("test-")}


# ---------------------------------------------------------------------------
# Mapping: Python prompt key → expected Rust file(s)
# ---------------------------------------------------------------------------
# project_rag / bm25_rag / pure_llm / structured_query live in rag.rs
# agent_writer lives in agents.rs
_PROMPT_TO_RUST: dict[str, list[Path]] = {
    "project_rag": [_RAG_RS],
    "bm25_rag": [_RAG_RS],
    "pure_llm": [_RAG_RS],
    "structured_query": [_RAG_RS],
    "agent_writer": [_AGENTS_RS],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prompt_key", list(PROMPTS.keys()))
def test_python_version_exists_in_rust(prompt_key: str) -> None:
    """Every Python PromptSpec version must appear verbatim in Rust source."""
    py_version = PROMPTS[prompt_key].version
    rust_files = _PROMPT_TO_RUST.get(prompt_key)
    if rust_files is None:
        pytest.fail(f"No Rust file mapping for prompt key '{prompt_key}'")

    all_rust_versions: set[str] = set()
    for rust_path in rust_files:
        source = _read_rust(rust_path)
        all_rust_versions |= _extract_rust_versions(source)

    assert py_version in all_rust_versions, (
        f"Python prompt '{prompt_key}' has version '{py_version}' "
        f"but it was not found in Rust source(s) "
        f"{[p.name for p in rust_files]}. "
        f"Rust versions found: {sorted(all_rust_versions)}"
    )


def test_no_orphan_rust_versions() -> None:
    """Every prompt version in Rust should have a corresponding Python entry."""
    python_versions = {spec.version for spec in PROMPTS.values()}

    all_rust_versions: set[str] = set()
    for rust_path in [_RAG_RS, _AGENTS_RS]:
        source = _read_rust(rust_path)
        all_rust_versions |= _extract_rust_versions(source)

    orphans = all_rust_versions - python_versions
    assert not orphans, (
        f"Rust source contains prompt versions not in Python registry: "
        f"{sorted(orphans)}. Python versions: {sorted(python_versions)}"
    )


def test_bm25_rag_shares_system_prompt_with_project_rag() -> None:
    """bm25_rag must reuse project_rag's system_prompt (no duplication)."""
    assert PROMPTS["bm25_rag"].system_prompt == PROMPTS["project_rag"].system_prompt
    # They should be the exact same object (single-source-of-truth).
    assert PROMPTS["bm25_rag"].system_prompt is PROMPTS["project_rag"].system_prompt
