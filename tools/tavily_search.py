"""Tool 1 — Tavily web search via a plain HTTP call.

No retry/cache machinery — just a simple POST. If the key is missing it returns
an empty result set so the graph can keep running during a demo.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import requests

from logconf import get_logger

log = get_logger("tool.web")

TAVILY_URL = "https://api.tavily.com/search"


def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    log.info("🔍 web_search query=%r (max_results=%d)", query, max_results)

    key = os.getenv("TAVILY_API_KEY")
    if not key:
        log.warning("   TAVILY_API_KEY not set — skipping search")
        return {"results": [], "note": "TAVILY_API_KEY not set"}

    resp = requests.post(
        TAVILY_URL,
        json={
            "api_key": key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    log.info("   ↳ %d results returned", len(data.get("results", [])))
    return data


def format_results(payload: Dict[str, Any]) -> str:
    """Flatten a search payload into a compact string for an LLM prompt."""
    results: List[Dict[str, Any]] = payload.get("results", []) or []
    if not results:
        return f"(no results — {payload.get('note', 'empty')})"

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "untitled")
        url = r.get("url", "")
        content = (r.get("content", "") or "")[:500]
        lines.append(f"[{i}] {title}\n    URL: {url}\n    {content}")
    return "\n".join(lines)
