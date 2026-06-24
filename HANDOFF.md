# Project Handoff — Startup Idea Validator (Multi-Agent System)

> Paste this whole file into a new AI session (or hand it to a teammate) to get
> full context and continue the work. It describes what the project is, how it's
> built, the current state, how to run it, and what's left.

---

## 1. What this is

A **capstone project** for the course *Multi-Agent Orchestration [AI/ML]*. It is a
multi-agent AI product built with **LangGraph** that validates a raw startup idea
end-to-end. A founder submits an idea; five specialized agents run in sequence,
passing shared state, and produce a structured validation report (PDF) gated by a
human approval step.

**It is deliberately NOT a chatbot** — it has 5 agents, structured hand-offs, real
tool use, 3 conditional branches, guardrails, and a human-in-the-loop gate, to
satisfy the capstone brief.

**Team:** 3 students. **Eval:** 10-min demo + 5-min Q&A (exam week 25–30 June).

---

## 2. The agents (the pipeline) — 6 specialized agents

1. **Idea Validation** — scores problem clarity / target / pain; decides `proceed`
   or bounces back with clarifying questions.
2. **Market & Competitor Intelligence** — calls Tavily web search + YC directory
   search; extracts market size, signals, segments, real competitors (with URLs).
3. **Strategy** — two branches: *differentiation* (competitors exist) or
   *category-creation* (zero competitors).
4a. **Business Model** — revenue model + pricing. **Runs in parallel with 4b.**
4b. **MVP** — ruthless 2-phase feature scope + tech requirements. **Parallel with 4a.**
5. **Risk Assessment** — devil's advocate across market/technical/business/
   regulatory risk; flags regulated domains for human escalation.

### Graph flow, parallelism & conditional entry

```
START ─(entry router: start_at)─► validate_idea
  ├─ proceed=False ──────────────► clarify ──► END             (Conditional #1)
  └─ proceed=True  ──► market_research
                          ├─ competitor_count==0 ► strategy_category ┐  (Conditional #2)
                          └─ competitor_count >0 ► strategy_diff ─────┤
                                                                      ▼
                                       ┌── business_model ──┐  (fan-OUT: parallel)
                                       └── mvp ─────────────┤  (fan-IN: risk waits)
                                                            ▼
                                                          risk
                          ┌─ requires_human_escalation ► escalate ► END  (Conditional #3)
                          └─ else ──────────────────────────────────► END
```

- **Parallel:** Business Model (4a) + MVP (4b) fan out from Strategy and run
  concurrently; Risk fans them in and runs once. They write distinct state keys
  (`biz_model`, `mvp`) so there's no write conflict.
- **Conditional entry (`route_entry`):** a run can START at any section via
  `start_at`. This powers the human re-run loop.

Human-in-the-loop = the approval gate in Streamlit:
- **Approve** → generate + download the PDF (the only irreversible action).
- **Request changes** → pick ONE section (single-select) + optional note → re-run
  the pipeline from that section onward, reusing earlier results. The note is
  injected into prompts via `llm.with_revision()`.

---

## 3. Tech stack & key decisions

| Layer | Choice | Notes |
|-------|--------|-------|
| Orchestration | **LangGraph** `StateGraph` | nodes, edges, 3 conditional routers |
| LLM access | **OpenRouter** (OpenAI-compatible) | provider set by `LLM_PROVIDER`; also supports `openai` / `anthropic` |
| Current model | `openai/gpt-oss-120b:free` | free tier; slow (~10-13s/call) and can rate-limit. Switch to `openai/gpt-4o` for the live demo |
| Structured output | **PydanticOutputParser** (manual JSON parse + 1 retry) | **NOT** `with_structured_output` — free models don't support native structured-output/tool-calling, so we parse JSON ourselves. See §6. |
| Tools | **Tavily web search** + **YC directory search** | plain `requests` HTTP call, no retry/cache wrapper (kept simple) |
| Schemas | **Pydantic v2** | one model per agent hand-off, in `models.py` |
| State | single `GraphState` TypedDict | `state.py` — shared by all nodes |
| Observability | **clear logs** now; **LangSmith** later (env-var only, zero code) | rubric accepts logs OR LangSmith |
| UI | **Streamlit** (`app.py`) | input → per-agent output → approval → PDF |
| PDF | **fpdf2** (`report.py`) | the gated irreversible action |
| Evals | 5 scenarios (`evals/run_eval.py`) | one per branch |

**Why YC search instead of Crunchbase:** Crunchbase API has no free tier
(~$49–79/mo). A scoped `site:ycombinator.com/companies` search is the free,
authoritative substitute and counts as a distinct second tool.

**RAG justification (brief requires use-or-justify):** the data needed is fresh &
external (live competitors/funding), so we ground via live web retrieval rather
than a vector store that would go stale. Documented in README §7.3.

---

