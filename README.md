# AI Startup Mentor — A Multi-Agent System

> An AI "startup mentor" that takes a raw startup idea and runs it through a pipeline of
> specialized agents — validating the problem, researching the market, defining strategy,
> designing a business model + MVP, and stress-testing risk — before producing a structured
> validation report with a human-in-the-loop approval gate.

**Status:** Capstone project proposal (for instructor validation)
**Type:** Multi-agent LLM system with tool use, structured outputs, conditional routing, and a human approval gate.

---

## 1. Problem

Most early-stage founders fall in love with a *solution* before they have validated the
*problem*. They skip rigorous market research, ignore competitors, hand-wave the business
model, and discover regulatory or technical landmines only after wasting months and money.

There is no cheap, fast, and *rigorous* way to pressure-test an idea end-to-end. Generic
chatbots are too agreeable — they encourage rather than scrutinize.

## 2. Solution

A **multi-agent validation pipeline** that behaves like a panel of skeptical experts. The
user submits a raw idea; five specialized agents each do one job well, passing structured
state down the chain. The system:

- Refuses to proceed on vague ideas and asks sharp clarifying questions instead.
- Grounds market and competitor claims in **real search results** (no hallucinated startups).
- Adapts its strategy based on whether competitors exist (differentiation vs. category creation).
- Flags regulated spaces (health, fintech, children, EU data) and **escalates to a human**.
- Produces a downloadable PDF report only after the user explicitly approves.

## 3. Target Users

- **Primary:** First-time / student founders and indie hackers validating an idea pre-build.
- **Secondary:** Accelerator/incubator programs, university entrepreneurship courses, and
  hackathon teams that need a fast, structured first-pass critique.

---

## 4. The Agents

The system is a directed graph of five agents sharing a single typed state object.

| # | Agent | Responsibility | Key Output |
|---|-------|----------------|------------|
| 1 | **Idea Validation** | Scores problem clarity, target customer, pain severity. Decides whether to proceed or ask clarifying questions. | `proceed: bool`, `clarifying_questions[]` |
| 2 | **Market & Competitor Intelligence** | Uses search tools to estimate market size, find growth signals, and list real competitors with sources. | `competitors[]`, `competitor_count` |
| 3 | **Strategy** | Branches on competitor count: **differentiation** (competitors exist) or **category creation** (zero competitors). | `usp`, `positioning`, `strategy_type` |
| 4 | **Business Model + MVP** | Chooses a revenue model, pricing, and a ruthless phased MVP feature scope. | `revenue_model`, `phase_1_features[]` |
| 5 | **Risk Assessment** | Devil's advocate. Scores market/technical/business/**regulatory** risk and triggers human escalation if needed. | `overall_risk_score`, `requires_human_escalation` |

### Flow

```
          ┌─────────────────────────────────────────────────────────┐
          │                    GraphState (shared)                   │
          └─────────────────────────────────────────────────────────┘
 user idea
     │
     ▼
[1] Idea Validation ──proceed=False──► [Clarify node] ──► (wait for user) ──┐
     │ proceed=True                                                          │
     ▼                                          ◄──────── re-submit ─────────┘
[2] Market & Competitor Intel  (Tool: Tavily web search + YC directory search)
     │
     ▼
[3] Strategy  ──competitor_count == 0──► Category-Creation prompt
     │         ──competitor_count > 0──► Differentiation prompt
     ▼
[4] Business Model + MVP
     │
     ▼
[5] Risk Assessment ──regulatory_risk in {high, critical}──► [Escalation warning]
     │
     ▼
[Human-in-the-loop gate]  "Approve & Generate Report"
     │ approved
     ▼
[PDF Report]  (irreversible external action)
```

---

## 5. Tech Stack & Rationale

