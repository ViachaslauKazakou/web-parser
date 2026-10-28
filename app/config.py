from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://forumscope:forumscope_dev@localhost:5432/forumscope"
    parser_allowed_hosts: str = "searchengines.guru"
    max_upload_bytes: int = 5 * 1024 * 1024
    max_request_body_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    max_import_messages: int = 2000
    max_parser_pages: int = Field(default=20, ge=1, le=100)
    max_parser_page_chars: int = Field(default=2_000_000, ge=100_000, le=10_000_000)
    parser_timeout_ms: int = 3000
    parser_total_timeout_seconds: int = Field(default=180, ge=5, le=600)
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 45.0

    @property
    def allowed_forum_hosts(self) -> tuple[str, ...]:
        hosts = (host.strip().lower().rstrip(".") for host in self.parser_allowed_hosts.split(","))
        configured = tuple(host for host in hosts if host)
        return tuple(dict.fromkeys(("searchengines.guru", *configured)))


@lru_cache
def get_settings() -> Settings:
    return Settings()
