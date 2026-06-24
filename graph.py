"""LangGraph orchestration — the state graph that ties the agents together.

Flow:

    START ─(entry router: start_at)─► validate_idea
      │ proceed=False ───────────────────────► clarify ──► END     (Conditional #1)
      │ proceed=True
      ▼
    market_research  (tools: Tavily + YC)
      ├─ competitor_count == 0 ──► strategy_category ─┐            (Conditional #2)
      └─ competitor_count  > 0 ──► strategy_diff ─────┤
                                                      ▼
                              ┌──────── business_model ─┐
                  (fan-out)   │                         │  (fan-in)
                              └──────── mvp ────────────┤
                                                        ▼
                                                      risk
      ├─ requires_human_escalation ──► escalate ──► END            (Conditional #3)
      └─ else ───────────────────────────────────► END

Business Model + MVP run in PARALLEL (both fan out from Strategy, both fan in to
Risk). The entry router lets a run START at any section so the human-in-the-loop
"request changes" flow can re-run the pipeline from a chosen section onward.

The human approval gate (approve → PDF, else pick a section → re-run) lives in
the UI (app.py); generating the PDF is the only irreversible external action.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agents import (
    business_model_node,
    idea_validation_node,
    market_research_node,
    mvp_node,
    risk_node,
    strategy_category_node,
    strategy_differentiation_node,
)
from logconf import get_logger
from state import GraphState

log = get_logger("graph")

# Section keys used by the entry router and the UI's "request changes" flow.
# Business Model and MVP are SEPARATE sections so the human can revise just one.
SECTIONS = ["idea", "market", "strategy", "biz_model", "mvp", "risk"]
SECTION_LABELS = {
    "idea": "1 · Idea Validation",
    "market": "2 · Market & Competitor Intelligence",
    "strategy": "3 · Strategy",
    "biz_model": "4a · Business Model",
    "mvp": "4b · MVP Scope",
    "risk": "5 · Risk Assessment",
}


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
# Routers
# --------------------------------------------------------------------------- #


def _strategy_target(state: GraphState) -> str:
    return "strategy_category" if state.get("competitor_count", 0) == 0 else "strategy_diff"


def route_entry(state: GraphState):
    """Conditional entry: start the run at the requested section. Used by the
    'request changes' re-run; defaults to a full run from idea validation."""
    start = state.get("start_at", "idea")
    if start == "market":
        target = "market_research"
    elif start == "strategy":
        target = _strategy_target(state)
    elif start == "biz_model":
        target = "business_model"   # re-run Business Model only (MVP reused from prior state)
    elif start == "mvp":
        target = "mvp"              # re-run MVP only (Business Model reused from prior state)
    elif start == "risk":
        target = "risk"
    else:
        target = "validate_idea"
    log.info("↳ entry router: start_at=%s → %s", start, target)
    return target


def route_after_validation(state: GraphState) -> str:
    target = "market_research" if state["idea_validation"].proceed else "clarify"
    log.info("↳ route after validation: proceed=%s → %s", state["idea_validation"].proceed, target)
    return target


def route_after_market(state: GraphState) -> str:
    count = state.get("competitor_count", 0)
    target = _strategy_target(state)
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
    g.add_node("business_model", business_model_node)
    g.add_node("mvp", mvp_node)
    g.add_node("risk", risk_node)
    g.add_node("escalate", escalate_node)

    # Conditional entry — start at any section (full run defaults to validate_idea).
    g.add_conditional_edges(
        START,
        route_entry,
        {
            "validate_idea": "validate_idea",
            "market_research": "market_research",
            "strategy_category": "strategy_category",
            "strategy_diff": "strategy_diff",
            "business_model": "business_model",
            "mvp": "mvp",
            "risk": "risk",
        },
    )

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

    # Fan-out: both strategy branches kick off Business Model AND MVP in parallel.
    for strat in ("strategy_category", "strategy_diff"):
        g.add_edge(strat, "business_model")
        g.add_edge(strat, "mvp")

    # Fan-in: Risk runs once, after BOTH parallel nodes complete.
    g.add_edge("business_model", "risk")
    g.add_edge("mvp", "risk")

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


def run_validation(
    user_input: str,
    clarification_context: str = "",
    *,
    start_at: str = "idea",
    revision_note: str = "",
    prior_state: GraphState | None = None,
) -> GraphState:
    """Run the pipeline. For a fresh run, leave start_at='idea'. For a human
    'request changes' re-run, pass the previous final state as `prior_state`,
    the section to restart from as `start_at`, and optional founder feedback."""
    log.info("═══ Running validation (start_at=%s) for: %r ═══", start_at, user_input[:80])

    initial: GraphState = dict(prior_state or {})
    initial.update(
        {
            "user_input": user_input,
            "clarification_context": clarification_context,
            "start_at": start_at,
            "revision_note": revision_note,
            "errors": initial.get("errors", []),
        }
    )
    final = APP.invoke(initial)
    log.info("═══ Pipeline finished ═══")
    return final


if __name__ == "__main__":
    import json
    import sys

    idea = " ".join(sys.argv[1:]) or "An app that reminds people to water their plants."
    final = run_validation(idea)
    print(json.dumps({k: str(v)[:200] for k, v in final.items()}, indent=2))
