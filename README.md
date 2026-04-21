# Canon

Autonomous bridge between a [Bonfires AI](https://github.com/NERDDAO/bonfires-sdk) knowledge graph and [Harmonica AI](https://github.com/harmonicabot/harmonica-mcp) deliberation sessions. A CLI pipeline queries the KG for topic context, designs structured facilitation sessions, deploys them to Harmonica, and — after participants respond — ingests the summary back into the KG as new entities and relationships.

Replaces a manual 10-step `harmonica-chat` session design process.

---

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in BONFIRE_API_KEY, BONFIRE_ID, BONFIRE_AGENT_ID, HARMONICA_API_KEY
python main.py --discover "your topic" --batch 3
```

---

## CLI Usage

| Command | What it does |
|---|---|
| `python main.py --discover [QUERY]` | Query KG for topic suggestions (omit QUERY for full KG scan) |
| `python main.py --discover "QUERY" --batch N` | Generate N topic suggestions |
| `python main.py --list-topics` | Show all stored topic suggestions |
| `python main.py --design TOPIC_ID` | Generate session design from stored topic |
| `python main.py --design TOPIC_ID --batch N` | Generate N design variations, prompts to select one |
| `python main.py --list-designs [TOPIC_ID]` | Show stored designs (all or filtered by topic) |
| `python main.py --create DESIGN_ID` | Create Harmonica session from stored design |
| `python main.py --create DESIGN_ID --template-id ID` | Override template ID on create |
| `python main.py --session SESSION_ID` | Poll session status and response count |
| `python main.py --session ID --ingest KG_ID` | Ingest completed session into KG |
| `python main.py --export-vault` | Regenerate Obsidian vault from DB |
| `python main.py --topic "QUERY"` | (Legacy) Design + deploy in one step |

---

## Architecture

### 5-Step Pipeline

```
[Step 1 — Discover]
TopicAdvisor.discover_batch(query, n)
  kg.search(query) or kg.get_latest_episodes()  → entities markdown
  agents.sync(tempfile) → agents.chat(discovery_prompt.md)
  → N suggestions stored: batches + topics tables

[Step 2 — Review]  ← human picks topic ID from --list-topics

[Step 3 — Design]
SurveyDesigner.build_survey_params_from_topic(topic_id, n)
  DB lookup → kg.search(topic) → session.md
  agents.sync(session.md) → agents.chat(design_prompt.md)
  → N design variations stored: batches + designs tables

[Step 4 — Create]
SurveyDesigner.create_session_from_design(design_id)
  DB lookup → harmonica.create_session(**params)
  → join_url returned + stored in sessions table

[Step 5 — Ingest]
ResultsIngestor.ingest(session_id, kengram_id)
  harmonica.get_summary() → agents.chat(ingest_prompt, graph_mode="append")
  → kengrams.pin() for each surfaced entity
```

### Component Layers

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

### Project Structure

```
canon/
├── harmonica/
│   ├── __init__.py
│   └── client.py                    REST wrapper — sessions, responses, summaries
├── agent/
│   ├── __init__.py
│   ├── prompts/
│   │   ├── design_prompt.md         session design instruction (edit to tune output)
│   │   └── discovery_prompt.md      topic discovery instruction (edit to tune output)
│   ├── survey_designer.py           DB topic → KG → session.md → Harmonica session
│   ├── topic_advisor.py             KG scan → N topic suggestions
│   └── results_ingestor.py          Harmonica summary → KG entities/edges
├── store/
│   ├── __init__.py
│   ├── db.py                        SQLite — batches/topics/designs/sessions
│   ├── vault.py                     Obsidian vault export
│   └── vault/                       generated — open in Obsidian
│       ├── discovery/
│       ├── design/
│       ├── sessions/
│       └── index.md
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

## Obsidian Vault

`store/vault/` is a valid Obsidian vault — open the folder directly in Obsidian.

1. Open Obsidian → **Open folder as vault** → select `store/vault/`
2. Install the **Dataview** community plugin
3. Open `index.md` to see live tables of all discovery and design batches

The vault is regenerated automatically after `--discover` and `--design` runs.  
Manual refresh: `python main.py --export-vault`

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
- **Ingest pinning** — pins entities found by a post-sync KG search, not necessarily the newly created nodes. May miss entities not yet indexed.
