import pytest

from app.core.config import Settings


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(cors_origins=" http://localhost:3000, http://127.0.0.1:13000 ,, ")

    assert settings.cors_origin_list == [
        "http://localhost:3000",
        "http://127.0.0.1:13000",
    ]


def test_ocr_defaults_cover_project_languages() -> None:
    assert Settings().ocr_languages == "chi_sim+eng"


def test_rag_retrieval_limits_are_safe() -> None:
    settings = Settings(rag_retrieval_top_k=31, rag_vector_candidate_k=30)

    with pytest.raises(RuntimeError, match="RAG_RETRIEVAL_TOP_K"):
        settings.validate_runtime()


def test_production_rejects_default_secrets_and_demo_data() -> None:
    settings = Settings(app_env="production", seed_demo_data=True)

    with pytest.raises(RuntimeError, match="Unsafe production configuration") as error:
        settings.validate_runtime()

    assert "SECRET_KEY" in str(error.value)
    assert "BOOTSTRAP_ADMIN_PASSWORD" in str(error.value)
    assert "POSTGRES_PASSWORD" in str(error.value)
    assert "SEED_DEMO_DATA" in str(error.value)
    assert "DEEPSEEK_API_KEY" in str(error.value)
    assert "APP_REVISION" in str(error.value)


def test_non_development_env_rejects_default_secrets() -> None:
    settings = Settings(app_env="test")

    with pytest.raises(RuntimeError, match="Unsafe test configuration") as error:
        settings.validate_runtime()

    assert "SECRET_KEY" in str(error.value)
    assert "BOOTSTRAP_ADMIN_PASSWORD" in str(error.value)
    assert "POSTGRES_PASSWORD" in str(error.value)
    # Deployment metadata is only enforced in production.
    assert "DEEPSEEK_API_KEY" not in str(error.value)
    assert "APP_REVISION" not in str(error.value)


def test_test_env_accepts_non_default_secrets_without_release_metadata() -> None:
    settings = Settings(
        app_env="test",
        secret_key="s" * 32,
        bootstrap_admin_password="a-secure-bootstrap-password",
        postgres_password="a-secure-database-password",
        seed_demo_data=False,
    )

    settings.validate_runtime()


def test_production_accepts_explicit_safe_bootstrap_configuration() -> None:
    settings = Settings(
        app_env="production",
        secret_key="s" * 32,
        bootstrap_admin_password="a-secure-bootstrap-password",
        postgres_password="a-secure-database-password",
        seed_demo_data=False,
        deepseek_api_key="production-api-key",
        app_revision="release-2026.07.16",
    )

    settings.validate_runtime()
