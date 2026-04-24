# Canon — Technical Flow

This document traces the complete journey of data through Canon, from a search query
to a live Harmonica session, in plain terms.

---

## The Big Picture

Canon connects two external systems:

- **Bonfires AI** — a knowledge graph platform. It stores entities (concepts, people,
  organizations, topics) and the relationships between them. It also hosts an AI agent
  that can read and write to the graph.

- **Harmonica AI** — a deliberation session platform. It runs async facilitated
  conversations where an AI guides participants through structured questions and
  synthesizes the results.

Canon's job is to use what Bonfires knows to design what Harmonica runs.

---

## What a Knowledge Graph Entity Looks Like

When Canon asks Bonfires for context, it gets back a list of **entities** — structured
objects representing things the KG knows about:

```json
{
  "name": "Community Trust Building",
  "summary": "The process by which communities develop shared confidence in governance
               structures through transparency, participation, and accountability.",
  "labels": ["concept", "governance", "social-capital"],
  "uuid": "3f9a1c2b-..."
}
```

Each entity is a node in the graph. The KG may contain dozens or hundreds of them,
covering different aspects of your domain. `kg.search()` returns the ones most
relevant to your query.

---

## Step-by-Step: Discovery Flow

### `python main.py --discover "community governance" --batch 3`

---

### 1. KG Search

```python
kg.search("community governance", num_results=20)
```

Canon sends the query to the Bonfires API. Bonfires searches its graph and returns
the 20 most relevant entities. If no query is given (`--discover` with no argument),
Canon calls `kg.get_latest_episodes()` instead — which returns the most recently added
content to the graph, giving a broad current-state scan rather than a targeted search.

**Result:** a list of entity dicts (name, summary, labels, uuid).

---

### 2. Entities → Markdown

```python
_entities_to_md(entities)
```

The raw entity list is converted into a **readable Markdown document**. Each entity
becomes a heading with its labels and summary as prose:

```markdown
## Community Trust Building
**Labels:** concept, governance, social-capital

The process by which communities develop shared confidence in governance structures
through transparency, participation, and accountability.

## Decision-Making Frameworks
**Labels:** process, governance

Structured approaches to collective decision-making that balance representation...
```

Why Markdown and not raw JSON? The Bonfires agent is a language model. It reads and
reasons over prose far more effectively than structured data. Formatting entities as
a document — rather than passing the raw JSON dict — produces noticeably better output.

**Result:** a string of Markdown, stored as `entities_md`.

---

### 3. Inject Context into Agent Memory

```python
# Written to a temp file first, because agents.sync() requires a file path
with tempfile.NamedTemporaryFile(mode="w", suffix=".md") as tmp:
    tmp.write(entities_md)
    bonfire.agents.sync(file_path=tmp.name, title="Discovery Context")
```

`agents.sync()` uploads the Markdown document into the Bonfires agent's context —
essentially handing the agent a briefing document before asking it a question.

The temp file is deleted immediately after sync.

---

### 4. Ask the Agent for Topic Suggestions

```python
formats_content = Path("agent/data/facilitation_formats.md").read_text()
formats_block = "\n\n---\n# Facilitation Formats Reference Library\n\n" + formats_content + "\n---\n\n"

prompt = discovery_prompt_with_N_replaced + formats_block
bonfire.agents.chat(message=prompt, graph_mode="adaptive")
```

The chat message has two parts:

1. **Discovery prompt** — instructs the agent: *"Identify 3 deliberation topics from
   the context, return a JSON array. For each topic, choose a `format_suggestion` from
   the formats in the reference library appended below."*

2. **Formats library** — the full contents of `facilitation_formats.md`, embedded
   inline. The library lists 20 complete facilitation formats with selector descriptions.
   Embedding it inline (rather than relying on a prior `sync()` call) ensures the agent
   definitely sees it.

`graph_mode="adaptive"` tells Bonfires the agent should read the graph for context
but not write new nodes back — this is a read-only reasoning step.

The agent returns a JSON array where each topic includes a `format_suggestion` — the
name of the facilitation format best suited to it, chosen from the library:

