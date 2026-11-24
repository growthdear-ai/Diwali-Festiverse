"""Application configuration loaded from environment variables / .env."""

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Nazar Rakho"
    app_env: str = "development"
    secret_key: str = "dev-insecure-secret-change-me"
    access_token_expire_minutes: int = 60 * 24 * 7

    database_url: str = "sqlite:///./nazar.db"

    serpapi_api_key: str = ""
    you_api_key: str = ""

    nexconn_app_key: str = ""
    nexconn_app_secret: str = ""
    nexconn_api_host: str = "https://api.sg-light-api.com"
    nexconn_bot_user_id: str = "nazar-bot"
    nexconn_bot_name: str = "Nazar"
    nexconn_webhook_secret: str = ""
    nexconn_alert_message_type: str = "NZ:AlertCard"
    nexconn_search_message_type: str = "NZ:SearchCard"
    nexconn_auto_create_groups: bool = False

    # "auto" resolves to Ollama when no OpenAI key is available or the base URL
    # points at a local Ollama server; explicit "ollama"/"openai" always wins.
    llm_provider: str = "auto"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "llama3.2:3b"
    llm_ollama_model: str = "llama3.2:3b"
    llm_timeout_seconds: int = 120

    frontend_url: str = "http://localhost:3000"

    scheduler_enabled: bool = True
    watch_interval_minutes: int = 30
    max_alerts_per_watch_per_day: int = 1
    max_watches_per_run: int = 20
    morning_brief_enabled: bool = True
    morning_brief_hour_utc: int = 1
    brief_language: str = "en"

    rate_limit_per_minute: int = 120
    internal_api_token: str = ""

    serpapi_timeout_seconds: int = 25
    serpapi_cache_ttl_seconds: int = 600
    you_research_timeout_seconds: int = 90
    you_finance_timeout_seconds: int = 240

    # Lyzr Enterprise Agent (structured verification of watch results)
    lyzr_enabled: bool = False
    lyzr_api_key: str = ""
    lyzr_agent_id: str = ""
    lyzr_agent_url: str = ""

    # BAND Collaboration (Scout→Verifier agent handoff in a BAND room)
    band_enabled: bool = False
    band_scout_agent_id: str = ""
    band_scout_api_key: str = ""
    band_verifier_agent_id: str = ""
    band_verifier_api_key: str = ""
    band_room_id: str = ""
    band_api_host: str = "https://api.band.ai"
    band_ws_host: str = "wss://api.band.ai"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def nexconn_configured(self) -> bool:
        return bool(self.nexconn_app_key and self.nexconn_app_secret and self.nexconn_api_host)

    @property
    def serpapi_configured(self) -> bool:
        return bool(self.serpapi_api_key)

    @property
    def you_configured(self) -> bool:
        return bool(self.you_api_key)

    @property
    def lyzr_configured(self) -> bool:
        return self.lyzr_enabled and bool(self.lyzr_api_key and self.lyzr_agent_id)

    @property
    def band_configured(self) -> bool:
        return self.band_enabled and bool(
            self.band_scout_agent_id
            and self.band_scout_api_key
            and self.band_verifier_agent_id
            and self.band_verifier_api_key
            and self.band_room_id
        )

    @property
    def resolved_llm_provider(self) -> str:
        explicit = self.llm_provider.strip().lower()
        if explicit in {"ollama", "openai"}:
            return explicit
        base = (self.llm_base_url or "").lower()
        if "11434" in base or "localhost" in base or "127.0.0.1" in base:
            return "ollama"
        if self.llm_api_key:
            return "openai"
        return "ollama"

    @property
    def effective_llm_base_url(self) -> str:
        base = (self.llm_base_url or "").strip().rstrip("/")
        if self.resolved_llm_provider == "ollama":
            if not base or "api.openai.com" in base:
                return "http://localhost:11434"
            return base
        return base or "https://api.openai.com/v1"

    @property
    def effective_llm_model(self) -> str:
        if self.resolved_llm_provider == "ollama" and (
            not self.llm_model or self.llm_model.startswith(("gpt", "o1", "o3", "text-"))
        ):
            return self.llm_ollama_model
        return self.llm_model

    @property
    def llm_configured(self) -> bool:
        # A local Ollama server needs no API key; OpenAI-compatible providers do.
        if self.resolved_llm_provider == "ollama":
            return True
        return bool(self.llm_api_key)

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.frontend_url.rstrip("/")}
        if not self.is_production:
            origins.update({"http://localhost:3000", "http://127.0.0.1:3000"})
        return sorted(origins)


INSECURE_SECRET_KEYS = {
    "",
    "dev-insecure-secret-change-me",
    "change-me-to-a-long-random-string",
}


def validate_runtime_settings() -> None:
    """Fail fast on unsafe production configuration and warn on weak choices."""

    if not settings.is_production:
        return

    problems: list[str] = []
    if settings.secret_key in INSECURE_SECRET_KEYS or len(settings.secret_key) < 32:
        problems.append("SECRET_KEY must be a random value of at least 32 characters")
    if not settings.frontend_url.startswith("https://"):
        logger.warning("FRONTEND_URL is not HTTPS in production")
    if not settings.internal_api_token:
        logger.warning(
            "INTERNAL_API_TOKEN is not set; internal monitoring endpoints will reject requests in production"
        )
    if not settings.nexconn_webhook_secret:
        logger.warning(
            "NEXCONN_WEBHOOK_SECRET is not set; protect the webhook endpoint at the network layer"
        )
    if settings.database_url.startswith("sqlite"):
        logger.warning(
            "SQLite is configured in production; use PostgreSQL for multi-instance deployments"
        )
    if not settings.serpapi_configured or not settings.you_configured:
        logger.warning("A live data provider key is missing; related watches will be unavailable")

    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
