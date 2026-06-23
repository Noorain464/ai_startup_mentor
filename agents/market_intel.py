"""Agent 2 — Market & Competitor Intelligence.

Calls both tools (Tavily web search + YC directory) to ground the analysis in
real results, then extracts market size, signals, segments, and competitors.
"""

from __future__ import annotations

from llm import run_structured
from logconf import get_logger
from models import MarketResearchOutput
from prompts import MARKET_RESEARCH_PROMPT
from state import GraphState
from tools import format_results, web_search, yc_search

log = get_logger("agent.2.market")


def market_research_node(state: GraphState) -> dict:
    idea_summary = state.get("idea_summary", state["user_input"])
    target = state.get("target_customer", "")
    log.info("▶ Agent 2 (Market & Competitor Intel) — researching: %r", idea_summary[:80])

    # --- Tool calls (grounding) ---
    web_query = f"{idea_summary} market competitors {target}"
    web_payload = web_search(web_query, max_results=6)
    yc_payload = yc_search(idea_summary, max_results=6)

    web_str = format_results(web_payload)
    yc_str = format_results(yc_payload)

    prompt = MARKET_RESEARCH_PROMPT.format(
        idea_summary=idea_summary,
        target_customer=target,
        web_search_results=web_str,
        yc_search_results=yc_str,
    )

    result: MarketResearchOutput = run_structured(MarketResearchOutput, prompt)

    log.info(
        "✓ Agent 2 done — %d direct competitors, market=%s",
        result.competitor_count, result.market_size_estimate,
    )

    return {
        "market_research": result,
        "competitor_count": result.competitor_count,
        "web_search_results": web_str,
        "yc_search_results": yc_str,
    }
