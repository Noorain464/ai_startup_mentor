"""Tool 2 — YC Company Directory search.

A distinct tool: it scopes the same search to the Y Combinator company
directory to surface startup competitors. This is the deliberate FREE substitute
for Crunchbase (whose API has no free tier).
"""

from __future__ import annotations

from typing import Any, Dict

from logconf import get_logger
from tools.tavily_search import format_results, web_search

log = get_logger("tool.yc")

_YC_SITE = "ycombinator.com/companies"


def yc_search(idea_keywords: str, max_results: int = 5) -> Dict[str, Any]:
    log.info("🏢 yc_search keywords=%r", idea_keywords)
    query = f"site:{_YC_SITE} {idea_keywords}"
    payload = web_search(query, max_results=max_results)
    payload["scope"] = _YC_SITE
    return payload


__all__ = ["yc_search", "format_results"]
