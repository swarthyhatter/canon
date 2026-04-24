# How Canon Works — Plain English Explainer

---

## The One-Line Version

Canon reads your community's knowledge graph, uses it to design structured group conversations, and sends those conversations to a platform where participants respond asynchronously — then feeds the results back into the knowledge graph.

---

## The Two Systems Canon Connects

**Bonfires** is a knowledge graph. Think of it as a structured memory for your community — a database of concepts, topics, people, and relationships that your community has built up over time. It also has an AI agent that can read this graph and answer questions based on what it knows.

**Harmonica** is a deliberation platform. You create a "session" there — a structured conversation with a clear topic, goal, and facilitation script. Harmonica's AI facilitates the conversation one-on-one with each participant, asking follow-up questions, and at the end synthesizes everyone's input into a summary.

Canon's job: take what Bonfires knows, and use it to design what Harmonica runs.

---

## The Five Steps

### Step 1 — Discover: What Should We Deliberate On?

You give Canon a keyword (or nothing, for a broad scan). Canon searches the knowledge graph for relevant content, then asks the Bonfires AI: *"Given everything in this graph, what topics are most worth deliberating on right now?"*

The AI returns a list of topic suggestions. Each one includes:
- A topic title
- A one-line rationale grounded in the KG content
- A recommended **facilitation format** — the type of structured conversation best suited to the topic (e.g. Driver Mapping, Force Field Analysis, Retrospective)

You browse the suggestions and pick one to move forward with.

---

### Step 2 — Design: How Should We Structure the Conversation?

You give Canon the topic ID you chose. Canon searches the knowledge graph again, this time with more focus, to get the most relevant context for that specific topic. It then asks the Bonfires AI to design a full session.

The AI returns a design with:
- A refined topic title and goal
- A context summary for the facilitator
- A **critical** directive — what the facilitator must prioritize extracting from each participant (e.g. "surface concrete driving forces with specific evidence, not general opinions")
- A **format** selection — the name of the facilitation format chosen from Canon's library of 20 pre-written approaches

If you ask for multiple variations (`--batch 3`), you'll typically get one design using the recommended format from discovery, and two more using different formats. This happens naturally because Canon instructs the AI to vary the facilitation angle across variations — giving you real options rather than three near-identical designs.

---

### Step 3 — Create: Deploy the Session

You pick a design. Canon:

1. Looks up the chosen format name in `agent/data/facilitation_formats.md` — a library of 20 complete, pre-written facilitation scripts
2. Copies that script verbatim into the session
3. Adds hardcoded intake questions (Name, Wallet Address, Email) and enables cross-pollination
4. Sends everything to the Harmonica API

Harmonica provisions the session and returns a participant URL.

**Why pre-written scripts?** The facilitation prompts in the library were carefully authored for each format. Asking an AI to write a fresh script every time introduces unpredictability. Instead, the AI selects which format fits (a judgment call it's good at), and Canon handles the script injection (a deterministic lookup). The AI picks the recipe; Canon measures the ingredients.

---

### Step 4 — Facilitate: Participants Respond

You share the participant URL. Each participant has a private 1:1 conversation with Harmonica's AI facilitator, guided by the script Canon provided. They can respond at their own pace — Harmonica is async.

Canon doesn't do anything during this phase. Harmonica handles everything.

---

### Step 5 — Ingest: Feed Results Back into the KG

After participants have responded, you tell Canon to ingest the session. Canon:

1. Fetches Harmonica's synthesized summary of all participant responses
2. Sends it to the Bonfires AI with instructions to extract entities and relationships and write them to the knowledge graph
3. Pushes the full summary as a timestamped episode in the graph
4. Pins the most relevant surfaced entities to a kengram (a curated collection)

The deliberation results become part of the knowledge graph — available for the next discovery run, building up the community's collective knowledge over time.

---

## The Facilitation Formats Library

`agent/data/facilitation_formats.md` contains 20 complete facilitation approaches:

| Category | Formats |
|---|---|
| Understanding change | Driver Mapping, Force Field Analysis, Three Horizons, Backcasting |
| Strengths and strategy | Appreciative Inquiry, SWOT Analysis, Pre-mortem |
| Complexity and systems | Cynefin Sensemaking, Iceberg Model, Scenario Planning |
| People and stakeholders | Stakeholder Analysis, Empathy Mapping, Jobs to Be Done |
| Learning and review | Retrospective, After Action Review, Change Readiness Assessment |
| Process and impact | Theory of Change, Impact Assessment |
| Creative | Dragon Dreaming |
| Multi-angle | Six Thinking Hats |

Each entry has:
- A **selector description** (one line, for the AI to choose the right format)
- A **complete facilitation prompt** — a multi-step script with specific probing questions, ready to use verbatim

---

## What the AI Does vs. What Canon Does

| Task | Who does it | Why |
|---|---|---|
| Identify relevant KG topics | Bonfires AI | Requires reading and reasoning over graph content |
| Recommend a facilitation format | Bonfires AI | Judgment call based on topic type |
| Write topic goal, context, critical | Bonfires AI | Requires understanding the specific topic |
| Write the facilitation script | **Canon (library lookup)** | Pre-written scripts are higher quality and consistent |
| Select intake questions | **Canon (hardcoded)** | Always the same — not a per-topic decision |
| Run the facilitation conversation | Harmonica AI | That's Harmonica's job |
| Extract entities from results | Bonfires AI | Graph write access required |

---

## The Web UI

`streamlit run ui/Create.py` opens a browser-based wizard with two pages:

**Create** — walks you through the five steps visually: discover topics, generate designs, create a session, monitor responses, and ingest results.

**Explore** — browse everything stored in the database: all topics (with KG context), all designs (with format, goal, critical directive, and facilitation script), and all sessions (with participant URLs).

---

## A Note on Format Diversity in Batch Designs

When you generate 3 design variations from one topic, you'll typically see different formats across the three designs. This is intentional: Canon tells the AI to "vary the facilitation angle" across variations. The AI interprets this as format variety — so instead of three slightly different versions of the same approach, you get three genuinely different ways of running the same deliberation. The first variation usually follows the format recommended at discovery; the others explore alternatives.

---

## The Full Loop

```
Your community's knowledge
         │
         ▼
   [Bonfires KG]
         │
         │  Canon reads the graph
         ▼
   Topic suggestions
         │
         │  You pick a topic
         ▼
   Session designs (format + goal + critical)
         │
         │  You pick a design
         ▼
   Canon injects verbatim facilitation script
         │
         ▼
   [Harmonica session]
         │
         │  Participants respond
         ▼
   Synthesized summary
         │
         │  Canon ingests results
         ▼
   [Bonfires KG] ← richer than before
```

Each cycle makes the knowledge graph more complete, which makes future topic discovery
more grounded, which makes future sessions more relevant.