## 4. File map

```
AI_Startup_Mentor/
├── README.md            # full project spec + rubric mapping (instructor-facing)
├── HANDOFF.md           # this file
├── requirements.txt     # langgraph, langchain, langchain-openai/anthropic, streamlit, fpdf2, requests, python-dotenv
├── .env                 # REAL keys (gitignored) — LLM_PROVIDER, LLM_MODEL, OPENROUTER_API_KEY, TAVILY_API_KEY
├── .env.example         # placeholder template (committed)
├── .gitignore           # excludes .env, .venv, __pycache__, reports/, *.pdf
├── logconf.py           # logging setup (LOG_LEVEL env)
├── llm.py               # get_llm() + run_structured()  ← provider switch + JSON parsing live here
├── prompts.py           # SYSTEM_PROMPT + one prompt per agent
├── models.py            # Pydantic v2 schemas (IdeaValidationOutput, MarketResearchOutput, StrategyOutput, BizModelOutput, RiskAssessmentOutput, ...)
├── state.py             # GraphState TypedDict
├── graph.py             # LangGraph wiring, routers, run_validation(); `python graph.py "idea"` runs headless
├── report.py            # generate_pdf(state) -> path  (fpdf2)
├── app.py               # Streamlit UI + 2 human gates (clarify loop, approval)
├── agents/
│   ├── idea_validation.py
│   ├── market_intel.py
│   ├── strategy.py         # strategy_category_node + strategy_differentiation_node
│   ├── business_model.py   # Agent 4a (parallel)
│   ├── mvp.py              # Agent 4b (parallel)
│   └── risk.py
├── tools/
│   ├── tavily_search.py   # web_search(), format_results()
│   └── yc_search.py       # yc_search()
└── evals/
    └── run_eval.py        # 5 scenarios; `python -m evals.run_eval`
```

---

## 5. How to run

```bash
cd /Users/syedanoorain/Documents/AI_Startup_Mentor
source .venv/bin/activate          # venv already created with all deps
streamlit run app.py               # UI at http://localhost:8501

# headless options:
python graph.py "An app that helps freelancers auto-generate invoices"
python -m evals.run_eval           # runs all 5 scenarios
```

`.env` already has working OpenRouter + Tavily keys. Logs print to the terminal.

### Test ideas (one per branch)
- Happy path / differentiation: *"A Slack-native tool that auto-summarizes long threads into action items for remote engineering managers."*
- Clarify loop: *"An app that uses AI to help people with stuff."*
- Category creation: *"A marketplace connecting retired competitive yo-yo champions with amateurs for paid 1:1 video coaching."*
- Guardrail / escalation: *"An app where users upload blood-test PDFs and our AI diagnoses conditions and recommends prescription dosages."*

---

## 6. Gotchas / things a new session MUST know

1. **Do NOT switch back to `with_structured_output`.** It failed on the free
   OpenRouter model (`ValueError: ... does not have a 'parsed' field`). We use
   `PydanticOutputParser` + manual parse + 1 retry in `llm.py::run_structured`.
   This is intentional and model-agnostic.
2. **Free model is slow & rate-limit-prone.** ~10-13s per LLM call → full run ~1
   min. For the live demo, set `LLM_MODEL=openai/gpt-4o` in `.env` (fast, reliable).
3. **Secrets.** `.env` holds real keys and is gitignored. Only `.env.example`
   (placeholders) is committed. Keys were shared in chat during setup — consider
   rotating them before final submission.
4. **fpdf2 latin-1 fonts.** `report.py` strips non-latin-1 chars (`_clean()`).
   Don't pass emoji/smart-quotes straight into the PDF without it.
5. **Streamlit reruns the whole script** on every interaction — results are cached
   in `st.session_state` so clicking "Approve" doesn't re-run the 5-agent pipeline.

---

## 7. Current status & what's left

**Done & verified:** all 18 files build; graph compiles (10 nodes); all 3 routers
work; PDF generates; a live single-agent call against the free model returns valid
structured output.

**Not yet done / next steps:**
- [ ] Run the **full pipeline live** end-to-end (Agent 1 + parallel split verified;
      full live run still recommended before demo day).
- [ ] Capture 5 LangSmith traces for the eval (flip `LANGCHAIN_TRACING_V2=true` + add key).
- [ ] Write each student's Individual Contribution Document (required by brief).
- [ ] Push to GitHub repo `Noorain464/ai_startup_mentor` (this repo's remote is set
      to push as the **Noorain464** account; other repos use `syedanoorain-hash`).
- [ ] Decide final demo model (recommend `openai/gpt-4o`).

---

## 8. Git / account note

This repo pushes as the **Noorain464** GitHub account (remote URL has the username
prefix; `credential.useHttpPath true` is set globally so the two accounts coexist).
The first push will prompt for Noorain464's username + a Personal Access Token.
