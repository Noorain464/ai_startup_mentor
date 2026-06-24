# Graph Deep-Dive — Nodes, Edges & State (Presentation Reference)

This document explains the LangGraph orchestration in full detail: every node, every
edge, the shared state, the routing logic, the parallelism, and a worst-case
end-to-end walkthrough showing how the state evolves. Build slides directly from this.

- **Framework:** LangGraph `StateGraph`
- **Agents:** 6 (Idea, Market, Strategy, Business Model ∥ MVP, Risk)
- **Conditional branches:** 3 + a conditional entry point
- **Parallelism:** Business Model and MVP run concurrently (fan-out / fan-in)
- **Human-in-the-loop:** approval gate → PDF, or reject → re-run from a chosen section

---

## 1. Mental model in one paragraph

A founder's raw idea enters as a string. It flows through a **directed graph** where
each node is one specialized agent. Every node reads from and writes to **one shared
state object** (`GraphState`). Between nodes, **routers** inspect the state and decide
where to go next (proceed or clarify? competitors or not? regulated or not?). Two
nodes run **in parallel**. The graph ends; the UI then asks a human to **approve**
(produce the PDF) or **reject and re-run** from any section.

---

## 2. The shared state — `GraphState` (state.py)

This single TypedDict is the "memory" passed between all nodes. Each node returns a
**partial** dict that LangGraph merges into the state.

| Field | Type | Written by | Read by |
|-------|------|-----------|---------|
| `user_input` | `str` | entry (UI) | Idea Validation |
| `clarification_context` | `str` | UI (re-submit) | Idea Validation |
| `start_at` | `str` | UI / entry | `route_entry` |
| `revision_note` | `str` | UI (re-run) | all agents (`with_revision`) |
| `idea_validation` | `IdeaValidationOutput` | Idea Validation | (report/UI) |
| `idea_summary` | `str` | Idea Validation | Market, Strategy, Biz, MVP, Risk |
| `target_customer` | `str` | Idea Validation | Market, Strategy, Biz, MVP, Risk |
| `needs_clarification` | `bool` | Idea Validation / clarify | UI |
| `web_search_results` | `str` | Market | (report) |
| `yc_search_results` | `str` | Market | (report) |
| `market_research` | `MarketResearchOutput` | Market | Strategy, Biz, MVP, Risk |
| `competitor_count` | `int` | Market | `route_after_market` |
| `strategy` | `StrategyOutput` | Strategy (one branch) | Biz, MVP, Risk |
| `biz_model` | `BizModelOutput` | Business Model (4a) | Risk |
| `mvp` | `MVPOutput` | MVP (4b) | Risk |
| `risk` | `RiskAssessmentOutput` | Risk | `route_after_risk`, escalate |
| `requires_human_escalation` | `bool` | Risk | `route_after_risk` |
| `escalation_warning` | `str?` | escalate | UI |
| `errors` | `list[str]` | (bookkeeping) | — |

> **Slide tip:** show this as "the baton in a relay race" — each agent grabs what it
> needs, adds its result, and passes it on. No agent talks to another directly; they
> only communicate through this state.

---

## 3. Node-by-node detail

For each node: its role, the file, what it **reads** from state, what it **writes**,
the LLM schema it is forced into, and the edges leaving it.

### Node A — `validate_idea`  (Agent 1: Idea Validation)
- **File:** `agents/idea_validation.py`
- **Reads:** `user_input`, `clarification_context`, `revision_note`
- **LLM:** schema `IdeaValidationOutput`, temp `0.2`
- **Writes:** `idea_validation`, `idea_summary`, `target_customer`, `needs_clarification`
- **Job:** score problem clarity / pain / target; decide `proceed`. If the idea is too
  vague (`proceed=False`), produce `clarifying_questions`.
- **Edges out:** conditional → `market_research` (proceed) or `clarify` (vague).

