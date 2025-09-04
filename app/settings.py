from functools import lru_cache
from typing import Optional

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # API
    api_prefix: str = "/api"

    # Database
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "file_monitor"

    # Redis
    redis_url: str = "redis://127.0.0.1:6379/0"

    # DB schema management
    # Set to True to let the app auto-create tables on startup (dev only). For production, keep False and use Alembic.
    auto_create_tables: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"\
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()