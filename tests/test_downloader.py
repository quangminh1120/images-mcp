from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx

from stock_image_mcp import downloader
from stock_image_mcp.downloader import DownloadError, download_image, resolve_dest

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

_PUBLIC = {"example.com": "93.184.215.14", "cdn.example.com": "93.184.215.15"}
_PRIVATE = {
    "internal.example.com": "10.0.0.5",
    "localhost": "127.0.0.1",
    "169.254.169.254": "169.254.169.254",
    "metadata.example.com": "169.254.169.254",
    "v6local.example.com": "::1",
}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve(host: str, port: int) -> list[str]:
        table = {**_PUBLIC, **_PRIVATE}
        if host not in table:
            raise OSError("unknown host")
        return [table[host]]

    monkeypatch.setattr(downloader, "_resolve_host", resolve)


def _img(content: bytes = JPEG, ctype: str = "image/jpeg", **headers: str) -> httpx.Response:
    return httpx.Response(200, content=content, headers={"content-type": ctype, **headers})


# --- resolve_dest -----------------------------------------------------------


def test_resolve_dest_accepts_nested_relative_path(tmp_path: Path) -> None:
    assert resolve_dest(tmp_path, "blog/hero.JPG") == (tmp_path / "blog" / "hero.JPG").resolve()


@pytest.mark.parametrize(
    "dest",
    [
        str(Path.home() / "evil.jpg"),  # absolute on this OS
        "/etc/evil.jpg",
        "C:/Users/x/AppData/evil.jpg",
        "C:evil.jpg",  # drive-relative (Windows)
        "\\\\server\\share\\evil.jpg",  # UNC
        "../evil.jpg",
        "blog/../../evil.jpg",
    ],
)
def test_resolve_dest_rejects_paths_outside_download_dir(tmp_path: Path, dest: str) -> None:
    with pytest.raises(DownloadError):
        resolve_dest(tmp_path / "downloads", dest)


@pytest.mark.parametrize("dest", ["", "   ", "update.bat", "x.ps1", "x.exe", "x.svg", "x.jpg.lnk"])
def test_resolve_dest_rejects_non_image_names(tmp_path: Path, dest: str) -> None:
    with pytest.raises(DownloadError):
        resolve_dest(tmp_path, dest)


def test_resolve_dest_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "downloads"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        os.symlink(outside, root / "link", target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks is not permitted on this machine")
    with pytest.raises(DownloadError):
        resolve_dest(root, "link/evil.jpg")


# --- download_image ---------------------------------------------------------


@respx.mock
async def test_download_image_saves_bytes(tmp_path: Path) -> None:
    respx.get("https://example.com/photo.jpg").mock(return_value=_img())
    dest = tmp_path / "nested" / "photo.jpg"

    async with httpx.AsyncClient() as client:
        saved_path = await download_image(client, "https://example.com/photo.jpg", dest)

    assert saved_path == dest
    assert dest.read_bytes() == JPEG
    assert not dest.with_name("photo.jpg.part").exists()


@respx.mock
async def test_download_image_raises_on_http_error(tmp_path: Path) -> None:
    respx.get("https://example.com/missing.jpg").mock(return_value=httpx.Response(404))
    dest = tmp_path / "missing.jpg"

    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await download_image(client, "https://example.com/missing.jpg", dest)

    assert not dest.exists()


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/Windows/win.ini",
        "ftp://example.com/x.jpg",
        "https://internal.example.com/x.jpg",
        "http://localhost:8080/x.jpg",
        "http://169.254.169.254/latest/meta-data",
        "http://metadata.example.com/x.jpg",
        "http://v6local.example.com/x.jpg",
        "http://no-such-host.example/x.jpg",
    ],
)
async def test_download_image_refuses_unsafe_urls(tmp_path: Path, url: str) -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(DownloadError):
            await download_image(client, url, tmp_path / "x.jpg")
    assert list(tmp_path.iterdir()) == []


@respx.mock
async def test_download_image_follows_public_redirect(tmp_path: Path) -> None:
    respx.get("https://example.com/a.jpg").mock(
        return_value=httpx.Response(302, headers={"location": "https://cdn.example.com/a.jpg"})
    )
    respx.get("https://cdn.example.com/a.jpg").mock(return_value=_img(PNG, "image/png"))

    async with httpx.AsyncClient(follow_redirects=True) as client:
        await download_image(client, "https://example.com/a.jpg", tmp_path / "a.png")

    assert (tmp_path / "a.png").read_bytes() == PNG


@respx.mock
async def test_download_image_refuses_redirect_to_private_host(tmp_path: Path) -> None:
    respx.get("https://example.com/a.jpg").mock(
        return_value=httpx.Response(302, headers={"location": "http://localhost/secret"})
    )
    internal = respx.get("http://localhost/secret").mock(return_value=_img())

    async with httpx.AsyncClient(follow_redirects=True) as client:
        with pytest.raises(DownloadError):
            await download_image(client, "https://example.com/a.jpg", tmp_path / "a.jpg")

    assert not internal.called
    assert list(tmp_path.iterdir()) == []


@respx.mock
async def test_download_image_refuses_redirect_loop(tmp_path: Path) -> None:
    respx.get("https://example.com/loop.jpg").mock(
        return_value=httpx.Response(302, headers={"location": "/loop.jpg"})
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(DownloadError, match="too many redirects"):
            await download_image(client, "https://example.com/loop.jpg", tmp_path / "x.jpg")


@pytest.mark.parametrize(
    ("content", "ctype"),
    [
        (b"@echo off\r\ncalc.exe\r\n", "application/octet-stream"),
        (b"<html>login</html>", "text/html"),
        (b"<svg onload='x()'/>", "image/svg+xml"),
        (b"@echo off\r\ncalc.exe\r\n" + b" " * 32, "image/jpeg"),  # lies about its type
    ],
)
async def test_download_image_refuses_non_images(
    tmp_path: Path, content: bytes, ctype: str
) -> None:
    with respx.mock:
        respx.get("https://example.com/x.jpg").mock(return_value=_img(content, ctype))
        async with httpx.AsyncClient() as client:
            with pytest.raises(DownloadError):
                await download_image(client, "https://example.com/x.jpg", tmp_path / "x.jpg")
    assert list(tmp_path.iterdir()) == []


@respx.mock
async def test_download_image_refuses_declared_oversize(tmp_path: Path) -> None:
    respx.get("https://example.com/big.jpg").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "image/jpeg", "content-length": str(10**9)},
            content=JPEG,
        )
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(DownloadError, match="limit"):
            await download_image(client, "https://example.com/big.jpg", tmp_path / "big.jpg")
    assert list(tmp_path.iterdir()) == []


@respx.mock
async def test_download_image_aborts_streamed_oversize(tmp_path: Path) -> None:
    async def body() -> AsyncIterator[bytes]:
        yield JPEG
        for _ in range(10):
            yield b"\x00" * 1024

    respx.get("https://example.com/big.jpg").mock(
        return_value=httpx.Response(200, headers={"content-type": "image/jpeg"}, content=body())
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(DownloadError, match="limit"):
            await download_image(
                client, "https://example.com/big.jpg", tmp_path / "big.jpg", max_bytes=4096
            )
    assert list(tmp_path.iterdir()) == []
