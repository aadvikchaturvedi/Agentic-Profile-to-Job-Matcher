from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):
    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"

    # LLM model name (also reads from JOBEXTRACT_LLM_MODEL env var for
    # compatibility with the new pipeline's Settings class).
    llm_model: str = Field(default="mistral", validation_alias="JOBEXTRACT_LLM_MODEL")

    # Security
    groq_api_key: str = ""

    # Embeddings (hybrid scoring)
    enable_embeddings: bool = False
    embedding_model: str = "all-MiniLM-L6-v2"

    # Weights
    weights_path: str = "scoring_weights.yaml"

    # Scraping
    proxy_list: str = ""
    headless: bool = True
    cookie_file: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def effective_ollama_url(self) -> str:
        return self.ollama_url or self.ollama_base_url

    @property
    def proxy_list_parsed(self) -> List[str]:
        if not self.proxy_list:
            return []
        return [p.strip() for p in self.proxy_list.split(",") if p.strip()]


settings = Settings()
