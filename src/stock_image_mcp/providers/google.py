"""Google Images results via SerpAPI's ``google_images`` engine.

Unlike every other provider here, Google returns images from across the whole
web with *no* licence guarantee. Each result is therefore flagged
``copyright_unverified=True`` and its licence text says so; the caller must
check the source page before publishing the image anywhere.

SerpAPI is paid (100 free searches/month, then roughly $0.01 each), so the
server leaves this provider out of ``search_all_images`` unless asked.
"""

from __future__ import annotations

import hashlib

import httpx

from stock_image_mcp.models import ImageResult, Orientation, ProviderName, SearchParams
from stock_image_mcp.providers.base import ImageProvider

_ENDPOINT = "https://serpapi.com/search.json"

# SerpAPI google_images "imgar" (aspect ratio): t=tall, s=square, w=wide.
_ORIENTATION_MAP = {
    Orientation.LANDSCAPE: "w",
    Orientation.PORTRAIT: "t",
    Orientation.SQUARE: "s",
}

# SerpAPI google_images "licenses" values.
LICENSE_FILTERS = frozenset({"f", "fc", "fm", "fmc", "cl", "ol"})

_NO_RESULTS_PREFIX = "Google hasn't returned any results"

LICENSE_TEXT = "Unknown — Google Images result; may be copyrighted, verify on the source page"


class GoogleProviderError(RuntimeError):
    """SerpAPI failure, with a message that never contains the API key."""


class GoogleProvider(ImageProvider):
    name = ProviderName.GOOGLE
    requires_api_key = True

    def __init__(
        self,
        api_key: str | None,
        client: httpx.AsyncClient,
        license_filter: str | None = None,
    ) -> None:
        super().__init__(api_key, client)
        if license_filter and license_filter not in LICENSE_FILTERS:
            allowed = ", ".join(sorted(LICENSE_FILTERS))
            raise ValueError(f"GOOGLE_LICENSE_FILTER must be one of: {allowed}")
        self.license_filter = license_filter or None

    async def search(self, params: SearchParams) -> list[ImageResult]:
        query: dict[str, str | int] = {
            "engine": "google_images",
            "q": params.query,
            "ijn": max(params.page - 1, 0),  # SerpAPI pages are 0-based
            "api_key": self.api_key or "",
        }
        if params.orientation is not None:
            query["imgar"] = _ORIENTATION_MAP[params.orientation]
        if self.license_filter:
            query["licenses"] = self.license_filter

        try:
            response = await self.client.get(_ENDPOINT, params=query)
        except httpx.HTTPError as exc:
            # The exception's request URL carries api_key; report only the type.
            raise GoogleProviderError(f"SerpAPI request failed ({type(exc).__name__})") from None

        try:
            data = response.json()
        except ValueError:
            data = {}
        error = data.get("error") if isinstance(data, dict) else None
        if error and str(error).startswith(_NO_RESULTS_PREFIX):
            return []
        if response.status_code >= 400 or error:
            detail = str(error or f"HTTP {response.status_code}")
            if self.api_key:
                detail = detail.replace(self.api_key, "***")
            raise GoogleProviderError(f"SerpAPI error: {detail[:200]}")

        results: list[ImageResult] = []
        for item in data.get("images_results", []):
            original = item.get("original")
            if not original:
                continue
            source_page = item.get("link") or original
            results.append(
                ImageResult(
                    id=hashlib.sha1(original.encode()).hexdigest()[:16],
                    provider=self.name,
                    url=original,
                    thumbnail_url=item.get("thumbnail") or original,
                    width=item.get("original_width"),
                    height=item.get("original_height"),
                    description=item.get("title") or None,
                    photographer_name=item.get("source") or None,
                    photographer_url=item.get("link") or None,
                    license=LICENSE_TEXT,
                    attribution_required=True,
                    source_page_url=source_page,
                    copyright_unverified=True,
                )
            )
            if len(results) >= params.per_page:
                break
        return results

    def build_attribution(self, image: ImageResult) -> str:
        site = image.photographer_name or "the source site"
        return (
            f"Image from {site} ({image.source_page_url}), found via Google Images — "
            "copyright NOT verified: check the source page's licence or get permission "
            "before publishing"
        )
