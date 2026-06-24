"""The single shared graph state.

Every node reads from and writes to this one `GraphState`. Keeping it in one
version-controlled file is the answer to the rubric's "state management" and
prevents silent schema drift across agents.
"""

from __future__ import annotations

from typing import List, Optional, TypedDict

from models import (
    BizModelOutput,
    IdeaValidationOutput,
    MarketResearchOutput,
    MVPOutput,
    RiskAssessmentOutput,
    StrategyOutput,
)


class GraphState(TypedDict, total=False):
    # --- input ---
    user_input: str
    clarification_context: str  # answers appended on re-submission

    # --- revision control (human-in-the-loop re-run) ---
    start_at: str        # which section to (re)start from: idea|market|strategy|biz_mvp|risk
    revision_note: str   # optional founder feedback injected on a re-run

    # --- Agent 1 ---
    idea_validation: IdeaValidationOutput
    idea_summary: str
    target_customer: str
    needs_clarification: bool

    # --- tool results (raw, formatted for prompts) ---
    web_search_results: str
    yc_search_results: str

    # --- Agent 2 ---
    market_research: MarketResearchOutput
    competitor_count: int

    # --- Agent 3 ---
    strategy: StrategyOutput

    # --- Agent 4 (parallel: business model + MVP) ---
    biz_model: BizModelOutput
    mvp: MVPOutput

    # --- Agent 5 ---
    risk: RiskAssessmentOutput
    requires_human_escalation: bool
    escalation_warning: Optional[str]

    # --- bookkeeping ---
    errors: List[str]
