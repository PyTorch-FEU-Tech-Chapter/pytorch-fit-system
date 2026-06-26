# resume-build-chopper

AI-powered (or fully static) resume builder na nag-mi-mine ng iyong **GitHub repos**,
**personal documents** (PDF/DOCX/TeX), at optionally ng iyong **social posts** para
gumawa ng **role-targeted** resume. Halimbawa: kung mag-a-apply ka as a cybersecurity
engineer, ang cybersecurity-relevant na projects/skills/achievements lang ang lalabas
— hindi ang buong portfolio mo.

Each pipeline stage is an interface with **two implementations** — a deterministic
`static` one (offline, no LLM) and an `ai` one (LLM-driven). The orchestrator swaps
stages by mode without conditional plumbing, so the same domain models flow through
both paths.

---

## Features

- **Two build modes** — `static` (offline, regex/keyword scoring) and `ai` (LLM role
  spec, relevance scan, and ruthless role-aware filtering of projects/achievements).
- **Provider-agnostic LLM layer** — `anthropic`, `openai`, `claude-session`
  (interactive, no API key), or `null` (static).
- **Multiple sources** — GitHub (via the `gh` CLI), local documents, and a social
  middleman (Facebook, LinkedIn, Twitter/X, Instagram) with parallel collection,
  cross-vendor dedupe, and TTL caching.
