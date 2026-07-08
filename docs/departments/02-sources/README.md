# Department 02 — Sources / Data Collection

> **Functional module:** pull raw evidence *into* the system — GitHub repos, local documents,
> and social-media posts.
> **One-line mandate:** get the truth in, normalize it, and never let one flaky source break the build.

📊 Diagram: [`sources.puml`](sources.puml)

---

## What this department is responsible for

Collecting everything true about a candidate and normalizing it into `models.py` shapes that
Dept 03 can reason over. There are three collectors, but **one (social) is far heavier than the
other two** and is where most of the risk lives.

| Collector | Input | Output (contract) | Difficulty |
|-----------|-------|-------------------|------------|
| `GitHubSource` | a GitHub username (via `gh` CLI) | `list[Repo]` | low |
| `DocumentSource` | a file path (PDF/DOCX/TeX/MD) | `list[RawDocument]` | low–med |
| `SocialAggregator` | a `ScrapeConfig` | `CollectResult` | **high** |

---

## Files owned

```
src/resume_builder/sources/
├── base.py            # SourceCollector ABC
├── github.py          # GitHubSource — runs `gh repo list ...`
├── document.py        # DocumentSource — PDF/DOCX/TeX/MD text extraction
└── social/            # ⚠️ the heavy subsystem
    ├── aggregator.py        # SocialAggregator: dispatch + dedupe + cache
    ├── base.py              # SocialVendor ABC + VendorUnavailableError
    ├── models.py            # SocialPost, SocialMention, ScrapeConfig
    ├── auth.py              # login prompts, challenges, session persistence
    ├── browser_login.py     # visible-browser sign-in flow
    ├── vendors/
    │   ├── facebook.py      # Playwright + mbasic fallback
    │   ├── linkedin.py
    │   ├── twitter.py       # via Nitter
    │   └── instagram.py
    └── playwright_*.py      # visible-first tooling (overlay/step/picker/debug)
config/social.example.yaml   # ScrapeConfig template
```

---

## The public contract you must NOT break

```python
# sources/base.py
class SourceCollector(ABC):
    name: str
    def collect(self, **kwargs) -> Any: ...   # concrete return types below

# concrete returns (must stay these shapes — owned by Dept 01)
GitHubSource.collect(user, include_readme=True) -> list[Repo]
DocumentSource.collect(path)                    -> list[RawDocument]

# sources/social/base.py — every vendor implements exactly this
class SocialVendor(ABC):
    name: str
    def fetch_own_posts(self, handle: str, limit: int = 50) -> list[SocialPost]: ...
    def search_mentions(self, full_name: str, limit: int = 50) -> list[SocialMention]: ...

# sources/social/aggregator.py
class SocialAggregator:
    def collect(self, config: ScrapeConfig) -> CollectResult: ...
```

---

## Critical design rules (these are non-negotiable)

### 1. Resilience: a source failure must degrade, never crash
The `SocialAggregator` wraps every vendor in a try/except boundary. A broken vendor records an
entry in `CollectResult.failures` and returns empty — it **never** re-raises into the build.
Vendors should return `[]` on failure, not throw (`VendorUnavailableError` is the only sanctioned
raise, and the aggregator catches it).

### 2. Parallel + cached
Vendors run in a `ThreadPoolExecutor(max_workers=4)`. Results are cached per-vendor on disk with
a TTL (default 6h / `21600s`), written `chmod 600`. Don't re-scrape inside the TTL window.

### 3. Dedupe is cross-vendor
Posts dedupe by `(vendor, post_id)` first, then by **content hash** — so the same announcement
cross-posted to Facebook and LinkedIn collapses to one record.

### 4. Adding a vendor = subclass + register, nothing else
The aggregator never imports concrete vendors. Add a `SocialVendor` subclass and register it in
`build_default_aggregator()`. Use **lazy imports** so a missing optional dep (e.g. Playwright)
never breaks unrelated code paths.

---

## The Facebook / visible-first gotchas (hard-won, do not relearn)

These are documented in project memory — read before touching `vendors/facebook.py`:

- **Visible-first workflow:** develop the scraper in a *visible* browser; only go headless after
  sign-off. The `playwright_*.py` tooling (overlay highlights, step-through debugger, click-to-pick
  selector) exists exactly so you can *watch it work* before trusting output.
- **FB posts are NOT `role="article"`.** Real posts are plain `div`s; only comments use
  `role=article`. Detect posts by their permalink / timestamp anchor (the `__cft__` token + post
  id). Detecting by `role=article` is the "0 posts" bug.
- **Highlight the post UNIT**, not the tiny `__cft__` anchor or the `role=article` node — that's
  the "invisible highlight" bug.

> Design specs live in `docs/superpowers/specs/2026-06-26-fb-scraper-visual-step-mode-design.md`.

---

## Dos & Don'ts

✅ Normalize to `Repo` / `RawDocument` / `SocialPost` / `SocialMention` at the boundary.
✅ Return empty + record a failure; keep the build alive.
✅ Keep secrets/sessions out of git (cache under `~/.cache/resume-builder/`).

🚫 Don't let raw vendor HTML/DOM leak past this department.
🚫 Don't add mode (`ai`/`static`) logic here — sources are mode-agnostic.
🚫 Don't block the main thread on a single slow vendor.

---

## Hands off to

**Dept 03 (Intelligence)** consumes `Repo[]` (for extraction) and `RawDocument[]` /
`CollectResult` (for synthesis). You produce the raw material; they judge relevance.
