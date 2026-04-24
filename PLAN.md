# Canon — Next Steps

## Status
Core pipeline complete. Streamlit UI (Create + Explore) live. All consistency fixes from prior review applied.

---

## Track 1 — Immediate

### T1-1: Add `critical` field to session design

**Context:** The Harmonica `POST /sessions` API accepts a `critical` field — a directive to the facilitator about what is most important to extract from each participant. Distinct from `goal` (what the session is about) and `prompt` (the conversation script): `critical` shapes how the AI probes and follows up.

Example values:
- "Specific driving forces and restraining forces around the change, with concrete examples. Which forces are most amenable to influence?"
- "Each participant's direct lived experience — not opinions, but concrete examples from their own context."
- "Genuine engagement with how the participant arrived at their position, not just what it is."

**Files:**

| File | Change |
|---|---|
| `agent/prompts/design_prompt.md` | Add `critical` field — 1-3 sentence facilitator directive |
| `harmonica/client.py` | Add `critical: str \| None = None` param to `create_session()`, include in POST body |
| `pages/1_Explore.py` | Display `critical` in designs tab under goal |

No DB schema change needed — `critical` is stored in `params_json` and flows to the API automatically via `create_session_from_design(**params)`.

---

### T1-2: Facilitation Formats Reference Library

**Context:** The agent generates low-diversity facilitation prompts because it has no explicit knowledge of deliberation frameworks. A reference library synced to the agent before each design call gives it full awareness of available formats, enabling it to select and apply the right approach per topic.

**Architecture:** Local file `agent/data/facilitation_formats.md` — synced as a second `agents.sync()` call in `build_survey_params_from_topic()`. The design prompt directs the agent to select a format and apply its structure to the `prompt` field.

**Files:**

| File | Change |
|---|---|
| `agent/data/facilitation_formats.md` | **Create** — full reference library (56 formats across 8 categories) |
| `agent/survey_designer.py` | Load + sync formats file before design chat call |
| `agent/prompts/design_prompt.md` | Add format-selection instruction to `prompt` field |

**Note:** If Track 2 (BYOM proxy) succeeds, the pre-generated `prompt` becomes less critical — but the formats library remains useful as KG-encoded facilitation knowledge.

---

## Track 2 — Investigate: Bonfires as Harmonica's AI Provider (BYOM Proxy)

### Background

Harmonica's BYOM feature lets you replace its built-in AI facilitator with any OpenAI-compatible API endpoint — configured via Settings > AI Models with a base URL + API key.

**Bonfires does not expose an OpenAI-compatible endpoint natively.** But we can build a thin proxy that does.

### Architecture

```
Harmonica session (participant turn)
  → POST /v1/chat/completions  (proxy)
    → bonfire.agents.chat(message, graph_mode="adaptive")
      → Bonfires KG-connected AI
    ← response text
  ← OpenAI-format completion
  → Harmonica delivers facilitator message to participant
```

The proxy (`proxy.py`) is a small FastAPI service (~80 lines):
- Exposes `POST /v1/chat/completions` in OpenAI format
- Translates incoming message array to a Bonfires `agents.chat()` call
- Returns response as `choices[0].message.content`
- Run locally with ngrok for testing; deployed as a service for production

### Why This Matters

| Current Canon | BYOM Proxy Canon |
|---|---|
| KG context loaded once at design time | KG queried live every facilitator turn |
| Static pre-written facilitation script | Dynamic — Bonfires agent responds in context |
| 5-step pipeline | 3-step: discover → create → facilitate |
| Ingest post-session | Could append to KG during the session itself |

### Open Questions to Resolve

1. **Does Harmonica BYOM accept a self-hosted/custom base URL?** Docs say "OpenAI-compatible APIs" — implies yes, but needs verification.
2. **Does Harmonica require streaming?** (`text/event-stream` SSE) — if so, proxy must implement SSE relay.
3. **What does Harmonica send as the message payload?** Full conversation history? Just the latest turn? Determines how we reconstruct context.
4. **Does `bonfire.agents.chat()` maintain thread state across calls?** If stateless, proxy reconstructs context from full message history on every turn.
5. **Which `graph_mode`?** `"adaptive"` (read KG, no writes) vs `"append"` (write to KG during session).

### Implementation Plan

| Step | Description |
|---|---|
| 1 | Build `proxy.py` — FastAPI, `POST /v1/chat/completions` |
| 2 | Expose via ngrok locally |
| 3 | Configure Harmonica BYOM: base URL = ngrok URL, model = any string |
| 4 | Create a minimal test Harmonica session (no custom prompt) |
| 5 | Participate as test user — observe facilitator responses |
| 6 | Confirm KG context surfaces in facilitator messages |
| 7 | Evaluate: does this replace or complement the design pipeline? |

### Files to Create

| File | Description |
|---|---|
| `proxy.py` | FastAPI BYOM proxy server |
| `requirements.txt` | Add `fastapi`, `uvicorn` |

---

## Deferred

- **`template_id` registry**: Template IDs are opaque strings from the Harmonica web UI — no API to discover them. The 16 Harmonica templates correspond to the formats in our reference library. Revisit once real IDs are available. The `--template-id` CLI flag and UI override remain the mechanism.

---

## Assumptions (carried forward)

| # | Assumption |
|---|---|
| 1 | `template_id` references templates built in the Harmonica web UI; no GET /templates endpoint exists |
| 2 | The Bonfires KG agent can return multiple suggestions as a JSON array in a single call |
| 3 | No-query discovery uses `kg.get_latest_episodes(agent_id, limit)` — `kg.search()` requires non-empty string |
| 4 | `store/canon.db` path is configurable via `CANON_STORE_DIR` env var |
| 5 | Batch designs are N variations on the same topic, not N independent topics |
| 6 | `--topic` legacy flag is kept for backwards compatibility, not promoted |