```json
[
  {
    "topic": "Establishing Core Community Values",
    "rationale": "The KG shows recurring tension between inherited norms and emerging
                  community expectations — deliberation could surface alignment.",
    "format_suggestion": "Driver Mapping"
  },
  {
    "topic": "Strategic Knowledge Sharing Practices",
    "rationale": "Multiple entities reference siloed expertise with no bridging...",
    "format_suggestion": "Force Field Analysis"
  },
  {
    "topic": "Barriers to Information Flow",
    "rationale": "...",
    "format_suggestion": "Iceberg Model"
  }
]
```

**Result:** 3 topic suggestions grounded in actual KG content, each with a format name.

---

### 5. Store to Database

```python
batch_id = db.insert_batch(
    batch_run_id="3efac758",
    type="discovery",
    query="community governance",
    context_text=entities_md,
    raw_response=raw_json_text,
)
for suggestion in suggestions:
    db.insert_topic(batch_id, topic, format_suggestion)
```

The batch metadata is stored once in `batches`. Each topic suggestion gets its own
row in `topics`, linked by `batch_id`.

**Result:** 1 batch row + 3 topic rows in SQLite. Each topic has an integer ID.

---

### 6. Export to Obsidian Vault

Canon writes two Markdown files to `store/vault/discovery/`:

- `...-community-governance-context.md` — the KG entities document with YAML frontmatter
- `...-community-governance-topics.md` — a table of the 3 topic suggestions

---

## Step-by-Step: Design Flow

### `python main.py --design 1 --batch 3`

The human has reviewed the topic table, chosen topic ID 1, and wants 3 design
variations.

---

### 1. DB Lookup

```python
topic_row = db.get_topic(topic_id=1)
# Returns: { topic: "Establishing Core Community Values",
#            format_suggestion: "Driver Mapping", ... }
```

Canon reads the stored topic from SQLite. No network call yet.

---

### 2. KG Search (again, targeted)

```python
kg.search("Establishing Core Community Values", num_results=10)
```

A new, more focused KG search using the specific topic title.

---

### 3. Build session.md

```python
_build_session_md_content(topic_query, entities, format_suggestion)
```

The entities are formatted into a Markdown document with the format suggestion included:

```markdown
# Session Context: Establishing Core Community Values

**Recommended format:** Driver Mapping

## Community Trust Building
...
```

---

### 4. Inject Context + Ask for Designs

```python
bonfire.agents.sync(file_path="session.md")

formats_block = "\n\n---\n# Facilitation Formats Reference Library\n\n" + formats_content + "\n---\n\n"

topic_anchor = 'The deliberation topic is: "Establishing Core Community Values"\n
                Recommended format: Driver Mapping\n\n'

prompt = topic_anchor + design_prompt + formats_block + batch_suffix_n3
bonfire.agents.chat(message=prompt, graph_mode="adaptive")
```

The prompt has four parts:

1. **Topic anchor** — explicitly states the topic and the recommended format at the top.
   Guards against the agent drifting to a different topic.

2. **Design prompt** — instructs the agent to produce a complete session design as JSON
   with fields: `topic`, `goal`, `context`, `critical`, `format`, `summary_prompt`.
   The `format` field is the *name* of the chosen facilitation format — not the script
   itself. The agent does not write facilitation prompts.

3. **Formats library** — the full `facilitation_formats.md` embedded inline, so the
   agent can see all 20 formats and make an informed selection by name.

4. **Batch suffix** (when n > 1) — *"Generate exactly 3 variations for this topic.
   Each should differ in framing, emphasis, or facilitation angle."* This is why
   a batch of 3 designs will typically yield format diversity: the agent interprets
   "vary the facilitation angle" as choosing different formats for different variations.
   The first variation usually follows the recommended format; subsequent ones explore
   alternatives.

The agent returns 3 JSON objects, each with a `format` field containing a name:

