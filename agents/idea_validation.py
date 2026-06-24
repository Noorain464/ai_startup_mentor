"""Agent 1 — Idea Validation.

Scores problem clarity / target / pain and decides whether the pipeline should
proceed or bounce back to the user with clarifying questions (conditional #1).
"""

from __future__ import annotations

from llm import run_structured, with_revision
from logconf import get_logger
from models import IdeaValidationOutput
from prompts import IDEA_VALIDATION_PROMPT
from state import GraphState

log = get_logger("agent.1.idea")


def idea_validation_node(state: GraphState) -> dict:
    log.info("▶ Agent 1 (Idea Validation) — input: %r", state["user_input"][:80])
    clarification = state.get("clarification_context", "")
    clar_block = (
        f"Founder's follow-up answers:\n{clarification}" if clarification else ""
    )

    prompt = IDEA_VALIDATION_PROMPT.format(
        user_input=state["user_input"],
        clarification_context=clar_block,
    )
    prompt = with_revision(prompt, state)

    result: IdeaValidationOutput = run_structured(IdeaValidationOutput, prompt)

    log.info(
        "✓ Agent 1 done — clarity=%d pain=%d proceed=%s target=%r",
        result.problem_clarity, result.pain_severity, result.proceed, result.target_customer,
    )

    return {
        "idea_validation": result,
        "idea_summary": result.idea_summary,
        "target_customer": result.target_customer,
        "needs_clarification": not result.proceed,
    }
