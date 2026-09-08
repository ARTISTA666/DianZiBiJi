"""Run the shared Rust/Python security vectors against the Python implementation.

The same fixture file is compiled into the Rust backend tests
(backend/src/security.rs), so any divergence between the two password/JWT
implementations fails one of the suites instead of surfacing in production.
"""

import json
from pathlib import Path

import pytest

from app.core import security
from app.core.config import get_settings

VECTORS = json.loads((Path(__file__).parent / "security_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("vector", VECTORS["password_vectors"], ids=lambda v: v["name"])
def test_password_vectors_match_python_implementation(vector) -> None:
    assert security.verify_password(vector["password"], vector["hash"]) is vector["matches"]


@pytest.mark.parametrize("vector", VECTORS["jwt_vectors"], ids=lambda v: v["name"])
def test_jwt_vectors_match_python_implementation(vector, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "secret_key", VECTORS["jwt_secret"])

    claims = security.decode_access_token_claims(vector["token"])

    if vector["valid"]:
        assert claims == (vector["subject"], vector["auth_version"])
    else:
        assert claims is None


def test_freshly_hashed_password_uses_a_format_rust_supports() -> None:
    new_hash = security.hash_password("cross-runtime-check")

    assert new_hash.startswith(("$pbkdf2-sha256$", "$2")), new_hash
    assert security.verify_password("cross-runtime-check", new_hash)