- **Five output formats** — LaTeX, Markdown, HTML, JSON, and PDF.
- **Visual scraper debugger** — watch the social scraper work in a real Chrome window:
  non-destructive overlay highlights, a live HUD, a slow per-post step-through, and an
  interactive click-to-pick element selector. See [Visual debugger](#visual-scraper-debugger).
- **Config-only extensibility** — add roles, regex categories, and templates without
  touching code.
- **FastAPI web UI** — a prototype dashboard with OAuth identity login.

---

## Requirements

- **Python ≥ 3.11**
- **[`gh`](https://cli.github.com/) (GitHub CLI)**, authenticated (`gh auth status`) —
  used to scan repositories.
- **API key** (Anthropic or OpenAI) — only for AI mode. Skip it with the
  `claude-session` provider or use `static` mode.
- **Playwright + a browser** — only for the visible browser scraping / visual debugger
  paths. Install separately (it is not a hard dependency):
  ```bash
  pip install playwright
  playwright install chromium      # or drive your real Chrome via the channel option
  ```

---

## Install

```bash
# Core
pip install -e .

# With dev tools (pytest, ruff) and optional extras
pip install -e ".[dev]"           # tests + linting
pip install -e ".[openai]"        # OpenAI provider
pip install -e ".[social]"        # curl_cffi for the cookie/curl social fallback

# Copy the env template (only needed for AI mode / web OAuth)
cp .env.example .env
```

This installs the `resume-build` CLI entry point.

---

## Quickstart

### AI mode (with an API key)

```bash
resume-build build --mode ai \
    --gh-user yourhandle \
    --role-prompt "cybersecurity blue team / SOC analyst" \
    --docs ./my-resume.pdf \
    --formats latex,pdf,md,json \
    --output ./out/
```

### AI mode **without** an API key (interactive)

Routes every LLM call through a Claude chat: each call prints a block to copy into a
chat; paste the reply back and end with a line containing `===END===`. No token, no
network.

```bash
resume-build build --mode ai \
    --llm-provider claude-session \
    --gh-user yourhandle \
    --role-prompt "cybersecurity blue team / SOC analyst" \
    --docs ./my-resume.pdf \
    --output ./out/
```

### Static mode (offline, deterministic)

```bash
resume-build build --mode static \
    --gh-user yourhandle \
    --role cybersecurity-blueteam \
    --docs ./my-resume.tex \
    --formats latex,md,json \
    --output ./out/
```

### Web UI

```bash
uvicorn resume_builder.web.app:app --reload
```

For GitHub / Google / Microsoft OAuth setup, see
[`docs/web-auth-setup.md`](docs/web-auth-setup.md).

---

## CLI reference

| Command | What it does |
|---|---|
| `resume-build build` | Build a role-targeted resume (main command). |
| `resume-build review --docs <file>` | Findings-only review of an existing resume via the review orchestrator. |
| `resume-build list-roles` | List role ids from `config/roles.json`. |
| `resume-build list-vendors` | List registered social-media vendor handlers. |
| `resume-build login` / `logout` | Manage a stored, authenticated social session. |
| `resume-build scrape` | Run a single vendor interactively and dump posts/mentions as JSON. |
| `resume-build scrape-all --config social.yaml` | Run every enabled vendor through the aggregator. |

### `build` options

| Flag | Default | Notes |
|---|---|---|
| `--mode` | `static` | `ai` or `static`. |
| `--gh-user` | — (required) | GitHub username/org to scan. |
| `--role` | — | Role id (static mode), e.g. `cybersecurity-blueteam`. |
| `--role-prompt` | — | Free-form role description (AI mode). |
| `--docs` | — | A resume file (PDF/DOCX/TeX) or a folder. |
| `--formats` | `latex,md,json,pdf` | Comma-separated: `latex`/`tex`, `md`/`markdown`, `json`, `pdf`, `html`. |
| `--output` | `./out` | Output directory. |
| `--social` | — | Path to a `social.yaml` for the social middleman (optional). |
| `--llm-provider` | — | Override provider: `anthropic`, `openai`, `claude-session`, `null`. |
| `--verbose` / `-v` | off | INFO logging. |

Built-in role ids: `cybersecurity-blueteam`, `cybersecurity-redteam`, `fullstack-web`,
`ml-engineer`, `systems-compilers` (run `list-roles` for the live list).

---

## Visual scraper debugger

A best-effort, opt-in surface for **watching** the social scraper in a real Chrome
window before trusting headless extraction. It is non-destructive — nothing in the
page DOM is changed; highlights are drawn in a separate overlay layer.

```bash
# Watch the scrape: highlights each focused element + a live HUD.
resume-build scrape --visual

# Slower, with a fixed delay (implies --visual).
resume-build scrape --delay-ms 800

# Slow per-post step-through: walk the first few posts one at a time, painting
# POST / comments / picture / text / shared overlays. Implies --visual.
resume-build scrape --step --step-limit 3
```

### What you see

- **Overlay rectangles** positioned from each element's `getBoundingClientRect()`
  (DevTools-style), color-coded: red = the post being scraped, orange = comments
  (skipped), rose = picture being retrieved, green = the text being retrieved,
  blue = a shared post (preserved).
- **Live HUD** (top-right) — during scrolling: `Cards loaded`, `Scroll pass`,
  `Status` (so you can see *why* the scraper waits for lazy-loaded cards); during the
  step walk: `Card`, `Status`, `Next`.
- **Interactive click-to-pick** (`resume_builder.sources.social.playwright_picker`) —
  a hover-inspector + click-to-lock picker: hover the live feed (element under the
  cursor is outlined with a tag/size tooltip), click the div to scrape, and it gets
  spotlighted while everything else is dimmed (= skipped). The pick's CSS path + text
  are captured back to Python. Currently a module-level capability used from scripts,
  not yet wired to a CLI flag.

### Environment knobs

| Variable | Effect |
|---|---|
| `RESUME_BUILD_PLAYWRIGHT_VISUAL=1` | Headed browser + highlights + pauses. |
| `RESUME_BUILD_PLAYWRIGHT_DELAY_MS` | Slow-motion delay (ms) between steps (implies visual). |
| `RESUME_BUILD_PLAYWRIGHT_HIGHLIGHT_MS` | How long a highlight stays before clearing. |
| `RESUME_BUILD_PLAYWRIGHT_STEP_LIMIT` | Posts to step-walk (`0` = off). |
| `RESUME_BUILD_PLAYWRIGHT_STEP_DELAY_MS` | Pause per step (default `5000`). |
| `RESUME_BUILD_PLAYWRIGHT_CHANNEL` | `chrome` (default, real Chrome) or `chromium`. |
| `RESUME_BUILD_PLAYWRIGHT_HEADLESS` | Force headless on/off. |
| `RESUME_BUILD_PLAYWRIGHT_FORCE_HEADED` | Force a visible window in visual mode (default on). |
| `RESUME_BUILD_PLAYWRIGHT_CDP_URL` | Connect over an existing Chrome's remote-debugging port (CDP). |
| `RESUME_BUILD_PLAYWRIGHT_HIGHLIGHT_COLORS` | Comma-separated highlight palette. |

---

## Social scraping

The `SocialAggregator` is the middleman: it holds a registry of vendor handlers,
dispatches collection in parallel, dedupes across vendors (by `(vendor, id)` then by
content hash), and caches per-vendor results with a TTL. One broken vendor never fails
the whole build.

Sign in once (a visible Chrome login persists a session), then scrape:

```bash
resume-build login                       # interactive, visible-browser sign-in
resume-build scrape                       # single vendor, interactive prompts
resume-build scrape-all --config social.yaml
```

Copy [`config/social.example.yaml`](config/social.example.yaml) to `social.yaml` and
fill in `full_name`, `enabled_vendors`, and `handles`. Cookie-based fallbacks read
secrets from env vars (`FB_COOKIE`, `LI_COOKIE`, `IG_COOKIE`) — never commit them.
Session and cache files live under `~/.cache/resume-builder/social` (override with
`RESUME_BUILDER_CACHE`).

> Modern Facebook profile timelines do **not** wrap posts in `role="article"` (only
> comments are); posts are detected by their permalink/timestamp anchor instead. Keep
> this in mind when adjusting selectors.

---

## Configuration & extensibility

No code required:

- **Add a role** → edit [`config/roles.json`](config/roles.json).
- **Add a regex pattern category** → edit [`config/regex_patterns.json`](config/regex_patterns.json).
- **Add a resume template** → drop a new `.j2` file into [`config/templates/`](config/templates/)
  (`resume.html.j2`, `resume.md.j2`, `resume.tex.j2` ship by default).

Code-level extension points (subclassing / registering):

- `LLMProvider` — add a model provider (`llm/registry.py`).
- `SourceCollector` — add GitLab, Bitbucket, etc.
- `Renderer` — add an output format (`renderers/registry.py`).
- `SocialVendor` — add a social network handler.

### Settings (env, prefix `RESUME_`)

| Variable | Default | Notes |
|---|---|---|
| `RESUME_LLM_PROVIDER` | `anthropic` | Default provider for AI mode. |
| `RESUME_ANTHROPIC_MODEL` | `claude-sonnet-4-6` | |
| `RESUME_OPENAI_MODEL` | `gpt-4o-mini` | |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | — | Provider keys (no prefix). |
| `RESUME_GH_USER` | — | Default GitHub user (override with `--gh-user`). |
| `RESUME_CONFIG_DIR` | `./config` | Override the config directory. |

---

## Architecture

```
RolePicker → Sources (GitHub / Docs / Social) → Extractor → Synthesizer
           → role-aware filtering → Renderers
```

- **`pipeline.py`** is the only module that knows about `mode`; it wires concrete
  stages and runs the build. Every other module works on abstract interfaces.
- **`models.py`** holds the canonical pydantic contracts (`RoleSpec`, `Repo`,
  `Resume`, …) shared by both static and AI implementations.
- Project/achievement **role filtering** keeps only what a hiring manager for the
  target role would value (LLM verification with a strict keyword fallback), guided by
  Harvard resume principles. It returns nothing rather than padding a section.

Layout:

```
src/resume_builder/
├── cli.py                 # Typer CLI
├── pipeline.py            # orchestrator (mode-aware)
├── models.py              # shared pydantic models
├── config.py              # settings + config paths
├── role/                  # static + AI role pickers
├── sources/               # github, documents, social/
│   └── social/            # aggregator, vendors, auth, playwright_* (overlay/step/picker)
├── extractors/            # static (regex) + AI relevance
├── synthesizers/          # static + AI resume assembly
├── renderers/             # latex / md / html / json / pdf
└── web/                   # FastAPI app + templates
```

---

## Development & testing

```bash
pip install -e ".[dev]"

# Run the suite
pytest

# With coverage
pytest --cov=src --cov-report=term-missing

# Lint
ruff check src tests
```

The browser-driven `playwright_*` modules are unit-tested with mocked pages (no real
browser), so the suite runs offline.

---

## License

See repository for license details.
