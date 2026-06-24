"""Agent 4a — Business Model.

Chooses revenue model + pricing. Runs in PARALLEL with the MVP agent (both
fan out from Strategy and fan in to Risk).
"""

from __future__ import annotations

from llm import run_structured, with_revision
from logconf import get_logger
from models import BizModelOutput
from prompts import BUSINESS_MODEL_PROMPT
from state import GraphState

log = get_logger("agent.4a.biz")


def business_model_node(state: GraphState) -> dict:
    log.info("▶ Agent 4a (Business Model) [parallel]")
    strategy = state.get("strategy")
    market = state.get("market_research")

    prompt = BUSINESS_MODEL_PROMPT.format(
        idea_summary=state.get("idea_summary", ""),
        target_customer=state.get("target_customer", ""),
        strategy=strategy.model_dump_json(indent=2) if strategy else "{}",
        market_research=market.model_dump_json(indent=2) if market else "{}",
    )
    prompt = with_revision(prompt, state)

    result: BizModelOutput = run_structured(BizModelOutput, prompt)
    log.info("✓ Agent 4a done — revenue=%s pricing=%r", result.revenue_model, result.pricing_strategy)
    return {"biz_model": result}
