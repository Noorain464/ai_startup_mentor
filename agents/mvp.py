"""Agent 4b — MVP scope.

Defines a ruthless two-phase feature scope + tech requirements. Runs in PARALLEL
with the Business Model agent (both fan out from Strategy and fan in to Risk).
"""

from __future__ import annotations

from llm import run_structured, with_revision
from logconf import get_logger
from models import MVPOutput
from prompts import MVP_PROMPT
from state import GraphState

log = get_logger("agent.4b.mvp")


def mvp_node(state: GraphState) -> dict:
    log.info("▶ Agent 4b (MVP scope) [parallel]")
    strategy = state.get("strategy")
    market = state.get("market_research")

    prompt = MVP_PROMPT.format(
        idea_summary=state.get("idea_summary", ""),
        target_customer=state.get("target_customer", ""),
        strategy=strategy.model_dump_json(indent=2) if strategy else "{}",
        market_research=market.model_dump_json(indent=2) if market else "{}",
    )
    prompt = with_revision(prompt, state)

    result: MVPOutput = run_structured(MVPOutput, prompt)
    log.info("✓ Agent 4b done — phase1=%d phase2=%d feats", len(result.phase_1_features), len(result.phase_2_features))
    return {"mvp": result}
