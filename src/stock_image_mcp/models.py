"""Shared, provider-agnostic data models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ProviderName(StrEnum):
    UNSPLASH = "unsplash"
    PEXELS = "pexels"
    PIXABAY = "pixabay"
    FREEPIK = "freepik"
    STOCKVAULT = "stockvault"
    BURST = "burst"
    GOOGLE = "google"


class Orientation(StrEnum):
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    SQUARE = "square"


class SearchParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str
    orientation: Orientation | None = None
    per_page: int = 10
    page: int = 1


class ImageResult(BaseModel):
    """Normalized image result, common across all providers."""

    model_config = ConfigDict(frozen=True)

    id: str
    provider: ProviderName
    url: str
    thumbnail_url: str
    width: int | None = None
    height: int | None = None
    description: str | None = None
    photographer_name: str | None = None
    photographer_url: str | None = None
    license: str
    attribution_required: bool
    source_page_url: str
    # True when the provider gives no licence guarantee (Google Images): the
    # image may be copyrighted and must be checked before it is published.
    copyright_unverified: bool = False


class RateLimitStatus(BaseModel):
    provider: ProviderName
    limit: int
    window_seconds: int
    remaining: int
    configured: bool