### Node B — `clarify`  (control node, no LLM)
- **File:** `graph.py::clarify_node`
- **Reads:** — · **Writes:** `needs_clarification=True`
- **Job:** terminal stop when the idea is too vague. The UI shows the questions and
  lets the founder re-submit (answers go into `clarification_context`).
- **Edges out:** → `END`.

### Node C — `market_research`  (Agent 2: Market & Competitor Intelligence)
- **File:** `agents/market_intel.py`
- **Reads:** `idea_summary`, `target_customer`
- **Tools (2):** `web_search()` (Tavily HTTP) + `yc_search()` (scoped YC directory)
- **LLM:** schema `MarketResearchOutput`, temp `0.2`
- **Writes:** `market_research`, `competitor_count`, `web_search_results`, `yc_search_results`
- **Job:** ground the analysis in real search results — market size, growth signals,
  segments, and **only** competitors found in results (with `source_url`).
- **Edges out:** conditional → `strategy_category` (0 competitors) or `strategy_diff` (>0).

### Node D1 — `strategy_category`  (Agent 3, category-creation branch)
- **File:** `agents/strategy.py::strategy_category_node`
- **Reads:** `idea_summary`, `target_customer`, `market_research`
- **LLM:** schema `StrategyOutput`, temp `0.4`
- **Writes:** `strategy` (`strategy_type="category_creation"`)
- **Job:** when there are zero competitors, reason whether it's a true new category, no
  demand, or a missed search; produce positioning + a wedge.
- **Edges out:** → `business_model` **and** → `mvp` (fan-out).

### Node D2 — `strategy_diff`  (Agent 3, differentiation branch)
- **File:** `agents/strategy.py::strategy_differentiation_node`
- **Reads:** `competitor_count`, `idea_summary`, `target_customer`, `market_research.competitors`
- **LLM:** schema `StrategyOutput`, temp `0.4`
- **Writes:** `strategy` (`strategy_type="differentiation"`)
- **Job:** pick a differentiation axis, name competitor gaps, write the USP + anti-positioning + beachhead.
- **Edges out:** → `business_model` **and** → `mvp` (fan-out).

### Node E — `business_model`  (Agent 4a — PARALLEL)
- **File:** `agents/business_model.py`
- **Reads:** `idea_summary`, `target_customer`, `strategy`, `market_research`
- **LLM:** schema `BizModelOutput`, temp `0.2`
- **Writes:** `biz_model` (revenue model + pricing)
- **Edges out:** → `risk`.

### Node F — `mvp`  (Agent 4b — PARALLEL)
- **File:** `agents/mvp.py`
- **Reads:** `idea_summary`, `target_customer`, `strategy`, `market_research`
- **LLM:** schema `MVPOutput`, temp `0.2`
- **Writes:** `mvp` (phase-1 / phase-2 features + tech requirements)
- **Edges out:** → `risk`.

> **Why E and F are safe in parallel:** they read the same upstream fields but **write
> different keys** (`biz_model` vs `mvp`), so there is no write conflict. LangGraph runs
> them in the same "superstep" and only proceeds to `risk` once **both** finish.

### Node G — `risk`  (Agent 5: Risk Assessment)
- **File:** `agents/risk.py`
- **Reads:** `idea_summary`, `target_customer`, `market_research`, `strategy`, `biz_model`, `mvp`
- **LLM:** schema `RiskAssessmentOutput`, temp `0.3`
- **Writes:** `risk`, `requires_human_escalation`
- **Job:** devil's advocate across market / technical / business / **regulatory** risk;
  computes an overall 1–10 score and sets escalation if a regulated domain is detected.
- **Guardrail (belt-and-suspenders):** even if the model forgets, the node forces
  `requires_human_escalation=True` when `regulatory_risk.risk_level ∈ {high, critical}`.
- **Edges out:** conditional → `escalate` (escalation) or `END`.

