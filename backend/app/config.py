from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from project root (parent of backend/)
_env_file = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_env_file), extra="ignore")

    app_name: str = "Hakim"
    debug: bool = False
    # Accept one key or several comma-separated ones. Free-tier quota is per
    # key, so listing spares lets a batch run continue past an exhausted key
    # instead of failing the rest of its work.
    gemini_api_key: str = ""
    groq_api_key: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://us.cloud.langfuse.com"
    allowed_origins: str = "http://localhost:3000"

    # Client-side pacing, in requests per minute.  Defaults target the free
    # tiers of gemini-2.5-flash (10 RPM) and llama-3.3-70b-versatile (30 RPM);
    # raise them if the deployment has paid quota.
    gemini_rpm: int = 10
    groq_rpm: int = 30
    # How long to skip a provider after it returns 429/401/403.
    provider_cooldown_seconds: float = 60.0


settings = Settings()
