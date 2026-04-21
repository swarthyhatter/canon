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

`agents.sync()` uploads the Markdown document into the **Bonfires agent's context
window** — essentially handing the agent a briefing document before asking it a
question. The agent can now reference the KG content in its response.

Think of it as: *"Here is what we know. Now, given this, what should we deliberate on?"*

The temp file is deleted immediately after sync.

**Result:** the agent has the KG entities loaded as a readable document.

---

### 4. Ask the Agent for Topic Suggestions

```python
prompt = discovery_prompt.md  # with <N> replaced by 3
bonfire.agents.chat(message=prompt, graph_mode="adaptive")
```

Canon sends the `discovery_prompt.md` instructions to the agent. The agent now has
two things in its context:

1. The KG entities document (just synced)
2. The instructions: *"Identify 3 valuable deliberation topics from this content,
   return them as a JSON array"*

`graph_mode="adaptive"` tells Bonfires that the agent should **read** the graph for
context but **not write** new nodes back — this is a read-only reasoning step.

The agent returns a JSON array:

```json
[
  {
    "topic": "Establishing Core Community Values",
    "rationale": "The KG shows recurring tension between inherited norms and emerging
                  community expectations — deliberation could surface alignment.",
    "format_suggestion": "SWOT",
    "template_id": null
  },
  {
    "topic": "Strategic Knowledge Sharing Practices",
    "rationale": "Multiple entities reference siloed expertise with no bridging...",
    "format_suggestion": "SOAR",
    "template_id": null
  },
  {
    "topic": "Barriers to Information Flow",
    "rationale": "...",
    "format_suggestion": "Fishbone",
    "template_id": null
  }
]
```

**Result:** 3 topic suggestions grounded in actual KG content.

---

### 5. Store to Database

```python
batch_id = db.insert_batch(
    batch_run_id="3efac758",
    type="discovery",
    query="community governance",
    context_text=entities_md,    # the Markdown document
    raw_response=raw_json_text,  # the agent's raw output
)
for suggestion in suggestions:
    db.insert_topic(batch_id, topic, format_suggestion, template_id)
```

The batch metadata (context, raw response) is stored **once** in the `batches` table.
Each individual topic suggestion gets its own row in `topics`, linked back by
`batch_id`. Storing context at the batch level avoids repeating the same KG document
once per topic — all 3 suggestions came from the same KG call and share the same context.

**Result:** 1 batch row + 3 topic rows in SQLite. Each topic has an integer ID.

---

### 6. Export to Obsidian Vault

```python
export_vault()
```

Canon writes two Markdown files to `store/vault/discovery/`:

- `2026-04-21-3efac758-community-governance-context.md` — the KG entities document
  with YAML frontmatter for Dataview
- `2026-04-21-3efac758-community-governance-topics.md` — a table of the 3 topic
  suggestions plus the agent's raw JSON response

The filename includes `batch_run_id` so two runs with the same query on the same day
never overwrite each other.

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
#            format_suggestion: "SWOT", batch_run_id: "3efac758", ... }
```

Canon reads the stored topic from SQLite. No network call yet.

---

### 2. KG Search (again, targeted)

```python
kg.search("Establishing Core Community Values", num_results=10)
```

A new, more focused KG search using the specific topic title. This returns entities
most relevant to the design — narrower and more targeted than the discovery search.

---

### 3. Build session.md

```python
_build_session_md_content(topic_query, entities, format_suggestion)
```

The entities are formatted into a Markdown document again, this time with the
format suggestion included at the top:

```markdown
# Session Context: Establishing Core Community Values

**Recommended format:** SWOT

## Community Trust Building
**Labels:** concept, governance

...
```

This document becomes the agent's briefing for session design.

---

### 4. Inject Context + Ask for Designs

```python
bonfire.agents.sync(file_path="session.md")

topic_anchor = 'The deliberation topic is: "Establishing Core Community Values"\n
                Recommended format: SWOT\n\n'

prompt = topic_anchor + design_prompt.md + batch_suffix_with_N_3
bonfire.agents.chat(message=prompt, graph_mode="adaptive")
```

The prompt has three parts, concatenated:

1. **Topic anchor** — explicitly states the topic at the top of the message. This
   is a guard against the agent drifting to a different topic if the KG context
   contains many competing ideas.

2. **design_prompt.md** — the main instruction: *"Produce a complete Harmonica session
   design as a JSON object with these fields: topic, goal, context, prompt, questions,
   cross_pollination, summary_prompt"*

3. **Batch suffix** (when n > 1) — *"Generate exactly 3 variations for this same topic.
   Return a JSON array of 3 objects."*

The agent returns 3 complete session designs as a JSON array. Each design is a
fully-specified Harmonica session — not a summary, but a production-ready facilitation
script with intake questions, a facilitator prompt, and a synthesis directive.

---

### 5. Store Designs to DB

```python
batch_id = db.insert_batch(type="design", query=topic_query, ...)
for params in designs:
    db.insert_design(batch_id, topic_id=1, params_json=json.dumps(params))
