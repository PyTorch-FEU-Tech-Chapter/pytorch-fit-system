from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit, urlunsplit

import lxml.html

from .models import JobListing, JobListingAction, JobListingRule

_SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:")
_DANGEROUS = re.compile(
    r"(?:^|[/_-])(logout|log-out|signout|delete|remove|destroy|unsubscribe|checkout|cart)(?:$|[/_?&=-])",
    re.IGNORECASE,
)


def _parse(html: str):
    try:
        return lxml.html.fromstring(html)
    except Exception:
        return None


def _canonicalize(url: str) -> str:
    parts = urlsplit(url)
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def safe_same_domain_url(seed_url: str, raw_url: str) -> str | None:
    if not raw_url or raw_url.lower().startswith(_SKIP_SCHEMES):
        return None
    absolute = _canonicalize(urljoin(seed_url, raw_url))
    seed = urlsplit(seed_url)
    target = urlsplit(absolute)
    if target.scheme not in {"http", "https"} or target.netloc.lower() != seed.netloc.lower():
        return None
    if _DANGEROUS.search(target.path) or _DANGEROUS.search(target.query):
        return None
    return absolute


def _matches(el, selector: str) -> bool:
    selector = selector.strip()
    if not selector or not isinstance(el.tag, str):
        return False
    tag = str(el.tag).lower()
    id_match = re.fullmatch(r"([\w-]+)?#([\w-]+)", selector)
    if id_match:
        return (not id_match.group(1) or tag == id_match.group(1).lower()) and (
            el.get("id") == id_match.group(2)
        )
    class_match = re.fullmatch(r"([\w-]+)?\.([\w-]+)", selector)
    if class_match:
        return (not class_match.group(1) or tag == class_match.group(1).lower()) and (
            class_match.group(2) in (el.get("class") or "").split()
        )
    attr_match = re.fullmatch(r"([\w-]+)?\[([\w:-]+)=['\"]?([^'\"]+)['\"]?\]", selector)
    if attr_match:
        return (not attr_match.group(1) or tag == attr_match.group(1).lower()) and (
            el.get(attr_match.group(2)) == attr_match.group(3)
        )
    return tag == selector.lower()


def _select(root, selector: str):
    selectors = [part.strip() for part in selector.split(",") if part.strip()]
    matches = []
    for el in root.iter():
        if any(_matches(el, part) for part in selectors):
            matches.append(el)
    return matches


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _node_text(el) -> str:
    return _clean_text(" ".join(part.strip() for part in el.itertext() if part.strip()))


def _extract_value(card, spec: str | None, page_url: str, seed_url: str) -> str | None:
    if not spec:
        return None
    selector, _, attr = spec.partition("@")
    selector = selector.strip() or "*"
    attr = attr.strip()
    candidates = [card] if selector == "*" else _select(card, selector)
    if not candidates:
        return None
    target = candidates[0]
    if attr:
        value = target.get(attr)
        if attr in {"href", "src"} and value:
            return safe_same_domain_url(seed_url, urljoin(page_url, value)) or urljoin(
                page_url, value
            )
        return _clean_text(value or "") or None
    return _node_text(target) or None


def apply_listing_rules(
    html: str,
    page_url: str,
    seed_url: str,
    rules: list[JobListingRule],
) -> tuple[list[JobListing], list[str], list[str], list[str]]:
    """Execute AI-authored listing rules deterministically."""

    root = _parse(html)
    if root is None:
        return [], [], [], []

    for rule in [rule for rule in rules if rule.role == JobListingAction.IGNORE]:
        for el in list(_select(root, rule.selector)):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)

    listings: list[JobListing] = []
    seen_listings: set[tuple[str, str | None]] = set()
    next_urls: list[str] = []
    filters: list[str] = []
    searches: list[str] = []

    for rule in rules:
        if rule.role == JobListingAction.JOB_CARD and rule.extract is not None:
            for card in _select(root, rule.selector):
                data = {
                    name: _extract_value(card, value, page_url, seed_url)
                    for name, value in rule.extract.model_dump().items()
                }
                title = data.get("title")
                if not title:
                    continue
                detail_url = data.get("detail_url")
                key = (title.lower(), detail_url)
                if key in seen_listings:
                    continue
                seen_listings.add(key)
                listings.append(
                    JobListing(
                        title=title,
                        detail_url=detail_url,
                        company=data.get("company"),
                        location=data.get("location"),
                        remote_signal=data.get("remote_signal"),
                        salary_signal=data.get("salary_signal"),
                        employment_type=data.get("employment_type"),
                        experience_level=data.get("experience_level"),
                        description=data.get("description"),
                        source_url=page_url,
                        source_selector=rule.selector,
                    )
                )
        elif rule.role == JobListingAction.NEXT_PAGE:
            for el in _select(root, rule.selector):
                href = el.get("href")
                if href:
                    url = safe_same_domain_url(seed_url, href)
                    if url and url not in next_urls:
                        next_urls.append(url)
        elif rule.role == JobListingAction.FILTER_CONTROL:
            filters.extend(_node_text(el) or rule.selector for el in _select(root, rule.selector))
        elif rule.role in {JobListingAction.SEARCH_INPUT, JobListingAction.SUBMIT_SEARCH}:
            searches.extend(rule.selector for _el in _select(root, rule.selector))

    return listings, next_urls, filters, searches
