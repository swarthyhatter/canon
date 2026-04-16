# Canon — Project Plan

## Overview

**Canon** is an autonomous integration between [Bonfires AI](https://github.com/NERDDAO/bonfires-sdk) and [Harmonica AI](https://github.com/harmonicabot/harmonica-mcp). A Bonfires knowledge graph (KG) agent queries its own graph for topic context, generates structured Harmonica survey parameters, creates a live deliberation session, and — after human participants respond — ingests the Harmonica summary back into the KG as new entities and relationships.

This replaces a manual 10-step `harmonica-chat` session design process with a single CLI command.

---

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                           Canon                                 │
│                                                                 │
│  topic_query                                                    │
│      │                                                          │
│      ▼                                                          │
│  ┌──────────────────┐    KG entities     ┌──────────────────┐  │
│  │  Bonfires KG     │ ──────────────────▶│  SurveyDesigner  │  │
│  │  (kg.search)     │                    │  (agent prompt)  │  │
│  └──────────────────┘                    └────────┬─────────┘  │
│                                                   │            │
│                                          survey params (JSON)  │
│                                                   │            │
│                                                   ▼            │
│                                          ┌──────────────────┐  │
│                                          │ HarmonicaClient  │  │
│                                          │ create_session() │  │
│                                          └────────┬─────────┘  │
│                                                   │            │
│                                          session_id + URL      │
│                                                   │            │
│                                                   ▼            │
│                                          [ Human participants  │
│                                            respond in browser ]│
│                                                   │            │
│                                          summary text          │
│                                                   │            │
│                                                   ▼            │
│  ┌──────────────────┐    new entities    ┌──────────────────┐  │
│  │  Bonfires KG     │ ◀──────────────────│ ResultsIngestor  │  │
│  │  (agents.sync)   │                    │ (agents.chat)    │  │
│  └──────────────────┘                    └──────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Layers

| Layer | Files | Responsibility |
|---|---|---|
| CLI / Orchestrator | `main.py` | Entry point, mode dispatch, env loading |
| Agent | `agent/survey_designer.py`, `agent/results_ingestor.py` | Bonfires ↔ Harmonica orchestration |
| Client | `harmonica/client.py` | Thin REST wrapper for Harmonica API v1 |
| External APIs | Bonfires SDK, Harmonica REST | KG storage + deliberation platform |

---

## Key Technical Decisions

| Decision | Choice | Reason |
|---|---|---|
| Harmonica API | Direct REST to `https://app.harmonica.chat/api/v1` | No MCP subprocess, no Node.js dependency |
| Bonfires access | `bonfires` pip SDK | Official SDK; handles auth and KG graph operations |
| HTTP client | `httpx` | Async-capable; sync used now, easy to upgrade |
| Language | English only for topic/goal/prompt | Harmonica metadata constraint |
| KG write mode (design) | `graph_mode="adaptive"` | Lets agent surface relevant context without overwriting |
| KG write mode (ingest) | `graph_mode="append"` | Adds new entities/edges without clobbering existing graph |

---

## Project Structure

```
canon/
├── harmonica/
│   ├── __init__.py             ✅ exports HarmonicaClient
│   └── client.py               ✅ REST wrapper — all methods implemented
├── agent/
│   ├── __init__.py             ✅ exports SurveyDesigner, ResultsIngestor
│   ├── survey_designer.py      ✅ KG context → survey params → create session
│   └── results_ingestor.py     ❌ TODO — ingest summary → KG entities/edges
├── main.py                     ❌ TODO — CLI orchestrator
├── .env.example                ✅
├── requirements.txt            ✅
└── PLAN.md                     ✅ this file
```

---

## Component Specifications

### `harmonica/client.py` — HarmonicaClient ✅

Thin REST wrapper mirroring [`harmonica-mcp/src/client.ts`](https://github.com/harmonicabot/harmonica-mcp).

**Auth:** `Authorization: Bearer {HARMONICA_API_KEY}` on every request.  
**Base URL:** `HARMONICA_API_URL` env var, default `https://app.harmonica.chat`.  
**Retry:** up to 3 attempts on HTTP 429 with `Retry-After` backoff.

| Method | Signature | Notes |
|---|---|---|
| `create_session` | `(topic, goal, prompt, questions, cross_pollination, summary_prompt, context, distribution) → dict` | Returns session dict with `id` and participant URL |
| `get_session` | `(session_id) → dict` | Session details + status |
| `list_sessions` | `(status, keyword) → list[dict]` | Filter by status or keyword |
| `update_session` | `(session_id, **fields) → dict` | PATCH arbitrary fields |
| `search_sessions` | `(query) → list[dict]` | Keyword search |
| `list_participants` | `(session_id) → list[dict]` | |
| `get_responses` | `(session_id, since, participant_name, min_messages, limit, last_seen_message_id) → list[dict]` | Participant threads |
| `get_questions` | `(session_id) → list[dict]` | |
| `chat_message` | `(session_id, message) → dict` | |
| `submit_questions` | `(session_id, answers) → dict` | Pre-session intake |
| `generate_summary` | `(session_id, prompt) → dict` | Triggers async synthesis |
| `get_summary` | `(session_id) → dict` | Summary text + themes |
| `list_telegram_groups` | `() → list[dict]` | Distribution targets |

---

### `agent/survey_designer.py` — SurveyDesigner ✅

Uses Bonfires KG + agent to generate Harmonica session parameters from graph context.

```python
class SurveyDesigner:
    def __init__(self, bonfire_client: BonfiresClient, harmonica_client: HarmonicaClient)
    def build_survey_params(self, topic_query: str) -> dict
    def create_session(self, topic_query: str) -> dict
```

**Flow inside `build_survey_params`:**
1. `bonfire.kg.search(topic_query, num_results=10)` → surface relevant entities
2. Format entities as `- name [labels]: summary` context block
3. `bonfire.agents.chat(prompt, graph_mode="adaptive")` → agent produces JSON
4. Strip markdown fences, `json.loads()` → return structured dict

**Agent prompt produces:**
- `topic` — concise English title (max 10 words)
- `goal` — what we want to discover (1–2 sentences)
- `prompt` — AI facilitator instructions (2–4 sentences; guide concrete experiences)
- `questions` — list of 2–4 intake question objects `{"text": "..."}`
- `cross_pollination` — bool
- `summary_prompt` — custom analysis directive (1 sentence)

---

### `agent/results_ingestor.py` — ResultsIngestor ❌ TODO

Parses a completed Harmonica session summary back into the Bonfires KG.

```python
class ResultsIngestor:
    def __init__(self, bonfire_client: BonfiresClient, harmonica_client: HarmonicaClient)
    def ingest(self, session_id: str, kengram_id: str) -> dict
```

**Flow inside `ingest`:**
1. `harmonica.get_summary(session_id)` → summary text + themes
2. `bonfire.agents.chat(summary_text, graph_mode="append")` → agent extracts entities/relationships
3. `bonfire.agents.sync()` → push episode to KG
4. `bonfire.kengrams.pin(kengram_id, ...)` → pin newly surfaced entities
5. Return `{ "entities_added": int, "edges_added": int, "kengram_id": str }`

---

### `main.py` — Orchestrator CLI ❌ TODO

```
usage: python main.py [--topic QUERY] [--session SESSION_ID] [--ingest]
```

| Flags | Mode | Behavior |
|---|---|---|
| *(none)* | Interactive | Prompt for topic, run full design flow, print participant URL |
| `--topic QUERY` | Non-interactive | Auto-design survey from KG query, print participant URL |
| `--session ID` | Poll | Print session status and response count |
| `--session ID --ingest` | Ingest | Ingest completed session back into KG, print summary |

**Implementation notes:**
- Load `.env` via `python-dotenv` at startup
- Instantiate `BonfiresClient`, `HarmonicaClient`, `SurveyDesigner`, `ResultsIngestor`
- Use `argparse` for flag parsing
- Print participant URL prominently after session creation

---

## Environment Variables

| Variable | Required | Description | Example |
|---|---|---|---|
| `BONFIRE_API_KEY` | Yes | Bonfires API key | `bf_live_...` |
| `BONFIRE_ID` | Yes | Target bonfire (KG) ID | `abc123` |
| `BONFIRE_AGENT_ID` | Yes | Bonfires agent ID for chat | `agent_xyz` |
| `HARMONICA_API_KEY` | Yes | Harmonica API key | `hm_live_...` |
| `HARMONICA_API_URL` | No | Override API base URL | `https://app.harmonica.chat` |

Copy `.env.example` to `.env` and fill in values before running.

---

## Dependencies

```
bonfires>=0.4.0      # Bonfires KG + agent SDK
httpx>=0.27          # HTTP client (sync + async capable)
python-dotenv>=1.0   # Load .env into os.environ
```

Install: `pip install -r requirements.txt`

---

## Implementation Checklist

### Core Components
- [x] `harmonica/client.py` — HarmonicaClient REST wrapper
- [x] `agent/survey_designer.py` — KG context → Harmonica session
- [x] `agent/results_ingestor.py` — Harmonica summary → KG entities/edges
- [x] `main.py` — CLI orchestrator (4 modes)

### Testing
- [ ] Unit tests: `HarmonicaClient` with mocked `httpx` responses
  - [ ] Auth header present on all requests
  - [ ] Retry logic fires on HTTP 429 with `Retry-After` backoff
  - [ ] `HarmonicaError` raised on 4xx/5xx
- [ ] Integration test: `SurveyDesigner.build_survey_params()` against live Bonfires agent
  - [ ] Returns valid JSON with all required keys
  - [ ] `topic` and `goal` are English strings
- [ ] End-to-end: create a real Harmonica session via `--topic`
  - [ ] Session appears at `https://app.harmonica.chat`
  - [ ] Participant URL is accessible
- [ ] End-to-end: respond as participant, then run `--session ID --ingest`
  - [ ] `ingest()` returns non-zero `entities_added` or `edges_added`
- [ ] Verify new entities/edges in Bonfires KG via `bonfire.kg.search()`

---

## Reference Links

| Resource | URL |
|---|---|
| Bonfires SDK (pip: `bonfires`) | https://github.com/NERDDAO/bonfires-sdk |
| Harmonica MCP (API reference) | https://github.com/harmonicabot/harmonica-mcp |
| Harmonica Chat (survey design patterns) | https://github.com/harmonicabot/harmonica-chat |
| Harmonica Web App | https://github.com/harmonicabot/harmonica-web-app |
| Harmonica API base | https://app.harmonica.chat/api/v1 |