```

Same pattern as discovery: one batch row owns the shared context, each design
variation gets its own row linked by `batch_id` and `topic_id`.

**Result:** 3 design rows in SQLite. Human is prompted to mark a preferred one.

---

## Step-by-Step: Create Flow

### `python main.py --create 5`

---

### 1. DB Lookup

```python
design = db.get_design(design_id=5)
params = json.loads(design["params_json"])
```

The full session design is read from SQLite — no KG call, no agent call. Everything
needed was stored at design time.

---

### 2. POST to Harmonica

```python
harmonica.create_session(
    topic="Establishing Core Community Values",
    goal="Understand what residents feel is missing...",
    prompt="You are a facilitator running a short async session...",
    questions=[{"text": "What's your name?"}, {"text": "Your role?"}],
    cross_pollination=True,
    summary_prompt="Summarize the key trust barriers identified.",
)
```

`HarmonicaClient` makes a single POST request to
`https://app.harmonica.chat/api/v1/sessions`. Harmonica provisions the session:
sets up the AI facilitator with the exact prompt Canon wrote, configures the intake
questions, and returns a response containing a `join_url`.

---

### 3. Store Session + Print URL

```python
db.insert_session(design_id=5, harmonica_session_id="abc12345", join_url=url)
db.mark_selected(design_id=5)
```

The Harmonica session ID and join URL are stored in the `sessions` table. The design
is flagged as selected. The URL is printed to the terminal for sharing.

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

The agent is given the session summary and instructed to extract entities and
relationships, then write them to the KG. `graph_mode="append"` is critical here —
it means the agent **only adds** new nodes and edges, never overwrites existing ones.

---

### 3. Push Summary as Episode

```python
bonfire.agents.sync(message=summary_text)
```

The full summary text is pushed to the KG as an **episode** — a timestamped document
attached to the graph. This makes the session results searchable in future KG queries.

---

### 4. Pin to Kengram

```python
kg_results = bonfire.kg.search(summary_text[:200], num_results=5)
for entity in kg_results["entities"]:
    bonfire.kengrams.pin(kengram_id, entity["uuid"])
```

A kengram is a curated collection of KG entities. Canon searches for entities
surfaced by the summary and pins them to the specified kengram, making the deliberation
results part of a persistent, queryable collection.

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
  agents.sync(tempfile) ─────── loads document into agent context window
      │
      ▼
  agents.chat(discovery_prompt) ← agent reads KG briefing + instructions
      │ JSON array: [{topic, rationale, format_suggestion}, ...]
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
  db.get_topic() ──────────────── read stored topic (no network call)
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
  agents.chat(topic_anchor + design_prompt + batch_suffix)
      │ JSON array: [{topic, goal, prompt, questions, ...}, ...]
      ▼
  db.insert_batch() + db.insert_design() × N ── stored to SQLite

         ↓ human reviews --list-designs, picks a design ID

CREATE
  design_id (from DB)
      │
      ▼
  db.get_design() ──────────────── read stored design (no network call)
      │ params_json
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

**The agent is the intelligence layer.** Canon does not generate session designs
programmatically. It uses the Bonfires agent — a language model with access to your KG
— to read real content and write real facilitation scripts. The quality of output
scales with the quality of your KG.

**Context is passed as documents, not data.** Entities are formatted as Markdown prose
before being synced to the agent. Language models reason better over readable text than
raw JSON structures.

**graph_mode controls whether the KG changes.**
- `"adaptive"` — agent reads graph for context, may suggest but does not write
- `"append"` — agent actively writes new nodes and edges, never overwrites existing ones

**Human review happens between pipeline steps.** The agents never automatically
promote a topic to a design or a design to a session. The human picks the IDs. Canon
is a tool for the human, not an autonomous loop.

**Context is stored once per batch.** All N topics in one `--discover --batch 3` run
share the same KG context (same search, same entities). Storing it in the `batches`
table and linking topics by `batch_id` avoids storing 3 copies of identical data.
