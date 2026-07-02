from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pydantic import Field


class Settings(BaseSettings):
    # Keep DB path stable regardless of current working directory.
    # Default to a file inside backend/new/ (which exists in-repo).
    database_url: str = "sqlite:///./backend/new/job_extract.db"
    llm_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias="JOBEXTRACT_LLM_BASE_URL",
    )
    llm_model: str = Field(
        default="mistral",
        validation_alias="JOBEXTRACT_LLM_MODEL",
    )
    llm_api_key: Optional[str] = None
    groq_api_key: Optional[str] = Field(
        default=None,
        validation_alias="GROQ_API_KEY"
    )
    llm_provider: str = "ollama"
    max_retries: int = 2
    retry_base_delay: float = 1.0
    max_concurrent_runs: int = 5
    rate_limit_per_domain: int = 1
    playwright_headless: bool = True

    # Redis configuration
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = False
    redis_queue_key: str = "pipeline:queue"
    redis_llm_token_key: str = "llm:tokens"
    llm_rate_per_minute: int = 30
    llm_burst_size: int = 10

    model_config = SettingsConfigDict(
        env_prefix="JOBEXTRACT_",
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
