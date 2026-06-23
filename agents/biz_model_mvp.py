"""Agent 4 — Business Model + MVP.

Chooses a revenue model and pricing, and defines a ruthless two-phase MVP scope.
"""

from __future__ import annotations

from llm import run_structured
from logconf import get_logger
from models import BizModelOutput
from prompts import BIZ_MODEL_MVP_PROMPT
from state import GraphState

log = get_logger("agent.4.bizmodel")


def biz_model_node(state: GraphState) -> dict:
    log.info("▶ Agent 4 (Business Model + MVP)")
    strategy = state.get("strategy")
    market = state.get("market_research")

    prompt = BIZ_MODEL_MVP_PROMPT.format(
        idea_summary=state.get("idea_summary", ""),
        target_customer=state.get("target_customer", ""),
        strategy=strategy.model_dump_json(indent=2) if strategy else "{}",
        market_research=market.model_dump_json(indent=2) if market else "{}",
    )

    result: BizModelOutput = run_structured(BizModelOutput, prompt)
    log.info("✓ Agent 4 done — revenue=%s pricing=%r", result.revenue_model, result.pricing_strategy)
    return {"biz_model": result}
