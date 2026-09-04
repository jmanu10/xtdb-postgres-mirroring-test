from functools import cached_property
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(directory: str) -> Path:
    candidate = Path(directory)
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    postgres_host: str = "localhost"
    postgres_port: int = 6532
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "mirror"
    publish_generated_columns: str = "stored"
    xtdb_host: str = "localhost"
    xtdb_port: int = 6533
    xtdb_user: str = "xtdb"
    xtdb_db: str = "xtdb"
    xtdb_remote: str = "mirror_pg"
    use_cases_dir: str = "use-cases"
    xtdb_container: str = "mirror-poc-xtdb"

    @cached_property
    def postgres_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @cached_property
    def xtdb_url(self) -> str:
        return (
            f"postgresql://{self.xtdb_user}@{self.xtdb_host}:{self.xtdb_port}"
            f"/{self.xtdb_db}"
        )

    @cached_property
    def use_cases_path(self) -> Path:
        return project_path(self.use_cases_dir)


def load_settings() -> Settings:
    return Settings()
