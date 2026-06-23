"""Agent 3 — Strategy.

Two distinct nodes, one per branch of conditional #2:
- `strategy_category_node`        — when competitor_count == 0 (category creation)
- `strategy_differentiation_node` — when competitors exist (differentiation)
The graph routes to exactly one of these based on `competitor_count`.
"""

from __future__ import annotations

from llm import run_structured
from logconf import get_logger
from models import StrategyOutput
from prompts import (
    STRATEGY_PROMPT_CATEGORY_CREATION,
    STRATEGY_PROMPT_DIFFERENTIATION,
)
from state import GraphState

log = get_logger("agent.3.strategy")


def _market_json(state: GraphState) -> str:
    mr = state.get("market_research")
    return mr.model_dump_json(indent=2) if mr else "{}"


def strategy_category_node(state: GraphState) -> dict:
    log.info("▶ Agent 3 (Strategy / CATEGORY-CREATION branch) — 0 competitors")
    prompt = STRATEGY_PROMPT_CATEGORY_CREATION.format(
        idea_summary=state.get("idea_summary", ""),
        target_customer=state.get("target_customer", ""),
        market_research=_market_json(state),
    )
    result: StrategyOutput = run_structured(StrategyOutput, prompt, temperature=0.4)
    log.info("✓ Agent 3 done — type=%s key_message=%r", result.strategy_type, result.key_message)
    return {"strategy": result}


def strategy_differentiation_node(state: GraphState) -> dict:
    log.info(
        "▶ Agent 3 (Strategy / DIFFERENTIATION branch) — %d competitors",
        state.get("competitor_count", 0),
    )
    mr = state.get("market_research")
    competitors = mr.competitors if mr else []
    competitors_list = "\n".join(
        f"- {c.name} ({c.type}, {c.funding_stage}): {c.one_line_description}"
        for c in competitors
    ) or "(none listed)"

    prompt = STRATEGY_PROMPT_DIFFERENTIATION.format(
        competitor_count=state.get("competitor_count", 0),
        idea_summary=state.get("idea_summary", ""),
        target_customer=state.get("target_customer", ""),
        competitors_list=competitors_list,
        market_research=_market_json(state),
    )
    result: StrategyOutput = run_structured(StrategyOutput, prompt, temperature=0.4)
    log.info("✓ Agent 3 done — type=%s axis=%s usp=%r", result.strategy_type,
             result.differentiation_axis, result.usp)
    return {"strategy": result}
