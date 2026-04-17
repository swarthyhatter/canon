# Canon

Autonomous bridge between a [Bonfires AI](https://github.com/NERDDAO/bonfires-sdk) knowledge graph and [Harmonica AI](https://github.com/harmonicabot/harmonica-mcp) deliberation sessions. A single CLI command queries the KG for topic context, designs a structured facilitation session, deploys it to Harmonica, and — after participants respond — ingests the summary back into the KG as new entities and relationships.

Replaces a manual 10-step `harmonica-chat` session design process.

---

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in BONFIRE_API_KEY, BONFIRE_ID, BONFIRE_AGENT_ID, HARMONICA_API_KEY
python main.py
```

---

## CLI Usage

| Command | What it does |
|---|---|
| `python main.py` | Interactive — prompts for topic query |
| `python main.py --topic "QUERY"` | Design + deploy a Harmonica session from KG context |
| `python main.py --session SESSION_ID` | Poll session status and response count |
| `python main.py --session ID --ingest KG_ID` | Ingest completed session summary into KG |

---

## Architecture

### Full Data Flow

```
topic_query
    │
    ▼
bonfire.kg.search(topic_query, num_results=10)
    │  Surfaces relevant KG entities (name, summary, labels)
    ▼
_write_session_md(topic_query, entities)
    │  Serializes entities to a Markdown document (session.md)
    ▼
bonfire.agents.sync(file_path="session.md")
    │  Injects session.md into the Bonfires agent context window
    ▼
bonfire.agents.chat(design_prompt.md, graph_mode="adaptive")
    │  Agent reads context + prompt, returns JSON:
    │  { topic, goal, context, prompt, questions,
    │    cross_pollination, summary_prompt }
    ▼
HarmonicaClient.create_session(**params)
    │  POST /api/v1/sessions → returns session dict with join_url
    ▼
join_url → printed to CLI / shared with participants
    │
    ▼
[Participants respond in Harmonica web app]
    │
    ▼
HarmonicaClient.get_summary(session_id)
    │  GET /api/v1/sessions/{id}/summary → summary text + themes
    ▼
bonfire.agents.chat(ingest_prompt, graph_mode="append")
    │  Agent extracts entities/relationships and writes them to KG
    ▼
bonfire.agents.sync(message=summary_text)
    │  Pushes the episode as a document to the KG stack
    ▼
bonfire.kg.search(summary_text[:200], num_results=5)
    │  Finds newly surfaced entity UUIDs
    ▼
bonfire.kengrams.pin(kengram_id, uuid)  [× per entity]
    │  Pins entities to the target kengram
    ▼
{ "entities_pinned": N, "kengram_id": "..." }
```

### Component Layers

| Layer | File(s) | Responsibility |
|---|---|---|
| CLI | `main.py` | Argument parsing, mode dispatch, env loading |
| Agent | `agent/survey_designer.py` | KG → session.md → Harmonica session |
| Agent | `agent/results_ingestor.py` | Harmonica summary → KG entities/edges |
| Client | `harmonica/client.py` | Thin REST wrapper for Harmonica API v1 |
| Prompt | `agent/prompts/design_prompt.md` | Agent instruction doc loaded at import |

### Project Structure

```
canon/
├── harmonica/
│   ├── __init__.py                  exports HarmonicaClient
│   └── client.py                    REST wrapper — sessions, responses, summaries
├── agent/
│   ├── __init__.py                  exports SurveyDesigner, ResultsIngestor
│   ├── prompts/
│   │   └── design_prompt.md         agent instruction doc (edit to tune output)
│   ├── survey_designer.py           KG → session.md → Harmonica session
│   └── results_ingestor.py          Harmonica summary → KG entities/edges
├── tests/
│   ├── test_harmonica_client.py     unit tests (mocked httpx)
│   └── test_integration_survey_designer.py  integration tests (live Bonfires)
├── main.py                          CLI entry point
├── .env.example                     env var template
├── requirements.txt
├── setup.cfg                        pycodestyle max-line-length = 100
├── README.md                        this file
└── DEVNOTES.md                      developer notes and architecture detail
```

---

## HarmonicaClient

Thin REST wrapper around `https://app.harmonica.chat/api/v1`.

**Auth:** `Authorization: Bearer {HARMONICA_API_KEY}` on every request.  
**Retry:** up to 3 attempts on HTTP 429 with `Retry-After` backoff.

| Method | Description |
|---|---|
| `create_session(topic, goal, prompt, questions, ...)` | Create session, returns dict with `join_url` |
| `get_session(session_id)` | Status, participant count, metadata |
| `list_sessions(status, keyword)` | Filterable session list |
| `update_session(session_id, **fields)` | PATCH arbitrary fields |
| `get_responses(session_id, ...)` | Participant threads with filtering |
| `generate_summary(session_id, prompt)` | Trigger async synthesis |
| `get_summary(session_id)` | Summary text + themes |

---

## SurveyDesigner

```
build_survey_params(topic_query) -> dict
create_session(topic_query) -> dict
```

1. `kg.search(topic_query)` → entities
2. `_write_session_md()` → writes `session.md` to cwd
3. `agents.sync(file_path="session.md")` → injects doc into agent context
4. `agents.chat(design_prompt.md)` → agent returns JSON with all session fields
5. Parse JSON → return dict ready for `HarmonicaClient.create_session(**params)`

**Facilitation prompt:** `agent/prompts/design_prompt.md` is loaded once at import. Edit it to tune agent output — no Python changes needed.

---

## ResultsIngestor

```
ingest(session_id, kengram_id) -> {"entities_pinned": int, "kengram_id": str}
```

1. `harmonica.get_summary(session_id)` → summary text
2. `agents.chat(ingest_prompt, graph_mode="append")` → entity extraction + KG write
3. `agents.sync(message=summary_text)` → push episode to KG
4. `kg.search(summary_text[:200])` → find surfaced entity UUIDs
5. `kengrams.pin(kengram_id, uuid)` for each UUID

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BONFIRE_API_KEY` | Yes | Bonfires API key |
| `BONFIRE_ID` | Yes | Target bonfire (KG) ID |
| `BONFIRE_AGENT_ID` | Yes | Bonfires agent ID |
| `HARMONICA_API_KEY` | Yes | Harmonica key (`hm_live_...`) |
| `HARMONICA_API_URL` | No | Override base URL (default: `https://app.harmonica.chat`) |

---

## Testing

```bash
python -m pytest tests/test_harmonica_client.py -v          # unit (no network)
python -m pytest tests/test_integration_survey_designer.py -v # integration (live Bonfires)
python -m pytest tests/ -v                                   # full suite
```

---

## Known Issues

- **Sparse KG** — if `kg.search()` returns no relevant entities, the agent defaults to a generic session about "deliberation design". Populate the KG with relevant content before running.
- **`session.md` written to cwd** — should use a temp path in production to avoid polluting the working directory.
- **Ingest pinning** — pins entities found by a post-sync KG search, not necessarily the newly created nodes. May miss entities not yet indexed.
