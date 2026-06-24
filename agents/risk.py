"""Agent 5 — Risk Assessment.

Devil's-advocate pass across market/technical/business/regulatory risk. Sets
`requires_human_escalation` when regulatory risk is high/critical — the trigger
for conditional #3 and the guardrail escalation gate.
"""

from __future__ import annotations

from llm import run_structured, with_revision
from logconf import get_logger
from models import RiskAssessmentOutput
from prompts import RISK_ASSESSMENT_PROMPT
from state import GraphState

log = get_logger("agent.5.risk")


def risk_node(state: GraphState) -> dict:
    log.info("▶ Agent 5 (Risk Assessment)")
    strategy = state.get("strategy")
    market = state.get("market_research")
    biz = state.get("biz_model")
    mvp = state.get("mvp")

    prompt = RISK_ASSESSMENT_PROMPT.format(
        idea_summary=state.get("idea_summary", ""),
        target_customer=state.get("target_customer", ""),
        market_research=market.model_dump_json(indent=2) if market else "{}",
        strategy=strategy.model_dump_json(indent=2) if strategy else "{}",
        biz_model=biz.model_dump_json(indent=2) if biz else "{}",
        mvp=mvp.model_dump_json(indent=2) if mvp else "{}",
    )
    prompt = with_revision(prompt, state)

    result: RiskAssessmentOutput = run_structured(RiskAssessmentOutput, prompt, temperature=0.3)

    # Belt-and-suspenders guardrail: enforce escalation from the data even if the
    # model forgot to flip the flag.
    escalate = result.requires_human_escalation or result.regulatory_risk.risk_level in (
        "high",
        "critical",
    )

    log.info(
        "✓ Agent 5 done — score=%d/10 regulatory=%s escalate=%s",
        result.overall_risk_score, result.regulatory_risk.risk_level, escalate,
    )

    return {
        "risk": result,
        "requires_human_escalation": escalate,
    }
