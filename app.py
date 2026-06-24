"""Streamlit UI — demo-ready front end with the human-in-the-loop gates.

Two human gates:
1. Clarification — if Agent 1 says the idea is too vague, the pipeline stops and
   the founder must answer clarifying questions and re-submit.
2. Approval — the multi-agent analysis runs, but the irreversible action
   (generating the PDF report) only fires when the human clicks "Approve".
   Otherwise the human picks ONE section to revise and the pipeline re-runs from
   that section onward (Business Model and MVP are separately selectable).

`st.session_state` holds the result so re-runs of the script don't re-trigger
the (expensive) multi-agent pipeline.
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

_RISK_BADGE = {"low": "🟢 low", "medium": "🟡 medium", "high": "🟠 high", "critical": "🔴 critical"}


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
# Small formatting helpers
# --------------------------------------------------------------------------- #

def _bullets(items) -> str:
    """Render a list as a proper markdown bullet block (single st.markdown call)."""
    return "\n".join(f"- {x}" for x in items) if items else "_none_"


def _field(label: str, value: str):
    st.markdown(f"**{label}:** {value}")


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
# Renderers
# --------------------------------------------------------------------------- #

def render_validation(state):
    iv = state.get("idea_validation")
    if not iv:
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Problem clarity", f"{iv.problem_clarity}/5")
    c2.metric("Pain severity", f"{iv.pain_severity}/5")
    c3.metric("Proceed?", "✅ Yes" if iv.proceed else "⛔ No")
    _field("Idea", state.get("idea_summary", ""))
    _field("Target customer", iv.target_customer)
    st.markdown("**Demand signals:**")
    st.markdown(_bullets(iv.demand_signals))


def render_market(state):
    mr = state.get("market_research")
    if not mr:
        return
    c1, c2 = st.columns([1, 3])
    c1.metric("Direct competitors", mr.competitor_count)
    c2.markdown(f"**Market size:** {mr.market_size_estimate}")
    c2.caption(mr.market_size_rationale)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Growth signals**")
        st.markdown(_bullets(mr.growth_signals))
    with col_b:
        st.markdown("**Customer segments**")
        st.markdown(_bullets(mr.customer_segments))

    st.markdown("**Competitors found**")
    if mr.competitors:
        for c in mr.competitors:
            st.markdown(
                f"- **{c.name}** · `{c.type}` · `{c.funding_stage}` — {c.one_line_description}  \n"
                f"  ↳ [source]({c.source_url})"
            )
    else:
        st.markdown("_none found in search results_")
    if mr.market_notes:
        st.info(mr.market_notes)


def render_strategy(state):
    s = state.get("strategy")
    if not s:
        return
    st.markdown(f"**Strategy type:** `{s.strategy_type}`")
    _field("Key message", s.key_message)
    _field("Positioning", s.positioning)
    st.divider()
    if s.strategy_type == "differentiation":
        _field("Differentiation axis", f"`{s.differentiation_axis}`")
        _field("USP", s.usp or "—")
        _field("Anti-positioning", s.anti_positioning or "—")
        _field("Beachhead", s.beachhead_segment or "—")
        if s.competitor_gaps:
            st.markdown("**Competitor gaps**")
            st.markdown("\n".join(f"- **{g.competitor}**: {g.gap}" for g in s.competitor_gaps))
    else:
        _field("Scenario", f"{s.scenario} — {s.scenario_rationale}")
        if s.category_name:
            _field("Category", s.category_name)
        if s.wedge_use_case:
            _field("Wedge use case", s.wedge_use_case)
        if s.reframe_search_keywords:
            _field("Re-search keywords", ", ".join(s.reframe_search_keywords))


def render_biz(state):
    bm = state.get("biz_model")
    mvp = state.get("mvp")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("##### 4a · Business Model")
        if bm:
            _field("Revenue model", f"`{bm.revenue_model}`")
            st.caption(bm.revenue_model_rationale)
            _field("Pricing", bm.pricing_strategy)
            st.caption(bm.pricing_rationale)
        else:
            st.markdown("_not yet generated_")
    with col_b:
        st.markdown("##### 4b · MVP Scope")
        if mvp:
            st.markdown("**Phase 1** — pre-revenue (weeks 1–8)")
            st.markdown(_bullets(mvp.phase_1_features))
            st.markdown("**Phase 2** — first revenue (weeks 9–20)")
            st.markdown(_bullets(mvp.phase_2_features))
            st.markdown("**Tech requirements**")
            st.markdown(_bullets(mvp.tech_requirements))
        else:
            st.markdown("_not yet generated_")


def render_risk(state):
    rk = state.get("risk")
    if not rk:
        return
    esc = "⚠️ escalation required" if rk.requires_human_escalation else "no escalation"
    c1, c2 = st.columns([1, 3])
    c1.metric("Overall risk", f"{rk.overall_risk_score}/10")
    c2.markdown(f"**Status:** {esc}")

    for label, dim in [
        ("Market", rk.market_risk),
        ("Technical", rk.technical_risk),
        ("Business", rk.business_risk),
        ("Regulatory", rk.regulatory_risk),
    ]:
        badge = _RISK_BADGE.get(dim.risk_level, dim.risk_level)
        st.markdown(f"**{label} — {badge}**")
        st.markdown(dim.description)
        st.caption(f"Mitigation: {dim.mitigation}")
    st.divider()
    st.markdown("**Top 3 mitigation actions**")
    st.markdown(_bullets(rk.top_3_mitigation_actions))


# --------------------------------------------------------------------------- #
# Output + human gates
# --------------------------------------------------------------------------- #

if result:
    # --- Gate 1: clarification loop ---------------------------------------- #
    if result.get("needs_clarification"):
        iv = result.get("idea_validation")
        st.warning("⏸ This idea needs clarification before we can validate it.")
        if iv:
            render_validation(result)
            st.markdown("**Please answer these before re-submitting:**")
            st.markdown("\n".join(f"- {q}" for q in iv.clarifying_questions))
        st.session_state.clarify_answers = st.text_area(
            "Your answers", value=st.session_state.clarify_answers, height=120
        )
        if st.button("Re-submit with answers", type="primary"):
            _run(result["user_input"], st.session_state.clarify_answers)
            st.rerun()

    # --- Full pipeline output ---------------------------------------------- #
    else:
        if result.get("escalation_warning"):
            st.error(result["escalation_warning"])

        with st.expander("1 · Idea Validation", expanded=True):
            render_validation(result)
        with st.expander("2 · Market & Competitor Intelligence", expanded=True):
            render_market(result)
        with st.expander("3 · Strategy", expanded=True):
            render_strategy(result)
        with st.expander("4 · Business Model & MVP (parallel agents)", expanded=True):
            render_biz(result)
        with st.expander("5 · Risk Assessment", expanded=True):
            render_risk(result)

        # --- Gate 2: human approval before the irreversible PDF action ----- #
        st.divider()
        st.subheader("✋ Human approval")
        st.caption(
            "Generating the PDF is the system's irreversible action. Approve to "
            "download it, or request changes to re-run the pipeline from one section."
        )

        approve_col, changes_col = st.columns(2)

        with approve_col:
            st.markdown("**Approve**")
            if st.button("✅ Approve & Generate Report", type="primary", use_container_width=True):
                path = generate_pdf(result)
                with open(path, "rb") as fh:
                    st.download_button(
                        "⬇️ Download validation report (PDF)",
                        data=fh.read(),
                        file_name=path.split("/")[-1],
                        mime="application/pdf",
                        use_container_width=True,
                    )
                st.success(f"Report generated: {path}")

        with changes_col:
            st.markdown("**Request changes**")
            with st.form("request_changes"):
                section = st.radio(
                    "Which section is unsatisfactory? (pick one)",
                    options=SECTIONS,
                    format_func=lambda s: SECTION_LABELS[s],
                )
                note = st.text_input("What should change? (optional)")
                if st.form_submit_button("🔁 Re-run from this section", use_container_width=True):
                    _rerun_from(section, note)
                    st.rerun()
