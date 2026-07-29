from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    postgres_db: str = "eln"
    postgres_user: str = "eln_user"
    postgres_password: str = "eln_password"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    secret_key: str = "change-me-in-production"
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"
    seed_demo_data: bool = False
    access_token_expire_minutes: int = 480
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    app_revision: str = "unversioned"
    deepseek_api_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_max_concurrency: int = 4
    embedding_model: str = "rust-hash-512-v1"
    embedding_dimension: int = 512
    embedding_cache_path: str = "/models/fastembed"
    rag_chunk_size: int = 700
    rag_chunk_overlap: int = 120
    rag_retrieval_top_k: int = 6
    rag_collection_retrieval_top_k: int = 12
    rag_vector_candidate_k: int = 30
    rag_graph_top_k: int = 10
    rag_graph_min_score: float = 1.0
    document_text_max_chars: int = 2_000_000
    upload_max_bytes: int = 50 * 1024 * 1024
    ocr_languages: str = "chi_sim+eng"
    ocr_preprocessing: str = "grayscale_otsu"
    ocr_page_segmentation_mode: int = 3
    login_ip_rate_limit_max_attempts: int = 10
    login_ip_rate_limit_window_seconds: int = 60
    db_pool_size: int = 5
    db_max_overflow: int = 3
    db_pool_recycle: int = 1800
    db_pool_timeout: int = 30
    storage_root: Path = Path("/storage")

    @property
    def normalized_deepseek_model(self) -> str:
        # Accept accidental shell-style inline comments in local .env files.
        return self.deepseek_model.split("#", 1)[0].strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def validate_runtime(self) -> None:
        # Secret hygiene is enforced for every non-development environment so a
        # deployment cannot run with default credentials just because APP_ENV
        # was left unset or misspelled short of "production".
        if self.app_env == "development":
            return
        problems: list[str] = []
        if self.secret_key == "change-me-in-production" or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be changed and contain at least 32 characters")
        if self.bootstrap_admin_password == "admin123" or len(self.bootstrap_admin_password) < 12:
            problems.append("BOOTSTRAP_ADMIN_PASSWORD must be changed and contain at least 12 characters")
        if self.postgres_password == "eln_password" or len(self.postgres_password) < 12:
            problems.append("POSTGRES_PASSWORD must be changed and contain at least 12 characters")
        if self.seed_demo_data:
            problems.append("SEED_DEMO_DATA must be false")
        if self.app_env == "production":
            # Deployment metadata is only mandatory for real releases.
            if not self.deepseek_api_key.strip():
                problems.append("DEEPSEEK_API_KEY must be configured")
            if not self.app_revision.strip() or self.app_revision == "unversioned":
                problems.append("APP_REVISION must identify the deployed release")
        if problems:
            raise RuntimeError(f"Unsafe {self.app_env} configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
