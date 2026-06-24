"""Streamlit UI — demo-ready front end with the human-in-the-loop gates.

Two human gates:
1. Clarification — if Agent 1 says the idea is too vague, the pipeline stops and
   the founder must answer clarifying questions and re-submit.
2. Approval — the multi-agent analysis runs, but the irreversible action
   (generating the PDF report) only fires when the human clicks "Approve".

`st.session_state` holds the result so re-runs of the script don't re-trigger
the (expensive) 5-agent pipeline.
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from graph import SECTION_LABELS, SECTIONS, run_validation
from report import generate_pdf

load_dotenv()

st.set_page_config(page_title="Startup Idea Validator", page_icon="🚀", layout="wide")

st.title("🚀 Startup Idea Validator")
st.caption("A multi-agent AI mentor that pressure-tests your startup idea end-to-end.")


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #

if "result" not in st.session_state:
    st.session_state.result = None
if "clarify_answers" not in st.session_state:
    st.session_state.clarify_answers = ""


def _run(idea: str, clarification: str = ""):
    with st.spinner("Running the multi-agent validation pipeline…"):
        st.session_state.result = run_validation(idea, clarification)


def _rerun_from(section: str, note: str):
    """Re-run the pipeline from a chosen section, reusing earlier results."""
    prior = st.session_state.result
    label = SECTION_LABELS.get(section, section)
    with st.spinner(f"Re-running from {label}…"):
        st.session_state.result = run_validation(
            prior["user_input"],
            prior.get("clarification_context", ""),
            start_at=section,
            revision_note=note,
            prior_state=prior,
        )


# --------------------------------------------------------------------------- #
# Input
# --------------------------------------------------------------------------- #

with st.form("idea_form"):
    idea = st.text_area(
        "Describe your startup idea",
        placeholder="e.g. A tool that helps freelance designers auto-generate contracts and invoices.",
        height=120,
    )
    submitted = st.form_submit_button("Validate idea", type="primary")

if submitted and idea.strip():
    st.session_state.clarify_answers = ""
    _run(idea.strip())

result = st.session_state.result


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def render_validation(state):
    iv = state.get("idea_validation")
    if not iv:
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Problem clarity", f"{iv.problem_clarity}/5")
    c2.metric("Pain severity", f"{iv.pain_severity}/5")
    c3.metric("Proceed?", "Yes" if iv.proceed else "No")
    st.write(f"**Idea:** {state.get('idea_summary', '')}")
    st.write(f"**Target customer:** {iv.target_customer}")
    if iv.demand_signals:
        st.write("**Demand signals:** " + ", ".join(iv.demand_signals))


def render_market(state):
    mr = state.get("market_research")
    if not mr:
        return
    st.write(f"**Market size:** {mr.market_size_estimate} — {mr.market_size_rationale}")
    if mr.growth_signals:
        st.write("**Growth signals:** " + ", ".join(mr.growth_signals))
    if mr.customer_segments:
        st.write("**Segments:** " + ", ".join(mr.customer_segments))
    st.write(f"**Direct competitors found:** {mr.competitor_count}")
    for c in mr.competitors:
        st.markdown(
            f"- **{c.name}** ({c.type}, {c.funding_stage}) — {c.one_line_description}  \n"
            f"  [{c.source_url}]({c.source_url})"
        )
    if mr.market_notes:
        st.info(mr.market_notes)


def render_strategy(state):
    s = state.get("strategy")
    if not s:
        return
    st.write(f"**Strategy type:** `{s.strategy_type}`")
    st.write(f"**Key message:** {s.key_message}")
    st.write(f"**Positioning:** {s.positioning}")
    if s.strategy_type == "differentiation":
        st.write(f"**Differentiation axis:** {s.differentiation_axis}")
        st.write(f"**USP:** {s.usp}")
        st.write(f"**Anti-positioning:** {s.anti_positioning}")
        st.write(f"**Beachhead:** {s.beachhead_segment}")
        for g in s.competitor_gaps:
            st.write(f"- Gap in **{g.competitor}**: {g.gap}")
    else:
        st.write(f"**Scenario:** {s.scenario} — {s.scenario_rationale}")
        if s.category_name:
            st.write(f"**Category:** {s.category_name}")
        if s.wedge_use_case:
            st.write(f"**Wedge:** {s.wedge_use_case}")
        if s.reframe_search_keywords:
            st.write("**Re-search keywords:** " + ", ".join(s.reframe_search_keywords))


def render_biz(state):
    bm = state.get("biz_model")
    mvp = state.get("mvp")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Business Model** *(parallel agent 4a)*")
        if bm:
            st.write(f"**Revenue model:** {bm.revenue_model} — {bm.revenue_model_rationale}")
            st.write(f"**Pricing:** {bm.pricing_strategy} — {bm.pricing_rationale}")
    with col_b:
        st.markdown("**MVP Scope** *(parallel agent 4b)*")
        if mvp:
            st.write("**Phase 1 (pre-revenue):**")
            for f in mvp.phase_1_features:
                st.write(f"  - {f}")
            st.write("**Phase 2 (first revenue):**")
            for f in mvp.phase_2_features:
                st.write(f"  - {f}")
            st.write("**Tech requirements:** " + ", ".join(mvp.tech_requirements))


def render_risk(state):
    rk = state.get("risk")
    if not rk:
        return
    st.metric("Overall risk score", f"{rk.overall_risk_score}/10")
    for label, dim in [
        ("Market", rk.market_risk),
        ("Technical", rk.technical_risk),
        ("Business", rk.business_risk),
        ("Regulatory", rk.regulatory_risk),
    ]:
        st.write(f"**{label} — `{dim.risk_level}`**: {dim.description}")
        st.caption(f"Mitigation: {dim.mitigation}")
    if rk.top_3_mitigation_actions:
        st.write("**Top 3 actions:**")
        for a in rk.top_3_mitigation_actions:
            st.write(f"  - {a}")


if result:
    # --- Gate 1: clarification loop ---
    if result.get("needs_clarification"):
        iv = result.get("idea_validation")
        st.warning("This idea needs clarification before we can validate it.")
        if iv:
            render_validation(result)
            st.write("**Please answer these before re-submitting:**")
            for q in iv.clarifying_questions:
                st.write(f"- {q}")
        st.session_state.clarify_answers = st.text_area(
            "Your answers", value=st.session_state.clarify_answers, height=120
        )
        if st.button("Re-submit with answers", type="primary"):
            _run(result["user_input"], st.session_state.clarify_answers)
            st.rerun()

    else:
        # --- Full pipeline output ---
        if result.get("escalation_warning"):
            st.error(result["escalation_warning"])

        with st.expander("1 · Idea Validation", expanded=True):
            render_validation(result)
        with st.expander("2 · Market & Competitor Intelligence", expanded=True):
            render_market(result)
        with st.expander("3 · Strategy", expanded=True):
            render_strategy(result)
        with st.expander("4 · Business Model & MVP", expanded=True):
            render_biz(result)
        with st.expander("5 · Risk Assessment", expanded=True):
            render_risk(result)

        # --- Gate 2: human approval before the irreversible PDF action ---
        st.divider()
        st.subheader("Human approval")
        st.caption(
            "Generating the PDF is the system's irreversible action. Approve to "
            "download it, or request changes to re-run the pipeline from a section."
        )

        approve_col, changes_col = st.columns(2)

        # --- Approve → generate + download the PDF ---
        with approve_col:
            if st.button("✅ Approve & Generate Report", type="primary"):
                path = generate_pdf(result)
                with open(path, "rb") as fh:
                    st.download_button(
                        "⬇️ Download validation report (PDF)",
                        data=fh.read(),
                        file_name=path.split("/")[-1],
                        mime="application/pdf",
                    )
                st.success(f"Report generated: {path}")

        # --- Request changes → pick ONE section, re-run from there ---
        with changes_col:
            with st.form("request_changes"):
                st.write("**Not satisfied?** Choose the section to revise:")
                section = st.radio(
                    "Section to re-run from",
                    options=SECTIONS,
                    format_func=lambda s: SECTION_LABELS[s],
                    label_visibility="collapsed",
                )
                note = st.text_input("What should change? (optional)")
                if st.form_submit_button("🔁 Re-run from this section"):
                    _rerun_from(section, note)
                    st.rerun()
