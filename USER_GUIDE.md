# Canon — User Guide

Canon is a CLI tool that bridges your Bonfires AI knowledge graph with Harmonica deliberation sessions. It helps you discover relevant topics from your KG, design structured facilitation sessions, deploy them, and feed the results back into the graph.

---

## Prerequisites

```bash
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and fill in all four required values:

```
BONFIRE_API_KEY=your_key
BONFIRE_ID=your_bonfire_id
BONFIRE_AGENT_ID=your_agent_id
HARMONICA_API_KEY=hm_live_...
```

---

## The 5-Step Workflow

### Step 1 — Discover Topics

Ask the KG what's worth deliberating on.

```bash
# Search by keyword
python main.py --discover "community governance"

# Generate 3 suggestions from one search
python main.py --discover "community governance" --batch 3

# Full KG scan (no keyword — uses latest episodes)
python main.py --discover --batch 3
```

Canon prints a table of topic suggestions with IDs, recommended formats (SWOT, SOAR, Gap Analysis, etc.), and a batch run ID.

---

### Step 2 — Review Topics

List what's been stored and pick a topic ID.

```bash
python main.py --list-topics
```

Output:
```
ID  Created              Topic                                   Format        Query
--  -------------------  --------------------------------------  ------------  ----------
1   2026-04-21 14:32:11  Establishing Core Community Values      SWOT          community ...
2   2026-04-21 14:32:11  Strategic Knowledge Sharing Practices   SOAR          community ...
3   2026-04-21 14:32:11  Barriers to Information Flow            Fishbone      community ...
```

---

### Step 3 — Design a Session

Generate Harmonica session parameters for a topic.

```bash
# Single design
python main.py --design 1

# Three design variations (you'll be prompted to pick one)
python main.py --design 1 --batch 3
```

Canon prints each design with its ID, topic title, and goal. If you ran `--batch 3`, it asks which design to mark as preferred — press Enter to skip.

```bash
# Review stored designs
python main.py --list-designs
python main.py --list-designs 1    # filtered to topic ID 1
```

---

### Step 4 — Create the Harmonica Session

Deploy a design to Harmonica.

```bash
python main.py --create 5

# Override the template if needed
python main.py --create 5 --template-id your_template_id
```

Output:
```
Creating session from design #5 (topic: 'Establishing Core Community Values') ...

Session created: abc12345
Participant URL:  https://app.harmonica.chat/session/abc12345
```

Share the participant URL with your group.

---

### Step 5 — Monitor and Ingest

Check on a session:

```bash
python main.py --session abc12345
```

After participants have responded, ingest the summary back into your KG:

```bash
python main.py --session abc12345 --ingest your_kengram_id
```

Output:
```
Ingesting session 'abc12345' into kengram 'your_kengram_id' ...
Entities pinned: 4
Kengram:         your_kengram_id
```

---

## Obsidian Vault

Every `--discover` and `--design` run updates an Obsidian vault at `store/vault/`.

**Setup:**
1. Open Obsidian → **Open folder as vault** → select `store/vault/`
2. Install the **Dataview** community plugin
3. Open `index.md` for live tables of all batches

**Manual refresh:**
```bash
python main.py --export-vault
```

The vault contains:
- `discovery/` — KG context and topic tables per discovery batch
- `design/` — session context and design tables per design batch
- `sessions/` — one file per created Harmonica session
- `index.md` — Dataview overview of everything

---

## Full Command Reference

| Command | Description |
|---|---|
| `--discover [QUERY]` | Suggest topics from KG (omit QUERY for full scan) |
| `--discover "QUERY" --batch N` | Generate N topic suggestions |
| `--list-topics` | Show all stored topics |
| `--design TOPIC_ID` | Design a session from a stored topic |
| `--design TOPIC_ID --batch N` | Generate N design variations |
| `--list-designs [TOPIC_ID]` | Show stored designs (all or by topic) |
| `--create DESIGN_ID` | Create Harmonica session from stored design |
| `--create DESIGN_ID --template-id ID` | Override template on create |
| `--session SESSION_ID` | Poll session status and response count |
| `--session ID --ingest KG_ID` | Ingest completed session into KG |
| `--export-vault` | Regenerate Obsidian vault from DB |
| `--topic "QUERY"` | (Legacy) Design + deploy in one step |

---

## Optional Environment Variables

| Variable | Default | Description |
|---|---|---|
| `HARMONICA_API_URL` | `https://app.harmonica.chat` | Override Harmonica base URL |
| `CANON_STORE_DIR` | `store/` (project directory) | Custom path for `canon.db` and vault |

---

## Tips

**Batch size:** Start with `--batch 3` for both discovery and design. Three options gives you enough variety without overwhelming the selection step.

**Format suggestions:** The KG agent recommends a discussion format (SWOT, SOAR, Gap Analysis, Force Field, Fishbone, Open Dialogue) based on the topic. These inform the session design prompt — you don't need to act on them directly.

**Sparse KG:** If `--discover` returns generic topics unrelated to your content, your KG may not have enough relevant episodes yet. Add content to Bonfires first, then re-run.

**Picking designs:** When running `--design --batch 3`, the CLI prompts you to mark one as preferred. This just sets a `selected` flag in the DB — it doesn't create the session. Run `--create` with any design ID, selected or not.

**Vault diffing:** Each `--discover` and `--design` run creates new files in the vault (named by date + topic slug), so you can track how suggestions evolve over time.
