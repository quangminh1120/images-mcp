"""Downloads an image to a local path for direct embedding in blog output.

Every download is treated as untrusted: the URL and destination usually come
from an LLM tool call, which may itself have been steered by text inside
search results. So this module enforces, independently of the caller:

* the destination stays inside ``download_dir`` and has an image extension;
* only http(s) URLs whose host (and every redirect hop) resolves to a public
  address are fetched;
* the response is an image by Content-Type *and* by its leading bytes;
* the body is capped at ``max_bytes``;
* nothing is left on disk unless all of the above pass.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
from pathlib import Path, PurePath
from urllib.parse import urlsplit

import httpx

MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5
ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"})
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


class DownloadError(ValueError):
    """Raised when a download is refused or fails a safety check."""


def resolve_dest(download_dir: Path, dest_path: str) -> Path:
    """Map a caller-supplied relative path to a file inside ``download_dir``.

    Absolute paths, drive-qualified paths (``C:foo``), ``..`` escapes,
    symlinks pointing outside, and non-image extensions are refused.
    """
    if not dest_path or not dest_path.strip():
        raise DownloadError("dest_path must be a non-empty relative path, e.g. 'blog/hero.jpg'")
    raw = PurePath(dest_path)
    if raw.anchor or raw.is_absolute():
        raise DownloadError(
            f"dest_path must be relative to the download directory, got {dest_path!r}"
        )
    if raw.suffix.lower() not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise DownloadError(f"dest_path must end in an image extension ({allowed})")

    root = download_dir.resolve()
    target = (root / raw).resolve()
    if not target.is_relative_to(root) or target == root:
        raise DownloadError(f"dest_path {dest_path!r} escapes the download directory")
    return target


async def _resolve_host(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


async def _check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise DownloadError(f"only http(s) URLs can be downloaded, got {parts.scheme or 'none'!r}")
    host = parts.hostname
    if not host:
        raise DownloadError("URL has no host")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        addresses = await _resolve_host(host, port)
    except OSError as exc:
        raise DownloadError(f"could not resolve host {host!r}: {exc}") from exc
    if not addresses:
        raise DownloadError(f"host {host!r} did not resolve to any address")
    for address in addresses:
        if not ipaddress.ip_address(address.split("%")[0]).is_global:
            raise DownloadError(f"host {host!r} resolves to a non-public address ({address})")


def _looks_like_image(head: bytes) -> bool:
    return (
        head.startswith(b"\xff\xd8\xff")  # JPEG
        or head.startswith(b"\x89PNG\r\n\x1a\n")  # PNG
        or head.startswith((b"GIF87a", b"GIF89a"))  # GIF
        or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")  # WebP
        or (head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis"))  # AVIF
    )


async def _open_checked(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET ``url``, following redirects by hand so every hop is vetted."""
    for _ in range(MAX_REDIRECTS + 1):
        await _check_url(url)
        request = client.build_request("GET", url)
        response = await client.send(request, stream=True, follow_redirects=False)
        if response.status_code not in _REDIRECT_CODES:
            return response
        location = response.headers.get("location")
        await response.aclose()
        if not location:
            raise DownloadError(f"redirect from {url} has no Location header")
        url = str(httpx.URL(url).join(location))
    raise DownloadError(f"too many redirects (more than {MAX_REDIRECTS})")


async def download_image(
    client: httpx.AsyncClient,
    url: str,
    dest_path: Path,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> Path:
    """Download ``url`` to ``dest_path`` (already validated by :func:`resolve_dest`)."""
    response = await _open_checked(client, url)
    tmp_path = dest_path.with_name(dest_path.name + ".part")
    try:
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if not content_type.startswith("image/") or content_type == "image/svg+xml":
            raise DownloadError(
                f"URL did not return a raster image (Content-Type: {content_type!r})"
            )

        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise DownloadError(f"image is {int(declared)} bytes, limit is {max_bytes}")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        received = 0
        head = b""
        with tmp_path.open("wb") as f:
            async for chunk in response.aiter_bytes():
                received += len(chunk)
                if received > max_bytes:
                    raise DownloadError(f"image exceeds the {max_bytes}-byte limit")
                if len(head) < 16:
                    head += chunk[: 16 - len(head)]
                f.write(chunk)

        if not _looks_like_image(head):
            raise DownloadError("downloaded file is not a JPEG/PNG/GIF/WebP/AVIF image")
        os.replace(tmp_path, dest_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        await response.aclose()
    return dest_path
