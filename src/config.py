from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # LLM
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    fallback_model_name: str = "gpt-4o"
    moderation_model_name: str = "omni-moderation-latest"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Reviewed Document policy corpus; deploy schema/data first, then enable canary retrieval.
    policy_rag_enabled: bool = False

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    # Lõi hội thoại v2 (spec 2026-08-29 mục 8)
    #: Danh sách `customer_id` bật lõi v2 bất kể phần trăm, ngăn bằng dấu phẩy.
    #:
    #: Kiểu CHUỖI chứ không `list[str]`: `pydantic-settings` cố JSON-decode mọi
    #: biến môi trường cho field kiểu phức, nên `CORE_V2_CUSTOMER_IDS=dat,long`
    #: sẽ nổ `SettingsError` ngay lúc khởi động thay vì tách theo dấu phẩy.
    #: `core.flag.customer_allowlist` là chỗ DUY NHẤT tách chuỗi này.


@lru_cache
def get_settings() -> Settings:
    return Settings()
