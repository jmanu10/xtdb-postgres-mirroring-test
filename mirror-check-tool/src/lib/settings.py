from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    source_url: str = "postgresql://postgres:postgres@localhost:6532/mirror"
    mirror_url: str = "postgresql://xtdb@localhost:6533/xtdb"
    mirror_database: str = "mirror"
    publication_name: str = "mirror"