### Node H — `escalate`  (guardrail control node, no LLM)
- **File:** `graph.py::escalate_node`
- **Reads:** `risk.regulatory_risk` · **Writes:** `escalation_warning`
- **Job:** insert a mandatory human-review warning before the approval gate.
- **Edges out:** → `END`.

---

## 4. Edges & routers (the decision logic)

### Static edges
| From | To |
|------|----|
| `clarify` | `END` |
| `strategy_category` | `business_model`, `mvp` |
| `strategy_diff` | `business_model`, `mvp` |
| `business_model` | `risk` |
| `mvp` | `risk` |
| `escalate` | `END` |

### Conditional edges (routers)
| Router | Location | Decides on | Outcomes |
|--------|----------|-----------|----------|
| **`route_entry`** | `START` | `start_at` | `validate_idea` / `market_research` / `strategy_*` / `[business_model, mvp]` / `risk` |
| **`route_after_validation`** (#1) | after `validate_idea` | `idea_validation.proceed` | `market_research` (True) / `clarify` (False) |
| **`route_after_market`** (#2) | after `market_research` | `competitor_count == 0` | `strategy_category` (0) / `strategy_diff` (>0) |
| **`route_after_risk`** (#3) | after `risk` | `requires_human_escalation` | `escalate` (True) / `END` (False) |

### The conditional entry point (powers the human re-run)
`route_entry` lets a run **start at any section** instead of always at the top. The UI's
"request changes" flow sets `start_at` to the chosen section and passes the previous
state back in, so only that section onward re-runs:

| `start_at` | Enters at |
|-----------|-----------|
| `idea` (default) | `validate_idea` |
| `market` | `market_research` |
| `strategy` | `strategy_category` or `strategy_diff` (by `competitor_count`) |
| `biz_model` | `business_model` only (MVP reused from prior state) |
| `mvp` | `mvp` only (Business Model reused from prior state) |
| `risk` | `risk` |

---

## 5. ASCII graph (for a slide)

```
                         ┌──────────── START ────────────┐
                         │   route_entry (start_at?)      │
                         └───────────────┬────────────────┘
                                         ▼ (default: idea)
                                  ┌──────────────┐
                                  │ validate_idea│  Agent 1
                                  └──────┬───────┘
                   proceed=False         │ proceed=True        ← Conditional #1
                 ┌───────────────────────┴───────────┐
                 ▼                                     ▼
            ┌─────────┐                        ┌────────────────┐
            │ clarify │                        │ market_research│ Agent 2 (+2 tools)
            └────┬────┘                        └───────┬────────┘
                 ▼                    competitor_count? │            ← Conditional #2
                END               ┌────────0───────────┴────────>0────────┐
                                  ▼                                        ▼
                        ┌──────────────────┐                   ┌──────────────────┐
                        │ strategy_category│                   │  strategy_diff   │ Agent 3
                        └────────┬─────────┘                   └────────┬─────────┘
                                 └───────────────┬──────────────────────┘
                                   (FAN-OUT: parallel)
                                 ┌───────────────┴───────────────┐
                                 ▼                               ▼
                       ┌──────────────────┐            ┌──────────────────┐
                       │ business_model   │ Agent 4a   │       mvp        │ Agent 4b
                       └────────┬─────────┘            └────────┬─────────┘
                                └──────────────┬────────────────┘
                                    (FAN-IN: risk waits for both)
                                               ▼
                                        ┌────────────┐
                                        │    risk    │ Agent 5
                                        └─────┬──────┘
                          escalate? True       │ False               ← Conditional #3
                            ┌──────────────────┴───────────┐
                            ▼                               ▼
                      ┌──────────┐                         END
                      │ escalate │ ──► END
                      └──────────┘

         (UI, after END) approve ─► PDF report   |   reject ─► set start_at ─► re-enter graph
```

---

## 6. Worst-case end-to-end walkthrough

We pick a deliberately **hard** idea that exercises the **maximum number of nodes and
edges**: it starts vague (clarify loop), comes back as a niche idea (zero competitors →
category creation), and touches regulated data (escalation), then the human rejects one
section (re-run). This single story demonstrates *every* branch.

**Idea submitted:** *"An AI app for health stuff."*

### Pass 1 — vague input
| Step | Node | State change |
|------|------|--------------|
| 1 | `START` → `route_entry` | `start_at="idea"` → `validate_idea` |
| 2 | `validate_idea` | `idea_validation.proceed=False`, `problem_clarity=2`, `clarifying_questions=["Who is the user?", "What health problem?", "What do they do today?"]`, `needs_clarification=True` |
| 3 | `route_after_validation` (#1) | `proceed=False` → **`clarify`** |
| 4 | `clarify` → `END` | pipeline pauses; UI shows the 3 questions |

> Demonstrates: conditional #1 (False path) + the clarify control node + the
> human-in-the-loop *input* gate.

### Pass 2 — founder re-submits with answers
Founder answers → `clarification_context` is filled, idea becomes:
*"A tool that lets small clinics auto-summarize patient visit notes into structured records."*

| Step | Node | State change |
|------|------|--------------|
| 5 | `validate_idea` | now `proceed=True`, `idea_summary="..."`, `target_customer="Small private clinics (1-5 doctors)"` |
| 6 | `route_after_validation` (#1) | `proceed=True` → **`market_research`** |
| 7 | `market_research` | tools run: `web_search()` + `yc_search()`. Suppose niche → `competitor_count=0`, `market_research` populated, `web_search_results`/`yc_search_results` stored |
| 8 | `route_after_market` (#2) | `competitor_count==0` → **`strategy_category`** |
| 9 | `strategy_category` | `strategy.strategy_type="category_creation"`, `scenario="C"`, positioning + wedge written |
| 10 | FAN-OUT | edges to **both** `business_model` and `mvp` |
| 11a | `business_model` (parallel) | `biz_model` = {revenue_model, pricing} |
| 11b | `mvp` (parallel) | `mvp` = {phase_1_features, phase_2_features, tech_requirements} |
| 12 | FAN-IN | `risk` runs only after **both** 11a & 11b complete |
| 13 | `risk` | `regulatory_risk.risk_level="critical"` (HIPAA — patient health data) → `requires_human_escalation=True`, `overall_risk_score=9` |
| 14 | `route_after_risk` (#3) | escalation True → **`escalate`** |
| 15 | `escalate` → `END` | `escalation_warning="⚠️ touches HIPAA-regulated health data ..."` |

> Demonstrates: conditional #1 (True path), tool use, conditional #2 (category branch),
> the parallel fan-out/fan-in, conditional #3 (escalation), guardrail node.

### Pass 3 — human rejects the MVP section
At the approval gate the human is **not satisfied with the MVP scope** and writes a note
*"focus on offline-first for clinics with poor internet"*. They pick section **`mvp`**
(Business Model and MVP are separately selectable).

| Step | Node | State change |
|------|------|--------------|
| 16 | UI | `start_at="mvp"`, `revision_note="focus on offline-first..."`, prior state reused |
| 17 | `START` → `route_entry` | `start_at="mvp"` → **`mvp`** (re-enters at the MVP node only) |
| 18 | `mvp` | re-runs with the note injected via `with_revision()` → new offline-first `phase_1_features` |
| 19 | `risk` | re-evaluates using the new MVP + the **reused** Business Model from prior state |
| 20 | `route_after_risk` (#3) | still regulated → `escalate` → `END` |

Idea Validation, Market, Strategy, **and Business Model** are **not** re-run — their
earlier results are reused from the prior state. (Picking `biz_model` instead would
re-run only Business Model and reuse the prior MVP.) The human approves → **PDF
generated** (the only irreversible action).

> Demonstrates: the conditional entry point, revision-note injection, and that a re-run
> only touches the chosen section onward.

---

## 7. Suggested presentation flow (maps to the brief's 10-min structure)

| Time | Slide content | Pull from |
|------|---------------|-----------|
| 0–1 min | Problem + target user | README §1–3 |
| 1–2 min | Why multi-agent (not a chatbot): 6 specialized roles, structured hand-offs | this doc §1, §3 |
| 2–4 min | Architecture: the ASCII graph, the shared state baton, the 3 conditionals + parallelism | this doc §2, §4, §5 |
| 4–7 min | Live demo: run the worst-case idea, show logs + the clarify loop + escalation + re-run | this doc §6 |
| 7–8.5 min | Eval cases (5 branches), guardrails, observability (logs/LangSmith), limitations | README §6, evals/ |
| 8.5–10 min | Per-student contributions | README §9 |

**Three things evaluators love that this graph gives you:**
1. A **visible decision** at every router (logs print `↳ route ...`).
2. **Genuine parallelism** (fan-out/fan-in), not just a straight line.
3. **Two human gates** — input clarification and output approval/re-run — so the
   human-in-the-loop is functional, not cosmetic.

---

## 8. Individual contributions (for the 15% viva criterion)

Each member owns specific nodes/files and must be able to explain how their part
connects to the shared `GraphState` and the rest of the graph.

| Member | Owns | Files | Graph nodes / components |
|--------|------|-------|--------------------------|
| **Noorain** | Market Intelligence + Strategy + **graph orchestration** | `agents/market_intel.py`, `agents/strategy.py`, `tools/tavily_search.py`, `tools/yc_search.py`, `graph.py` | `market_research`, `strategy_category`, `strategy_diff`; all routers (`route_entry`, `route_after_validation`, `route_after_market`, `route_after_risk`); parallel fan-out/fan-in wiring; conditional entry point |
| **Pooja** | Idea Validation + MVP + **prompts** | `agents/idea_validation.py`, `agents/mvp.py`, `prompts.py` | `validate_idea` (Agent 1), `mvp` (Agent 4b, parallel); authored the system prompt + all per-agent prompts |
| **Shruti** | Business Model + Risk + **evaluation** | `agents/business_model.py`, `agents/risk.py`, `evals/run_eval.py` | `business_model` (Agent 4a, parallel), `risk` (Agent 5) + the regulatory-escalation guardrail; the 5 evaluation test cases |

### What each member should be ready to explain in the Q&A

**Noorain — Market, Strategy & the graph**
- How the two tools (Tavily web search + YC directory) ground Agent 2 and why YC
  replaces Crunchbase (no free tier).
- The strategy **branch** (`route_after_market`): why `competitor_count == 0` routes to
  category-creation vs differentiation.
- How the graph is wired: nodes, edges, the 3 conditional routers, the parallel
  fan-out/fan-in, and the conditional entry point that powers the human re-run.

**Pooja — Idea Validation, MVP & prompts**
- The clarify branch: how Agent 1's `proceed=False` routes to `clarify` and asks
  questions (`route_after_validation`).
- Why MVP runs in parallel with Business Model and writes a separate state key (`mvp`).
- The prompt design: the shared `SYSTEM_PROMPT`, per-agent prompts, and how
  `PydanticOutputParser` enforces structured JSON output.

**Shruti — Business Model, Risk & tests**
- Why Business Model is `usage_based`/pricing logic and how it reads `strategy`.
- The Risk agent's 4 dimensions and the **guardrail**: how `regulatory_risk ∈
  {high, critical}` forces `requires_human_escalation=true` → routes to `escalate`.
- The 5 evaluation scenarios in `evals/run_eval.py`, one per branch (vague→clarify,
  competitors→differentiation, niche→category, regulated→escalation, clean→end).

> **Shared foundation (everyone should know):** the single `GraphState` TypedDict
> (`state.py`) is the contract between all nodes — agreed on day 1 and treated as
> read-only unless the whole team approves a change. This is the answer to the
> "state management" rubric criterion.
