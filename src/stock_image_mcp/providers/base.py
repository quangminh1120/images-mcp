"""Abstract interface every image provider implements."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from stock_image_mcp.models import ImageResult, ProviderName, SearchParams


class ProviderError(RuntimeError):
    """A provider failure whose message is safe to show the agent and to log.

    httpx errors embed the full request URL, and several providers (Pixabay,
    StockVault, SerpAPI) send their API key as a query parameter, so raw httpx
    messages must never leave the provider layer.
    """


class ImageProvider(ABC):
    name: ProviderName
    requires_api_key: bool = True

    def __init__(self, api_key: str | None, client: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.client = client

    @property
    def configured(self) -> bool:
        return not self.requires_api_key or self.api_key is not None

    @abstractmethod
    async def search(self, params: SearchParams) -> list[ImageResult]: ...

    async def safe_search(self, params: SearchParams) -> list[ImageResult]:
        """Run :meth:`search`, turning any failure into a key-free ProviderError."""
        try:
            return await self.search(params)
        except ProviderError:
            raise
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            hint = " (rate limited by the provider; try again later)" if status == 429 else ""
            raise ProviderError(
                f"{self.name} returned HTTP {status} {exc.response.reason_phrase}{hint}"
            ) from None
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} request failed ({type(exc).__name__})") from None
        except Exception as exc:
            message = str(exc)
            if self.api_key:
                message = message.replace(self.api_key, "***")
            raise ProviderError(f"{self.name} failed: {message[:200]}") from None

    @abstractmethod
    def build_attribution(self, image: ImageResult) -> str: ...