```json
[
  { "topic": "...", "goal": "...", "context": "...", "critical": "...",
    "format": "Driver Mapping", "summary_prompt": "..." },
  { ..., "format": "Force Field Analysis", ... },
  { ..., "format": "Stakeholder Analysis", ... }
]
```

Note: no `prompt` field. The facilitation script is not generated here.

---

### 5. Store Designs to DB

```python
batch_id = db.insert_batch(type="design", query=topic_query, ...)
for params in designs:
    db.insert_design(batch_id, topic_id=1, params_json=json.dumps(params))
```

Each design row stores the full agent JSON blob in `params_json`. The `format` name
is stored there too. The facilitation script is resolved later, at create time.

**Result:** 3 design rows in SQLite.

---

## Step-by-Step: Create Flow

### `python main.py --create 5`

---

### 1. DB Lookup

```python
design = db.get_design(design_id=5)
params = json.loads(design["params_json"])
```

The full session design is read from SQLite — no KG call, no agent call.

---

### 2. Resolve Facilitation Script

```python
format_name = params.pop("format", "")   # e.g. "Driver Mapping"
loaded = _load_format_prompt(format_name)
if loaded:
    params["prompt"] = loaded
```

`_load_format_prompt()` reads `facilitation_formats.md`, finds the section whose
`## heading` contains the format name, and returns everything after the
`### Facilitation Prompt` marker — the complete, verbatim facilitation script.

This is injected directly as `params["prompt"]` before the API call. The script
is never generated by the AI — it comes from the library file unchanged.

If the format name doesn't match any library entry (e.g. the agent returned an
unrecognised name), `prompt` is omitted and Harmonica uses its own default facilitator.

---

### 3. Inject Hardcoded Fields

```python
params["questions"] = INTAKE_QUESTIONS   # Name, Wallet Address, Email Address
params["cross_pollination"] = cross_pollination   # True by default
```

Intake questions are always the same — not a per-topic design decision.
`cross_pollination` is a caller-controlled boolean, defaulting to True.

---

### 4. POST to Harmonica

```python
harmonica.create_session(
    topic="Establishing Core Community Values",
    goal="...",
    context="...",
    critical="...",
    prompt="<verbatim Driver Mapping facilitation script>",
    questions=[{"text": "Name"}, {"text": "Wallet Address"}, {"text": "Email Address"}],
    cross_pollination=True,
    summary_prompt="...",
)
```

Harmonica provisions the session and returns a `join_url`.

---

### 5. Store Session + Print URL

```python
db.insert_session(design_id=5, harmonica_session_id="abc12345", join_url=url)
db.mark_selected(design_id=5)
```

The Harmonica session ID and join URL are stored. The URL is printed for sharing.

---

## Step-by-Step: Ingest Flow

### `python main.py --session abc12345 --ingest my_kengram_id`

After participants have responded, Canon feeds the results back into the KG.

---

### 1. Fetch Summary from Harmonica

```python
harmonica.get_summary("abc12345")
# Returns: { "summary": "Participants identified three core barriers..." }
```

---

### 2. Extract Entities via Agent (write mode)

```python
bonfire.agents.chat(
    message=ingest_prompt.format(summary_text=summary),
    graph_mode="append"
)
```

`graph_mode="append"` means the agent **only adds** new nodes and edges, never
overwrites existing ones.

---

### 3. Push Summary as Episode

```python
bonfire.agents.sync(message=summary_text)
```

The full summary text is pushed to the KG as a timestamped episode, making session
results searchable in future KG queries.

---

### 4. Pin to Kengram

```python
kg_results = bonfire.kg.search(summary_text[:200], num_results=5)
for entity in kg_results["entities"]:
    bonfire.kengrams.pin(kengram_id, entity["uuid"])
```

Entities surfaced by the summary are pinned to the specified kengram — a curated,
queryable collection of KG nodes.

---

## The Complete Data Flow

