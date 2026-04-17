# Canon — Developer Notes

## What It Does

**Canon** autonomously bridges a [Bonfires AI](https://github.com/NERDDAO/bonfires-sdk) knowledge graph with [Harmonica AI](https://github.com/harmonicabot/harmonica-mcp) deliberation sessions. A single CLI command queries the KG for topic context, designs a structured facilitation session, deploys it to Harmonica, and — after participants respond — ingests the summary back into the KG as new entities and relationships.

Replaces a manual 10-step `harmonica-chat` session design process.

---

## Architecture

### Data Flow

```
topic_query
    │
    ▼
bonfire.kg.search()           ← surfaces relevant KG entities
    │
    ▼
_write_session_md()           ← formats entities into session.md
    │
    ▼
agents.sync(file_path)        ← injects session.md into agent context
    │
    ▼
agents.chat(design_prompt.md) ← agent produces JSON: topic/goal/context/prompt/questions
    │
    ▼
HarmonicaClient.create_session(**params)
    │
    ▼
join_url → printed to CLI / shared with participants
    │
    ▼
[Participants respond in Harmonica web app]
    │
    ▼
harmonica.get_summary(session_id)
    │
    ▼
agents.chat(ingest_prompt, graph_mode="append") ← extracts entities/relationships
    │
    ▼
agents.sync(message)          ← pushes episode to KG stack
    │
    ▼
kengrams.pin(kengram_id, uuid) ← pins surfaced entities
```

### Layers

| Layer | File(s) | Responsibility |
|---|---|---|
| CLI | `main.py` | Argument parsing, mode dispatch, env loading |
| Agent | `agent/survey_designer.py` | KG → session.md → Harmonica session |
| Agent | `agent/results_ingestor.py` | Harmonica summary → KG entities/edges |
| Client | `harmonica/client.py` | Thin REST wrapper for Harmonica API v1 |
| Prompt | `agent/prompts/design_prompt.md` | Agent instruction doc loaded at import |

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

---

## Project Structure

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
| `create_session(topic, goal, prompt, questions, cross_pollination, summary_prompt, context, distribution)` | Returns session dict including `join_url` |
| `get_session(session_id)` | Status, participant count, metadata |
| `list_sessions(status, keyword)` | Filterable list |
| `update_session(session_id, **fields)` | PATCH arbitrary fields |
| `search_sessions(query)` | Keyword search |
| `get_responses(session_id, ...)` | Participant threads with filtering |
| `generate_summary(session_id, prompt)` | Triggers async synthesis |
| `get_summary(session_id)` | Summary text + themes |

---

## SurveyDesigner — `agent/survey_designer.py`

```python
build_survey_params(topic_query) -> dict
create_session(topic_query) -> dict
```

**Flow:**
1. `kg.search(topic_query, num_results=10)` → entities
2. `_write_session_md()` → writes `session.md` to cwd
3. `agents.sync(file_path="session.md")` → injects doc into agent context
4. `agents.chat(design_prompt.md)` → agent returns JSON with all session fields
5. Parse + return dict ready for `create_session(**params)`

**Prompt:** `agent/prompts/design_prompt.md` loaded once at import via `Path.read_text()`. Edit that file to tune agent output — no Python changes needed.

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
python main.py                              # interactive
python main.py --topic "QUERY"             # design + deploy session
python main.py --session SESSION_ID        # poll status
python main.py --session ID --ingest KG_ID # ingest summary into KG
```

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
- **`session.md` written to cwd** — should write to a temp path in production.
- **Ingest pinning** — pins entities found by post-sync KG search, not necessarily the newly created nodes. May miss nodes not yet indexed.

---

## Reference Links

| Resource | URL |
|---|---|
| Bonfires SDK | https://github.com/NERDDAO/bonfires-sdk |
| Harmonica MCP | https://github.com/harmonicabot/harmonica-mcp |
| Harmonica Chat (prompt patterns) | https://github.com/harmonicabot/harmonica-chat |
| Harmonica API base | https://app.harmonica.chat/api/v1 |
