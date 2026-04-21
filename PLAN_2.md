# Canon — Streamlit Frontend Plan

## Context
Canon's CLI pipeline (discover → design → create → monitor) has human review gates
between each step. A Streamlit multi-page app maps each step to a page, uses
`st.session_state` to carry selections forward, and calls existing agent classes
directly — no changes to backend code required.

---

## App Structure

```
canon/
├── app.py                     Home page — pipeline overview + quick status
├── app_utils.py               Shared client init (cached)
├── pages/
│   ├── 1_Discover.py          Step 1: query KG, generate topic suggestions
│   ├── 2_Design.py            Step 2: pick a topic, generate session designs
│   ├── 3_Create.py            Step 3: pick a design, deploy to Harmonica
│   ├── 4_Monitor.py           Step 4: poll session status + response count
│   └── 5_History.py           Browse all DB records (batches, topics, designs, sessions)
```

Streamlit's multi-page convention uses the `pages/` directory automatically —
each file becomes a sidebar nav item. The number prefix controls ordering.

---

## Page Specs

### `app.py` — Home

- Title + one-paragraph description of the pipeline
- Pipeline diagram (static Markdown, same as TECHNICAL_FLOW.md summary)
- Quick status table: last 5 topics, last 5 designs, last 3 sessions — pulled live
  from `db.list_topics()`, `db.list_designs()`, `db.list_sessions()`
- "Start here → Discover" button that navigates to page 1

---

### `pages/1_Discover.py` — Discover Topics

**Inputs:**
- Text input: `Query (leave blank for full KG scan)`
- Number input: `Variations (1–10)`, default 3
- Button: `Discover Topics`

**On click:**
- `st.spinner("Querying knowledge graph...")` wraps the `TopicAdvisor.discover_batch()` call
- Results displayed as `st.dataframe` with columns: ID, Topic, Format, Rationale, Batch
- User clicks a row → stores `selected_topic_id` in `st.session_state`
- `st.success("Topic #N selected — go to Design →")`

**Also shows:**
- Expander: `All stored topics` — `db.list_topics()` as a table, selectable
- Lets users pick a previously discovered topic without re-running discovery

---

### `pages/2_Design.py` — Design Session

**On load:**
- If `st.session_state.selected_topic_id` is set, pre-fills the topic selector
- Shows the selected topic details (topic text, format suggestion, batch)

**Inputs:**
- Select box: `Topic` — populated from `db.list_topics()`
- Number input: `Variations (1–5)`, default 3
- Button: `Generate Designs`

**On click:**
- `st.spinner("Designing session...")` wraps `SurveyDesigner.build_survey_params_from_topic()`
- Results as `st.dataframe`: ID, Topic, Goal (truncated), Template
- Clicking a row stores `selected_design_id` in `st.session_state`
- Expander per design: shows full `params_json` pretty-printed

**Also shows:**
- Expander: `All stored designs` for this topic — `db.list_designs(topic_id)`

---

### `pages/3_Create.py` — Create Session

**On load:**
- If `st.session_state.selected_design_id` is set, pre-selects it

**Inputs:**
- Select box: `Design` — populated from `db.list_designs()`
- Text input: `Template ID (optional override)`
- Button: `Create Harmonica Session`

**On click:**
- `st.spinner("Creating session...")` wraps `SurveyDesigner.create_session_from_design()`
- On success:
  - `st.success("Session created!")`
  - `st.code(join_url)` — copyable URL
  - `st.markdown(f"[Open session]({join_url})")` — clickable link
  - Saves `harmonica_session_id` to `st.session_state`

---

### `pages/4_Monitor.py` — Monitor Session

**Inputs:**
- Text input: `Harmonica Session ID` — pre-filled from `st.session_state` if set
- Button: `Poll Status`
- Ingest section:
  - Text input: `Kengram ID`
  - Button: `Ingest into KG`

**Poll display:**
- Status badge (active / complete / etc.)
- Response count
- `st.button("Refresh")` to re-poll

**Ingest display:**
- `st.spinner("Ingesting...")` wraps `ResultsIngestor.ingest()`
- Shows `entities_pinned` count on completion

---

### `pages/5_History.py` — History Browser

Three `st.tabs`: **Topics** | **Designs** | **Sessions**

- **Topics tab:** `db.list_topics()` as dataframe + expander per row showing
  the batch `context_text` (KG entities markdown)
- **Designs tab:** `db.list_designs()` as dataframe + expander per row showing
  pretty-printed `params_json`
- **Sessions tab:** `db.list_sessions()` as dataframe + join URLs as clickable links

---

## Shared Utilities — `app_utils.py`

```python
@st.cache_resource
def get_clients():
    """Initialize BonfiresClient + HarmonicaClient once per session."""
    load_dotenv()
    db.init()
    bonfire = BonfiresClient(
        api_key=os.environ["BONFIRE_API_KEY"],
        bonfire_id=os.environ["BONFIRE_ID"],
        agent_id=os.environ["BONFIRE_AGENT_ID"],
    )
    harmonica = HarmonicaClient()
    return bonfire, harmonica
```

`@st.cache_resource` ensures clients are created once and reused across reruns —
avoids re-initializing httpx connections and re-loading env vars on every interaction.

---

## State Flow Between Pages

```
session_state["selected_topic_id"]    set in Discover → read in Design
session_state["selected_design_id"]   set in Design   → read in Create
session_state["harmonica_session_id"] set in Create   → read in Monitor
```

Users can bypass session state by using the select boxes on each page directly —
session_state just pre-fills the selection for convenience.

---

## New Dependency

```
streamlit>=1.35
```

Add to `requirements.txt`. No other new dependencies — all agent/store code reused as-is.

---

## Files to Create

| File | Action |
|---|---|
| `app.py` | Home page |
| `app_utils.py` | Shared `get_clients()` with `@st.cache_resource` |
| `pages/1_Discover.py` | Discovery step |
| `pages/2_Design.py` | Design step |
| `pages/3_Create.py` | Create step |
| `pages/4_Monitor.py` | Monitor/ingest step |
| `pages/5_History.py` | History browser |
| `requirements.txt` | Add `streamlit>=1.35` |

No changes to any existing agent, store, or harmonica files.

---

## Run

```bash
streamlit run Create.py
```

---

## Verification

1. `streamlit run Create.py` — home page loads, quick status table shows DB records
2. Discover: enter "community governance", batch 3 → spinner → 3 topics in table
3. Select topic → navigate to Design → topic pre-selected in dropdown
4. Generate 3 designs → select one → navigate to Create → design pre-selected
5. Create session → join_url appears as copyable code + clickable link
6. Monitor: paste session ID → poll shows status + response count
7. History: all 3 tabs show correct DB records with expanders
