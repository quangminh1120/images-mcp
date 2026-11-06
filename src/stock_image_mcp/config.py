"""Environment-driven configuration for the server and its providers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from stock_image_mcp.models import ProviderName


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator(
        "unsplash_access_key",
        "pexels_api_key",
        "pixabay_api_key",
        "freepik_api_key",
        "stockvault_api_key",
        "serpapi_key",
        "google_license_filter",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, value: Any) -> Any:
        # `PEXELS_API_KEY=` (left blank, as in .env.example) must mean "not
        # configured", not an empty key that gets sent and rejected upstream.
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    unsplash_access_key: str | None = None
    unsplash_tier: str = "demo"  # "demo" (50/hr) or "production" (5000/hr)

    pexels_api_key: str | None = None

    pixabay_api_key: str | None = None

    freepik_api_key: str | None = None
    freepik_requests_per_minute: int = 60

    stockvault_api_key: str | None = None
    stockvault_requests_per_hour: int = 60

    burst_requests_per_minute: int = 10  # self-imposed, polite default (no official API)

    # Google Images via SerpAPI (paid: 100 free searches/month, then ~$0.01 each).
    serpapi_key: str | None = None
    serpapi_requests_per_hour: int = 20
    google_in_search_all: bool = False  # off: search_all_images skips Google unless asked
    google_license_filter: str | None = None  # SerpAPI "licenses": f, fc, fm, fmc, cl, ol

    default_provider: ProviderName = ProviderName.PEXELS
    download_dir: Path = Path("./downloads")

    def api_key_for(self, provider: ProviderName) -> str | None:
        return {
            ProviderName.UNSPLASH: self.unsplash_access_key,
            ProviderName.PEXELS: self.pexels_api_key,
            ProviderName.PIXABAY: self.pixabay_api_key,
            ProviderName.FREEPIK: self.freepik_api_key,
            ProviderName.STOCKVAULT: self.stockvault_api_key,
            ProviderName.BURST: "unofficial",  # no key required/possible
            ProviderName.GOOGLE: self.serpapi_key,
        }[provider]

    def is_configured(self, provider: ProviderName) -> bool:
        return self.api_key_for(provider) is not None


def get_settings() -> Settings:
    return Settings()