```
DISCOVER
  query string
      │
      ▼
  kg.search() ──────────────── Bonfires API returns relevant graph entities
      │ list of {name, summary, labels, uuid}
      ▼
  _entities_to_md() ─────────── formats entities as readable Markdown
      │ entities_md string
      ▼
  agents.sync(tempfile) ─────── loads KG document into agent context
      │
      ▼
  agents.chat(discovery_prompt + formats_library)
      │ agent sees: KG context + 20 facilitation formats with selector descriptions
      │ returns: [{topic, rationale, format_suggestion}, ...]
      ▼
  db.insert_batch() + db.insert_topic() × N ── stored to SQLite
      │
      ▼
  export_vault() ──────────────── writes 2 .md files to store/vault/discovery/

         ↓ human reviews --list-topics, picks a topic ID

DESIGN
  topic_id (from DB)
      │
      ▼
  db.get_topic() ──────────────── read stored topic + format_suggestion
      │
      ▼
  kg.search(topic) ────────────── targeted KG search for design context
      │ entities
      ▼
  _build_session_md_content() ─── Markdown doc with format suggestion
      │ session.md
      ▼
  agents.sync(session.md) ─────── load design context into agent
      │
      ▼
  agents.chat(topic_anchor + design_prompt + formats_library [+ batch_suffix])
      │ agent sees: topic anchor + design instructions + 20 formats with full prompts
      │ returns: [{topic, goal, context, critical, format, summary_prompt}, ...]
      │          note: no 'prompt' field — agent returns format NAME only
      ▼
  db.insert_batch() + db.insert_design() × N ── stored to SQLite

         ↓ human reviews --list-designs, picks a design ID

CREATE
  design_id (from DB)
      │
      ▼
  db.get_design() ──────────────── read stored design params
      │ params_json → format name (e.g. "Driver Mapping")
      ▼
  _load_format_prompt(format_name) ── read verbatim script from formats library
      │ complete facilitation prompt text
      ▼
  inject: params["prompt"] = verbatim_script
  inject: params["questions"] = [Name, Wallet Address, Email Address]
  inject: params["cross_pollination"] = True
      │
      ▼
  harmonica.create_session(**params) ── POST to Harmonica API
      │ {join_url, session_id, ...}
      ▼
  db.insert_session() ──────────── store session record
      │
      ▼
  join_url ──────────────────────── printed to terminal, shared with participants

         ↓ participants respond in Harmonica web app

INGEST
  session_id + kengram_id
      │
      ▼
  harmonica.get_summary() ─────── GET summary from Harmonica
      │ summary text
      ▼
  agents.chat(ingest_prompt, graph_mode="append") ── extract + write entities to KG
      │
      ▼
  agents.sync(summary_text) ───── push summary as KG episode
      │
      ▼
  kg.search(summary[:200]) ─────── find newly surfaced entity UUIDs
      │
      ▼
  kengrams.pin(kengram_id, uuid) × N ── pin entities to kengram
```

---

## Key Design Principles

**The agent is the intelligence layer, not the content layer.** Canon uses the Bonfires
agent to read real KG content and make judgment calls (which topic? which format?). But
it does not ask the agent to write facilitation scripts — that's the library's job. The
quality of topic and format selection scales with the quality of your KG.

**Context is passed as documents, not data.** Entities are formatted as Markdown prose
before being synced to the agent. Language models reason better over readable text than
raw JSON structures.

**Critical context is embedded inline, not just synced.** The facilitation formats
library is appended directly to the chat message rather than relying on `agents.sync()`
alone. Synced documents may or may not surface in the agent's active context; inline
content always does.

**graph_mode controls whether the KG changes.**
- `"adaptive"` — agent reads graph for context, may suggest but does not write
- `"append"` — agent actively writes new nodes and edges, never overwrites existing ones

**Human review happens between pipeline steps.** The agents never automatically promote
a topic to a design or a design to a session. The human picks the IDs.

**Format selection and prompt injection are separate concerns.** The agent picks a
format name (a judgment call). Python injects the verbatim script (a deterministic
lookup). LLMs cannot reliably copy long text verbatim, so we don't ask them to.

**Context is stored once per batch.** All N topics in one `--batch 3` run share the
same KG context. Storing it in `batches` and linking by `batch_id` avoids N copies
of identical data.
