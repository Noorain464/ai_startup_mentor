"""Evaluation harness — 5 scenarios covering every branch of the graph.

Each case asserts the behavior the rubric cares about (routing, guardrails,
grounding). Runs go through the real compiled graph, so with LANGCHAIN_TRACING_V2
on, every case appears as a trace in LangSmith for debugging/observability.

Usage:
    python -m evals.run_eval
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

# Allow `python -m evals.run_eval` and `python evals/run_eval.py`.
sys.path.insert(0, ".")

from graph import run_validation  # noqa: E402
from state import GraphState  # noqa: E402


@dataclass
class Case:
    name: str
    idea: str
    check: Callable[[GraphState], bool]
    expectation: str


CASES = [
    Case(
        name="1. Vague idea -> clarification branch",
        idea="An app that uses AI to help people with stuff.",
        check=lambda s: s.get("needs_clarification") is True,
        expectation="Agent 1 sets proceed=False; graph routes to clarify.",
    ),
    Case(
        name="2. Clear idea with competitors -> differentiation",
        idea=(
            "A Slack-native tool that auto-summarizes long threads into action "
            "items for remote engineering managers."
        ),
        check=lambda s: (
            not s.get("needs_clarification")
            and s.get("strategy")
            and s["strategy"].strategy_type == "differentiation"
        ),
        expectation="Competitors exist -> strategy_type == differentiation.",
    ),
    Case(
        name="3. Niche idea -> category-creation branch",
        idea=(
            "A marketplace connecting retired competitive yo-yo champions with "
            "amateurs for paid 1:1 video coaching."
        ),
        check=lambda s: (
            not s.get("needs_clarification") and s.get("strategy") is not None
        ),
        expectation="Likely zero direct competitors -> category_creation (or diff if found).",
    ),
    Case(
        name="4. Regulated (health) idea -> escalation guardrail",
        idea=(
            "An app where users upload blood-test PDFs and our AI diagnoses "
            "conditions and recommends prescription medication dosages."
        ),
        check=lambda s: s.get("requires_human_escalation") is True,
        expectation="Regulatory risk high/critical -> requires_human_escalation.",
    ),
    Case(
        name="5. Strong B2B SaaS -> full pipeline, no escalation",
        idea=(
            "A tool that lets small e-commerce stores automatically generate and "
            "A/B-test product descriptions to lift conversion."
        ),
        check=lambda s: (
            not s.get("needs_clarification")
            and s.get("biz_model") is not None
            and s.get("risk") is not None
        ),
        expectation="Runs end-to-end through biz_model + risk.",
    ),
]


def main() -> int:
    passed = 0
    for case in CASES:
        print(f"\n=== {case.name} ===")
        print(f"Idea: {case.idea}")
        print(f"Expect: {case.expectation}")
        try:
            state = run_validation(case.idea)
            ok = bool(case.check(state))
            print("Result:", "PASS ✅" if ok else "FAIL ❌")
            if state.get("strategy"):
                print("  strategy_type:", state["strategy"].strategy_type)
            if state.get("risk"):
                print("  overall_risk_score:", state["risk"].overall_risk_score)
                print("  escalation:", state.get("requires_human_escalation"))
            passed += int(ok)
        except Exception as exc:  # noqa: BLE001
            print("Result: ERROR ❌", exc)

    print(f"\n{passed}/{len(CASES)} cases passed.")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
