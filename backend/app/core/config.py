from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    postgres_db: str = "eln"
    postgres_user: str = "eln_user"
    postgres_password: str = "eln_password"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 480
    deepseek_api_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    embedding_service_url: str = "http://embedding:8000"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512
    rag_chunk_size: int = 700
    rag_chunk_overlap: int = 120
    rag_retrieval_top_k: int = 6
    rag_vector_candidate_k: int = 30
    rag_graph_top_k: int = 10
    rag_graph_min_score: float = 1.0

    @property
    def normalized_deepseek_model(self) -> str:
        # Accept accidental shell-style inline comments in local .env files.
        return self.deepseek_model.split("#", 1)[0].strip()

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
