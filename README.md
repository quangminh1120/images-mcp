# stock-image-mcp

<!-- mcp-name: io.github.Hasilt/images-mcp -->

An MCP server that lets Claude Code (or any MCP-compatible agent) search and
download stock images by tool call — useful for sourcing images while writing
SEO blog posts or other content.

## Providers

| Provider        | API type              | Requires key | Default rate limit                                |
| --------------- | --------------------- | ------------ | ------------------------------------------------- |
| Unsplash        | Official              | Yes          | 50/hr demo, 5000/hr production                    |
| Pexels          | Official              | Yes          | 200/hr                                            |
| Pixabay         | Official              | Yes          | 100 req/60s                                       |
| Freepik         | Official              | Yes          | configurable (plan-dependent)                     |
| StockVault      | Official              | Yes          | configurable (undocumented, conservative default) |
| Burst (Shopify) | **Unofficial scrape** | No           | self-imposed, polite default                      |
| Google Images   | SerpAPI (**paid**)    | Yes          | 20/hr (configurable)                              |

Burst has no public API. It's included as a best-effort HTML scraper, clearly
marked unsupported in code — any failure there is caught and reported as an
empty result rather than breaking `search_all_images`.

### Google Images (opt-in)

Google searches the whole web through [SerpAPI](https://serpapi.com/manage-api-key)'s
`google_images` engine — useful for real products, brands, people or news that
stock sites don't have. Two things make it different from the stock providers:

- **It costs money.** SerpAPI gives 100 free searches a month, then roughly
  $0.01 each. So `search_all_images` leaves Google out unless the call passes
  `include_google=true` (or you set `GOOGLE_IN_SEARCH_ALL=true`). Query it
  directly with `search_stock_images(query, provider="google")`.
- **Results may be copyrighted.** Every Google result has
  `copyright_unverified: true` and a licence of "Unknown"; check the source
  page before publishing. Set `GOOGLE_LICENSE_FILTER=cl` to ask Google for
  Creative Commons images only (`f`, `fc`, `fm`, `fmc`, `ol` are the other
  SerpAPI licence filters).

## Downloads are sandboxed

`download_image` only writes inside `DOWNLOAD_DIR`: `dest_path` must be a
relative path ending in `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` or `.avif`;
absolute paths and `..` are refused. It fetches only public http(s) URLs
(every redirect is re-checked), requires a real raster image by both
Content-Type and file signature, and stops at 20 MB.

## Install

Each user runs the server locally and supplies their own provider API keys —
there's no shared hosting or centrally-held keys.

With [Claude Code](https://docs.claude.com/en/docs/claude-code):

```bash
claude mcp add stock-image-mcp \
  -e UNSPLASH_ACCESS_KEY=... \
  -e UNSPLASH_TIER=demo \
  -e PEXELS_API_KEY=... \
  -e PIXABAY_API_KEY=... \
  -e FREEPIK_API_KEY=... \
  -e FREEPIK_REQUESTS_PER_MINUTE=60 \
  -e STOCKVAULT_API_KEY=... \
  -e STOCKVAULT_REQUESTS_PER_HOUR=60 \
  -e BURST_REQUESTS_PER_MINUTE=10 \
  -e DEFAULT_PROVIDER=pexels \
  -e DOWNLOAD_DIR=./downloads \
  -- uvx stock-image-mcp
```

With [OpenAI Codex CLI](https://github.com/openai/codex):

```bash
codex mcp add stock-image-mcp \
  --env UNSPLASH_ACCESS_KEY=... \
  --env UNSPLASH_TIER=demo \
  --env PEXELS_API_KEY=... \
  --env PIXABAY_API_KEY=... \
  --env FREEPIK_API_KEY=... \
  --env FREEPIK_REQUESTS_PER_MINUTE=60 \
  --env STOCKVAULT_API_KEY=... \
  --env STOCKVAULT_REQUESTS_PER_HOUR=60 \
  --env BURST_REQUESTS_PER_MINUTE=10 \
  --env DEFAULT_PROVIDER=pexels \
  --env DOWNLOAD_DIR=./downloads \
  -- uvx stock-image-mcp
```

With [Gemini CLI](https://github.com/google-gemini/gemini-cli):

```bash
gemini mcp add stock-image-mcp \
  -e UNSPLASH_ACCESS_KEY=... \
  -e UNSPLASH_TIER=demo \
  -e PEXELS_API_KEY=... \
  -e PIXABAY_API_KEY=... \
  -e FREEPIK_API_KEY=... \
  -e FREEPIK_REQUESTS_PER_MINUTE=60 \
  -e STOCKVAULT_API_KEY=... \
  -e STOCKVAULT_REQUESTS_PER_HOUR=60 \
  -e BURST_REQUESTS_PER_MINUTE=10 \
  -e DEFAULT_PROVIDER=pexels \
  -e DOWNLOAD_DIR=./downloads \
  -- uvx stock-image-mcp
```

Or add it to your MCP config manually with [`uvx`](https://docs.astral.sh/uv/guides/tools/)
(no clone or install step required — `uvx` fetches the package from PyPI on
first run):

```json
{
  "mcpServers": {
    "stock-image-mcp": {
      "command": "uvx",
      "args": ["stock-image-mcp"],
      "env": {
        "UNSPLASH_ACCESS_KEY": "...",
        "UNSPLASH_TIER": "demo",
        "PEXELS_API_KEY": "...",
        "PIXABAY_API_KEY": "...",
        "FREEPIK_API_KEY": "...",
        "FREEPIK_REQUESTS_PER_MINUTE": "60",
        "STOCKVAULT_API_KEY": "...",
        "STOCKVAULT_REQUESTS_PER_HOUR": "60",
        "BURST_REQUESTS_PER_MINUTE": "10",
        "DEFAULT_PROVIDER": "pexels",
        "DOWNLOAD_DIR": "./downloads"
      }
    }
  }
}
```

Only `UNSPLASH_ACCESS_KEY`, `PEXELS_API_KEY`, `PIXABAY_API_KEY`,
`FREEPIK_API_KEY`, `STOCKVAULT_API_KEY` and `SERPAPI_KEY` (Google, see above) are actual secrets — set only the
ones for providers you want enabled and drop the rest; any provider key you
omit is simply skipped by `search_all_images` and rejected if queried
directly via `search_stock_images`. The remaining variables are optional
tuning knobs shown above with their defaults — see `.env.example` for the
full list.

## Tools

- `search_stock_images(query, provider="default", orientation=None, per_page=10, page=1)`
- `search_all_images(query, orientation=None, per_page=5, include_google=None)` — fans out to every configured provider concurrently (Google only when `include_google=true`)
- `get_best_image(query, provider="default")`
- `download_image(url, dest_path, provider=None)` — saves inside `DOWNLOAD_DIR` (relative image path only), returns attribution text if the image came from a prior search
- `get_attribution(provider, image_id)`
- `get_rate_limit_status(provider=None)`

## Usage

You don't call these tools directly — you just talk to your agent, and it
decides when to reach for one based on what you asked and the tool
descriptions above. A few things worth knowing:

- Just ask in plain English. "Find me 3 landscape photos of mountains for a
  blog post" is enough to trigger `search_all_images` (or
  `search_stock_images` if you name a provider). "Download that first
  Unsplash result to `./images/hero.jpg`" triggers `download_image`. "How
  many Pexels requests do I have left this hour?" triggers
  `get_rate_limit_status`.
- `search_stock_images` needs a specific provider (or `"default"`);
  `search_all_images` just queries everything you've configured keys for and
  merges the results. Say "search Pexels only" or similar if you care which
  one gets used.
- Several providers (Unsplash and Pexels in particular) require attribution
  if you actually use the image somewhere public. `download_image` returns
  the attribution text alongside the file when it applies — it's on you to
  paste it wherever the image ends up, the server won't do that part for you.
- Want to call tools by hand instead of through a conversation? See the MCP
  Inspector section under Development below.

## Developing locally

Working from a clone instead of the published package:

```bash
uv sync
cp .env.example .env   # fill in the API keys for providers you want enabled
uv run stock-image-mcp
```

Point your Claude config at the local checkout instead of `uvx`:

```json
{
  "mcpServers": {
    "stock-image-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/stock-image-mcp",
        "run",
        "stock-image-mcp"
      ],
      "env": {
        "UNSPLASH_ACCESS_KEY": "...",
        "UNSPLASH_TIER": "demo",
        "PEXELS_API_KEY": "...",
        "PIXABAY_API_KEY": "...",
        "FREEPIK_API_KEY": "...",
        "FREEPIK_REQUESTS_PER_MINUTE": "60",
        "STOCKVAULT_API_KEY": "...",
        "STOCKVAULT_REQUESTS_PER_HOUR": "60",
        "BURST_REQUESTS_PER_MINUTE": "10",
        "DEFAULT_PROVIDER": "pexels",
        "DOWNLOAD_DIR": "./downloads"
      }
    }
  }
}
```

## Development

```bash
uv run pytest              # test suite (mocked HTTP, no live keys needed)
uv run ruff check .         # lint
uv run ruff format .        # format
uv run mypy src             # type check
```

To try it against real providers, use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector):

```bash
npx @modelcontextprotocol/inspector uv run stock-image-mcp
```
