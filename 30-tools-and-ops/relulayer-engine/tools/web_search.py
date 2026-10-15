"""
Path K: real-time web grounding for strategic drafts.

Uses Tavily or Serper when ``TAVILY_API_KEY`` / ``SERPER_API_KEY`` is set.
Controlled by ``RELULAYER_WEB_GROUNDING`` (default on; set 0/false/off to disable).
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "as", "by",
    "with", "from", "into", "through", "during", "before", "after", "above", "below",
    "between", "under", "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must",
    "shall", "can", "this", "that", "these", "those", "i", "you", "he", "she", "it", "we",
    "they", "what", "which", "who", "whom", "whose", "where", "when", "why", "how", "all",
    "each", "every", "both", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just", "also", "now",
    "here", "there", "then", "once", "if", "about", "against", "between", "into", "through",
    "while", "although", "because", "until", "unless", "create", "high", "level", "using",
    "use", "used", "based", "focus", "focused", "including", "include", "need", "want",
    "make", "made", "new", "one", "two", "first", "last", "next", "our", "your", "their",
})


def _grounding_env_enabled() -> bool:
    return os.environ.get("RELULAYER_WEB_GROUNDING", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _max_snippets() -> int:
    try:
        n = int(os.environ.get("RELULAYER_GROUNDING_MAX_SNIPPETS", "5"))
    except ValueError:
        n = 5
    return max(3, min(10, n))


def _search_provider() -> str:
    return os.environ.get("RELULAYER_SEARCH_PROVIDER", "auto").strip().lower()


def extract_search_query(user_prompt: str, max_terms: int = 10) -> str:
    """
    Lightweight keyword line for search APIs: drop stopwords, keep order, cap length.
    """
    text = (user_prompt or "").strip()
    if not text:
        return ""
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9+\-]*", text.lower())
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if len(t) < 3 or t in _STOPWORDS:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_terms:
            break
    q = " ".join(out)
    if len(q) < 8:
        q = re.sub(r"\s+", " ", text)[:200].strip()
    if len(q) > 280:
        q = q[:280].rsplit(" ", 1)[0].strip()
    return q


@dataclass
class LiveGroundingOutcome:
    """Result of a live web grounding attempt (mapped to API telemetry in main)."""

    active: bool
    provider: str
    search_query_used: str
    snippets: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None
    context_block: str = ""

    @property
    def snippet_count(self) -> int:
        return len(self.snippets)


def _http_json_post(url: str, payload: dict, headers: dict[str, str], timeout: float) -> dict | None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as e:
        logger.warning("web_search.http_failed url=%s err=%s", url, e)
        return None


def _tavily_search(query: str, api_key: str, max_results: int, timeout: float) -> LiveGroundingOutcome:
    url = "https://api.tavily.com/search"
    payload: dict[str, object] = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False,
    }
    data = _http_json_post(url, payload, {}, timeout)
    if not data:
        return LiveGroundingOutcome(
            active=False,
            provider="tavily",
            search_query_used=query,
            error="Tavily request failed or invalid JSON.",
        )
    results = data.get("results") or []
    snippets: list[dict[str, str]] = []
    for r in results[:max_results]:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or "").strip()
        link = str(r.get("url") or r.get("link") or "").strip()
        body = str(r.get("content") or r.get("snippet") or "").strip()
        if not body and not title:
            continue
        snippets.append({"title": title, "url": link, "snippet": body[:1200]})
    return _outcome_from_snippets("tavily", query, snippets)


def _serper_news_search(query: str, api_key: str, max_results: int, timeout: float) -> LiveGroundingOutcome:
    url = "https://google.serper.dev/news"
    payload = {"q": query, "num": max_results}
    headers = {"X-API-KEY": api_key}
    data = _http_json_post(url, payload, headers, timeout)
    if not data:
        return LiveGroundingOutcome(
            active=False,
            provider="serper",
            search_query_used=query,
            error="Serper news request failed or invalid JSON.",
        )
    news = data.get("news") or []
    snippets: list[dict[str, str]] = []
    for r in news[:max_results]:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or "").strip()
        link = str(r.get("link") or "").strip()
        body = str(r.get("snippet") or "").strip()
        if not body and not title:
            continue
        snippets.append({"title": title, "url": link, "snippet": body[:1200]})
    if snippets:
        return _outcome_from_snippets("serper", query, snippets)
    return _serper_web_search(query, api_key, max_results, timeout)


def _serper_web_search(query: str, api_key: str, max_results: int, timeout: float) -> LiveGroundingOutcome:
    url = "https://google.serper.dev/search"
    payload = {"q": query, "num": max_results}
    headers = {"X-API-KEY": api_key}
    data = _http_json_post(url, payload, headers, timeout)
    if not data:
        return LiveGroundingOutcome(
            active=False,
            provider="serper",
            search_query_used=query,
            error="Serper search request failed or invalid JSON.",
        )
    organic = data.get("organic") or []
    snippets: list[dict[str, str]] = []
    for r in organic[:max_results]:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or "").strip()
        link = str(r.get("link") or "").strip()
        body = str(r.get("snippet") or "").strip()
        if not body and not title:
            continue
        snippets.append({"title": title, "url": link, "snippet": body[:1200]})
    return _outcome_from_snippets("serper", query, snippets)


def _outcome_from_snippets(
    provider: str,
    query: str,
    snippets: list[dict[str, str]],
) -> LiveGroundingOutcome:
    if not snippets:
        return LiveGroundingOutcome(
            active=False,
            provider=provider,
            search_query_used=query,
            error="No results returned.",
        )
    lines: list[str] = [
        "### Live web grounding (news / market)",
        "",
        f"Search query used: `{query}`",
        "",
    ]
    for i, s in enumerate(snippets, start=1):
        title = s.get("title") or "(untitled)"
        link = s.get("url") or ""
        snip = s.get("snippet") or ""
        lines.append(f"**{i}. {title}**")
        if link:
            lines.append(f"- Source: {link}")
        lines.append(f"- Snippet: {snip}")
        lines.append("")
    ctx = "\n".join(lines).strip()
    return LiveGroundingOutcome(
        active=True,
        provider=provider,
        search_query_used=query,
        snippets=snippets,
        context_block=ctx,
    )


def fetch_live_grounding(
    user_prompt: str,
    *,
    max_snippets: int | None = None,
    timeout: float = 28.0,
) -> LiveGroundingOutcome:
    """
    If enabled and an API key is present, run a search and return markdown for context + snippets.
    """
    if not _grounding_env_enabled():
        return LiveGroundingOutcome(
            active=False,
            provider="disabled",
            search_query_used="",
            error=None,
        )

    tavily_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    serper_key = (os.environ.get("SERPER_API_KEY") or "").strip()
    if not tavily_key and not serper_key:
        return LiveGroundingOutcome(
            active=False,
            provider="none",
            search_query_used="",
            error="No TAVILY_API_KEY or SERPER_API_KEY set.",
        )

    n = max_snippets if max_snippets is not None else _max_snippets()
    query = extract_search_query(user_prompt)
    if not query:
        return LiveGroundingOutcome(
            active=False,
            provider="none",
            search_query_used="",
            error="Could not derive a search query from the strategic directive.",
        )

    prov = _search_provider()
    if prov == "tavily" and tavily_key:
        return _tavily_search(query, tavily_key, n, timeout)
    if prov == "serper" and serper_key:
        news_first = os.environ.get("RELULAYER_SERPER_USE_NEWS", "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        if news_first:
            return _serper_news_search(query, serper_key, n, timeout)
        return _serper_web_search(query, serper_key, n, timeout)

    if prov == "auto":
        if tavily_key:
            return _tavily_search(query, tavily_key, n, timeout)
        if serper_key:
            if os.environ.get("RELULAYER_SERPER_USE_NEWS", "1").strip().lower() not in (
                "0",
                "false",
                "no",
            ):
                return _serper_news_search(query, serper_key, n, timeout)
            return _serper_web_search(query, serper_key, n, timeout)

    return LiveGroundingOutcome(
        active=False,
        provider=prov or "none",
        search_query_used=query,
        error="RELULAYER_SEARCH_PROVIDER does not match available API keys.",
    )
