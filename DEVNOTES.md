# Canon — Developer Notes

## What It Does

**Canon** autonomously bridges a [Bonfires AI](https://github.com/NERDDAO/bonfires-sdk) knowledge graph with [Harmonica AI](https://github.com/harmonicabot/harmonica-mcp) deliberation sessions. A CLI pipeline queries the KG for topic context, designs structured facilitation sessions, deploys them to Harmonica, and — after participants respond — ingests the summary back into the KG as new entities and relationships.

Replaces a manual 10-step `harmonica-chat` session design process.

---

## Architecture

### 5-Step Pipeline

```
[Step 1 — Discover]
TopicAdvisor.discover_batch(query, n)
  kg.search(query) or kg.get_latest_episodes()
    → entities_md → agents.sync(tempfile) → agents.chat(discovery_prompt.md)
    → N topic suggestions stored in DB (batches + topics tables)

[Step 2 — Review]  ← human selects topic ID from --list-topics

[Step 3 — Design]
SurveyDesigner.build_survey_params_from_topic(topic_id, n)
  DB lookup → kg.search(topic) → session.md
    → agents.sync(session.md) → agents.chat(design_prompt.md)
    → N design variations stored in DB (batches + designs tables)

[Step 4 — Create]
SurveyDesigner.create_session_from_design(design_id)
  DB lookup → harmonica.create_session(**params)
    → join_url returned + stored in sessions table

[Step 5 — Ingest]
ResultsIngestor.ingest(session_id, kengram_id)
  harmonica.get_summary() → agents.chat(ingest_prompt, graph_mode="append")
    → kengrams.pin() for each surfaced entity
```

### Layers

| Layer | File(s) | Responsibility |
|---|---|---|
| CLI | `main.py` | Argument parsing, mode dispatch, env loading |
| Agent | `agent/topic_advisor.py` | KG scan → N topic suggestions with format recommendations |
| Agent | `agent/survey_designer.py` | DB topic → KG → session.md → N design variations |
| Agent | `agent/results_ingestor.py` | Harmonica summary → KG entities/edges |
| Client | `harmonica/client.py` | Thin REST wrapper for Harmonica API v1 |
| Store | `store/db.py` | SQLite — batches → topics → designs → sessions |
| Store | `store/vault.py` | Export DB to Obsidian vault (2 .md files per batch) |
| Prompt | `agent/prompts/design_prompt.md` | Session design instruction doc |
| Prompt | `agent/prompts/discovery_prompt.md` | Topic discovery instruction doc |

---

## DB Schema — `store/db.py`

Four tables in FK chain: `batches` → `topics` + `designs` → `sessions`.

```sql
CREATE TABLE batches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    batch_run_id TEXT UNIQUE,
    type         TEXT,      -- 'discovery' or 'design'
    query        TEXT,      -- seed query (discovery) or topic title (design)
    context_text TEXT,      -- KG entities markdown
    raw_response TEXT       -- raw agent response JSON
);

CREATE TABLE topics (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    batch_id          INTEGER REFERENCES batches(id),
    topic             TEXT,
    format_suggestion TEXT,
    template_id       TEXT
);

CREATE TABLE designs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    batch_id     INTEGER REFERENCES batches(id),
    topic_id     INTEGER REFERENCES topics(id),
    params_json  TEXT,
    template_id  TEXT,
    selected     INTEGER DEFAULT 0
);

CREATE TABLE sessions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    design_id            INTEGER REFERENCES designs(id),
    harmonica_session_id TEXT,
    join_url             TEXT,
    status               TEXT
);
```

`context_text` and `raw_response` are identical for all N topics/designs produced in one run,
so they live on `batches` rather than being repeated per row.

---

## Key Technical Decisions

| Decision | Choice | Reason |
|---|---|---|
| Harmonica API | Direct REST to `https://app.harmonica.chat/api/v1` | No MCP subprocess, no Node.js |
| Bonfires access | `bonfires` pip SDK | Official SDK; handles auth and KG ops |
| HTTP client | `httpx` | Sync now, trivial to upgrade to async |
| All metadata | English only | Harmonica's facilitation layer is English-only; non-Latin chars corrupt |
| KG mode (design) | `graph_mode="adaptive"` | Agent reads context without overwriting graph |
| KG mode (ingest) | `graph_mode="append"` | Adds new nodes/edges, never clobbers existing |
| Session context delivery | `session.md` via `agents.sync()` | Richer than inline bullet list; agent treats it as a document |
| Facilitation prompt | Agent-generated from `design_prompt.md` | Matches harmonica-chat Step 11 spec; editable without touching Python |
| Batch context storage | `batches` table owns context_text/raw_response | Context identical for all N rows in a run — store once |
| Vault format | 2 files per batch (context + list) | Diffable, Obsidian-compatible, no duplication |
| Discovery without query | `kg.get_latest_episodes()` | `kg.search()` requires non-empty string |
| topic_anchor in prompt | Prepend topic to chat message | Prevents agent going off-topic when KG context is broad |
| template_id | Optional free string passed to POST /sessions | No GET /templates endpoint exists in Harmonica API |

---

## Project Structure

```
canon/
├── harmonica/
│   ├── __init__.py                  exports HarmonicaClient
│   └── client.py                    REST wrapper — sessions, responses, summaries
├── agent/
│   ├── __init__.py                  exports SurveyDesigner, TopicAdvisor, ResultsIngestor
│   ├── prompts/
│   │   ├── design_prompt.md         session design instruction (edit to tune output)
│   │   └── discovery_prompt.md      topic discovery instruction (edit to tune output)
│   ├── survey_designer.py           DB topic → KG → session.md → design variations
│   ├── topic_advisor.py             KG scan → N topic suggestions
│   └── results_ingestor.py          Harmonica summary → KG entities/edges
├── store/
│   ├── __init__.py
│   ├── db.py                        SQLite schema and all CRUD functions
│   ├── vault.py                     Obsidian vault export (2 files per batch)
│   └── vault/                       generated — open in Obsidian
├── tests/
│   ├── test_harmonica_client.py     unit tests (mocked httpx)
│   └── test_integration_survey_designer.py  integration tests (live Bonfires)
├── main.py                          CLI entry point
├── .env.example                     env var template
├── requirements.txt
├── setup.cfg                        pycodestyle max-line-length = 100
├── README.md                        end-user documentation
└── DEVNOTES.md                      this file
```

---

## HarmonicaClient — `harmonica/client.py`

Thin REST wrapper mirroring [`harmonica-mcp/src/client.ts`](https://github.com/harmonicabot/harmonica-mcp).

**Auth:** `Authorization: Bearer {HARMONICA_API_KEY}` on every request.  
**Base URL:** `HARMONICA_API_URL` env var, default `https://app.harmonica.chat`.  
**Retry:** up to 3 attempts on HTTP 429 with `Retry-After` backoff. On the final attempt raises `HarmonicaError("Max retries exceeded")`.

| Method | Notes |
|---|---|
| `create_session(topic, goal, prompt, questions, cross_pollination, summary_prompt, context, distribution, template_id)` | Returns session dict including `join_url` |
| `get_session(session_id)` | Status, participant count, metadata |
| `list_sessions(status, keyword)` | Filterable list |
| `update_session(session_id, **fields)` | PATCH arbitrary fields |
| `search_sessions(query)` | Keyword search |
| `get_responses(session_id, ...)` | Participant threads with filtering |
| `generate_summary(session_id, prompt)` | Triggers async synthesis |
| `get_summary(session_id)` | Summary text + themes |

---

## TopicAdvisor — `agent/topic_advisor.py`

```python
discover(query=None) -> dict                   # single suggestion
discover_batch(query=None, n=3) -> list[dict]  # n suggestions, 'id' key added
```

**Flow:**
1. With `query`: `kg.search(query, num_results=20)` → entities
2. Without `query`: `kg.get_latest_episodes(agent_id, limit=20)` → episodes as entities
3. Serialize entities to markdown → write to tempfile → `agents.sync(tempfile)` → delete tempfile
4. `agents.chat(discovery_prompt.md)` with `<N>` replaced → parse JSON array
5. `db.insert_batch()` then `db.insert_topic()` per suggestion

**Prompt:** `agent/prompts/discovery_prompt.md` loaded once at import. Edit to tune output.

---

## SurveyDesigner — `agent/survey_designer.py`

```python
build_survey_params_from_topic(topic_id, n=1) -> list[dict]
create_session_from_design(design_id, template_id=None) -> dict
build_survey_params(topic_query) -> dict       # legacy single-shot
create_session(topic_query) -> dict            # legacy single-shot
```

**Batch flow (`build_survey_params_from_topic`):**
1. `db.get_topic(topic_id)` → topic text + format_suggestion
2. `kg.search(topic, num_results=10)` → entities
3. Build session.md content; `agents.sync(session.md)`
4. Prepend `topic_anchor` to prompt (prevents off-topic agent output)
5. n=1: single `agents.chat()` call, wrap result in list
6. n>1: append `_DESIGN_PROMPT_BATCH_SUFFIX` with `<N>` substituted; parse JSON array
7. `db.insert_batch()` then `db.insert_design()` per variation

**Prompt:** `agent/prompts/design_prompt.md` loaded once at import. Edit to tune output.

---

## ResultsIngestor — `agent/results_ingestor.py`

```python
ingest(session_id, kengram_id) -> {"entities_pinned": int, "kengram_id": str}
```

**Flow:**
1. `harmonica.get_summary(session_id)` → summary text
2. `agents.chat(ingest_prompt, graph_mode="append")` → entity extraction
3. `agents.sync(message=summary_text)` → push episode to KG
4. `kg.search(summary_text[:200])` → find surfaced entities
5. `kengrams.pin(kengram_id, uuid)` for each UUID

---

## CLI — `main.py`

```
python main.py --discover [QUERY]              # discover topics (full scan if no query)
python main.py --discover "QUERY" --batch N    # N topic suggestions
python main.py --list-topics                   # show stored topics
python main.py --design TOPIC_ID               # generate design
python main.py --design TOPIC_ID --batch N     # N design variations
python main.py --list-designs [TOPIC_ID]       # show stored designs
python main.py --create DESIGN_ID              # create Harmonica session
python main.py --session SESSION_ID            # poll status
python main.py --session ID --ingest KG_ID     # ingest into KG
python main.py --export-vault                  # regenerate Obsidian vault
python main.py --topic "QUERY"                 # (legacy) single-shot
```

`--list-topics`, `--list-designs`, `--export-vault` are read-only and skip client init.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BONFIRE_API_KEY` | Yes | Bonfires API key |
| `BONFIRE_ID` | Yes | Target bonfire (KG) ID |
| `BONFIRE_AGENT_ID` | Yes | Bonfires agent ID |
| `HARMONICA_API_KEY` | Yes | Harmonica key (`hm_live_...`) |
| `HARMONICA_API_URL` | No | Override base URL |

---

## Testing

```bash
python -m pytest tests/test_harmonica_client.py -v          # unit (no network)
python -m pytest tests/test_integration_survey_designer.py -v # integration
python -m pytest tests/ -v                                   # full suite
```

---

## Known Issues

- **Sparse KG** — if `kg.search()` returns no relevant entities the agent defaults to a session about "deliberation design". Populate the KG before running.
- **Ingest pinning** — pins entities found by post-sync KG search, not necessarily the newly created nodes. May miss nodes not yet indexed.

---

## Reference Links

| Resource | URL |
|---|---|
| Bonfires SDK | https://github.com/NERDDAO/bonfires-sdk |
| Harmonica MCP | https://github.com/harmonicabot/harmonica-mcp |
| Harmonica Chat (prompt patterns) | https://github.com/harmonicabot/harmonica-chat |
| Harmonica API base | https://app.harmonica.chat/api/v1 |
