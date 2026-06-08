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
    dify_api_base_url: str = "http://localhost"
    dify_dataset_api_key: str = ""
    dify_chat_app_api_key: str = ""
    dify_default_indexing_technique: str = "high_quality"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
