"""LangGraph orchestration — the state graph that ties the 5 agents together.

Flow:

    START
      │
      ▼
    validate_idea ──proceed=False──► clarify ──► END
      │ proceed=True
      ▼
    market_research  (tools: Tavily + YC)
      │
      ├─ competitor_count == 0 ──► strategy_category ──┐
      └─ competitor_count  > 0 ──► strategy_diff ──────┤
                                                       ▼
                                                   biz_model
                                                       │
                                                       ▼
                                                     risk
      ┌──── requires_human_escalation == True ──► escalate ──► END
      └──── otherwise ─────────────────────────────────────► END

Three conditional branches: (1) proceed gate, (2) strategy branch,
(3) regulatory escalation. The human-in-the-loop PDF approval lives in the UI
(app.py) — it gates the only irreversible external action (writing the report).
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agents import (
    biz_model_node,
    idea_validation_node,
    market_research_node,
    risk_node,
    strategy_category_node,
    strategy_differentiation_node,
)
from logconf import get_logger
from state import GraphState

log = get_logger("graph")


# --------------------------------------------------------------------------- #
# Simple nodes
# --------------------------------------------------------------------------- #


def clarify_node(state: GraphState) -> dict:
    """Terminal node when the idea is too vague. The UI surfaces the questions
    from Agent 1 and lets the founder re-submit with answers."""
    log.info("⏸ Clarification required — pipeline paused, bouncing back to user")
    return {"needs_clarification": True}


def escalate_node(state: GraphState) -> dict:
    """Guardrail node: regulated space detected. Inserts a mandatory warning
    before the human approval gate."""
    log.warning("⚠ Guardrail: regulatory escalation triggered — human review required")
    risk = state.get("risk")
    reg = risk.regulatory_risk if risk else None
    detail = reg.description if reg else "Regulated domain detected."
    return {
        "escalation_warning": (
            "⚠️ This idea touches a regulated space — additional human review "
            f"required before proceeding. {detail}"
        )
    }


# --------------------------------------------------------------------------- #
# Conditional routers
# --------------------------------------------------------------------------- #


def route_after_validation(state: GraphState) -> str:
    target = "market_research" if state["idea_validation"].proceed else "clarify"
    log.info("↳ route after validation: proceed=%s → %s", state["idea_validation"].proceed, target)
    return target


def route_after_market(state: GraphState) -> str:
    count = state.get("competitor_count", 0)
    target = "strategy_category" if count == 0 else "strategy_diff"
    log.info("↳ route after market: competitor_count=%d → %s", count, target)
    return target


def route_after_risk(state: GraphState) -> str:
    escalate = bool(state.get("requires_human_escalation"))
    target = "escalate" if escalate else END
    log.info("↳ route after risk: escalate=%s → %s", escalate, "escalate" if escalate else "END")
    return target


# --------------------------------------------------------------------------- #
# Graph builder
# --------------------------------------------------------------------------- #


def build_graph():
    g = StateGraph(GraphState)

    g.add_node("validate_idea", idea_validation_node)
    g.add_node("clarify", clarify_node)
    g.add_node("market_research", market_research_node)
    g.add_node("strategy_category", strategy_category_node)
    g.add_node("strategy_diff", strategy_differentiation_node)
    g.add_node("biz_model", biz_model_node)
    g.add_node("risk", risk_node)
    g.add_node("escalate", escalate_node)

    g.add_edge(START, "validate_idea")

    # Conditional #1 — proceed gate
    g.add_conditional_edges(
        "validate_idea",
        route_after_validation,
        {"market_research": "market_research", "clarify": "clarify"},
    )
    g.add_edge("clarify", END)

    # Conditional #2 — strategy branch
    g.add_conditional_edges(
        "market_research",
        route_after_market,
        {"strategy_category": "strategy_category", "strategy_diff": "strategy_diff"},
    )

    g.add_edge("strategy_category", "biz_model")
    g.add_edge("strategy_diff", "biz_model")
    g.add_edge("biz_model", "risk")

    # Conditional #3 — regulatory escalation
    g.add_conditional_edges(
        "risk",
        route_after_risk,
        {"escalate": "escalate", END: END},
    )
    g.add_edge("escalate", END)

    return g.compile()


# Module-level compiled graph for reuse.
APP = build_graph()


def run_validation(user_input: str, clarification_context: str = "") -> GraphState:
    """Run the full pipeline once and return the final state."""
    log.info("═══ Running validation for: %r ═══", user_input[:90])
    initial: GraphState = {
        "user_input": user_input,
        "clarification_context": clarification_context,
        "errors": [],
    }
    final = APP.invoke(initial)
    log.info("═══ Pipeline finished ═══")
    return final


if __name__ == "__main__":
    import json
    import sys

    idea = " ".join(sys.argv[1:]) or "An app that reminds people to water their plants."
    final = run_validation(idea)
    print(json.dumps({k: str(v)[:200] for k, v in final.items()}, indent=2))
