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

    # Model names are settings so a provider retiring or gating a model can be
    # fixed from the hosting dashboard instead of needing a redeploy.
    # gemini-2.5-flash is closed to new projects (404 on generateContent even
    # though the model still lists); 3.6-flash was the fastest reliable 3.x.
    gemini_model: str = "gemini-3.6-flash"
    # Gemini 3.x thinks before answering by default, which took classification
    # from ~2s to 14-21s.  Triage prompts don't need it.  Empty = model default.
    gemini_thinking_level: str = "minimal"
    # llama-3.3-70b-versatile is not available to every Groq account (it 404s
    # for the production key); qwen3.8-27b answers in natural Lebanese Arabic
    # in ~3s.
    groq_model: str = "qwen/qwen3.8-27b"
    # Groq's free tier limits *output tokens per minute* (1000 for qwen) and
    # counts each request's max_tokens against it up front, so asking for the
    # 2048 the prompts request got every call rejected as "too large".  Real
    # triage JSON and replies use 50-400 tokens.
    groq_max_tokens: int = 500
    # Which provider answers first: "groq" or "gemini"; the other is the backup.
    # Groq is first because it answered in 1.5-3s every time, while the Gemini
    # free tier took 7-14s and often returned 503 "high demand".  Flip this from
    # the dashboard if that changes.
    llm_primary: str = "groq"

    # Client-side pacing, in requests per minute.  Defaults target the free
    # tiers of Gemini flash (10 RPM) and Groq (30 RPM);
    # raise them if the deployment has paid quota.
    gemini_rpm: int = 10
    groq_rpm: int = 30
    # How long to skip a provider after it returns 429/401/403.
    provider_cooldown_seconds: float = 60.0


settings = Settings()