| Layer | Choice | Why |
|-------|--------|-----|
| **Orchestration** | **LangGraph (Python)** | Explicit `StateGraph` with nodes, edges, and conditional edges. Every team member can point at and own a specific node — easy to explain in a viva. More transparent than CrewAI/AutoGen. |
| **LLM** | **GPT-4o** (or **Claude Sonnet**) | Native JSON / structured-output support, tool calling, affordable per-call cost. Either is swappable behind one `run_agent()` function. |
| **Tools / APIs** | **Tavily Search** (free tier, ~1k searches/mo) + **YC Company Directory** (scoped web search) | Satisfies the "≥2 tools" requirement. YC search is a deliberate **free** substitute for Crunchbase, which has **no free API tier** (~$49–79/mo). |
| **Structured outputs** | **Pydantic v2** | Every agent hand-off is a validated model — robustness + a clean "structured outputs" rubric criterion. |
| **Observability** | **LangSmith** | `LANGCHAIN_TRACING_V2=true` auto-traces every run: graph trace, per-node tokens & latency. Zero extra code. |
| **UI** | **Streamlit** | Single `app.py`: text input, "Run" button, expandable per-agent output, and the approval button. Fast path to a demo. |
| **PDF output** | **fpdf2** (or ReportLab) | The "irreversible external action" gated by human approval. fpdf2 is simpler for a capstone. |

> **Note on Crunchbase:** Prior research confirmed Crunchbase's API has **no free tier**, so the
> design intentionally uses a scoped `site:ycombinator.com/companies` search as the second,
> free, authoritative tool. This is a deliberate, defensible design decision.

---

## 6. Key Design Decisions & Edge Cases

These are the system's "interesting" behaviors — the parts worth demoing and defending.

1. **Vague-idea branch** — Agent 1 returns `proceed=False`, routing to a clarify node that
   surfaces questions and waits for re-submission. (Conditional routing #1)
2. **Zero competitors** — Agent 3 switches to category-creation logic and reasons about whether
   it's a genuine new category, no demand, or a missed search. (Conditional routing #2)
3. **Regulatory guardrail** — Agent 5 sets `requires_human_escalation=true` for regulated
   spaces, inserting a mandatory warning before the approval gate.
4. **No hallucinated competitors** — Agents 2 & 5 may only cite startups present in search
   results, with a `source_url`. Listed openly as a known limitation.
5. **Schema robustness** — Malformed LLM JSON triggers one corrective retry, then a logged
   fallback. All agents read/write a single version-controlled `GraphState` TypedDict.
6. **Rate limits & cost** — Exponential-backoff retry (`tenacity`) around every tool call;
   dev-time response caching to avoid burning the free tier during repeated eval runs.
7. **Streamlit reruns** — Intermediate agent outputs stored in `st.session_state` so clicking
   "Approve" never re-triggers the full 5-agent pipeline.

---

## 7. Rubric Mapping

| Rubric criterion | Where it's satisfied |
|------------------|----------------------|
| Multi-agent system | 5 specialized agents in a LangGraph graph |
| Correct graph flow / routing | 2+ conditional branches (clarify loop, strategy branch, escalation) |
| State management | Single `GraphState` TypedDict shared across all agents |
| ≥2 tool integrations | Tavily web search + YC directory search |
| Structured outputs | Pydantic v2 models for every agent hand-off |
| Human-in-the-loop | Functional "Approve & Generate Report" gate before PDF |
| Guardrails | Regulatory-risk escalation node |
| Observability / debugging | LangSmith tracing on all runs + 5 eval scenarios |
| Demo-ready output | Streamlit UI + downloadable PDF report |

---

## 8. Project Structure (planned)

```
AI_Startup_Mentor/
├── README.md
├── requirements.txt
├── .env                  # OPENAI_API_KEY, TAVILY_API_KEY, LANGCHAIN_* 
├── app.py                # Streamlit UI + human-in-the-loop gate
├── graph.py              # LangGraph StateGraph wiring (orchestration)
├── state.py              # GraphState TypedDict — single source of truth
├── prompts.py            # All agent prompts (system + per agent)
├── agents/
│   ├── idea_validation.py
│   ├── market_intel.py
│   ├── strategy.py
│   ├── biz_model_mvp.py
│   └── risk.py
├── tools/
│   ├── tavily_search.py
│   └── yc_search.py
├── models.py             # Pydantic v2 output schemas
├── report.py             # fpdf2 PDF generation
└── evals/
    └── run_eval.py       # 5 test scenarios → LangSmith traces
```

---

## 9. Setup (planned)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # langgraph, langchain-openai, pydantic, tavily-python,
                                        # streamlit, fpdf2, tenacity, langsmith
cp .env.example .env                    # add OPENAI_API_KEY, TAVILY_API_KEY, LANGCHAIN_API_KEY
streamlit run app.py
```

---


