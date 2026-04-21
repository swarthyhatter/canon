import json
import re
from pathlib import Path

from . import db

_DEFAULT_VAULT = Path(__file__).parent / "vault"


def _clear_md_files(folder: Path):
    """Delete all .md files in a folder without removing the folder itself."""
    for f in folder.glob("*.md"):
        f.unlink()


def export_vault(vault_dir: str | None = None) -> str:
    """Regenerate the full Obsidian vault from the DB. Returns vault path."""
    vault = Path(vault_dir) if vault_dir else _DEFAULT_VAULT
    for subdir in ("discovery", "design", "sessions"):
        (vault / subdir).mkdir(parents=True, exist_ok=True)
    _clear_md_files(vault / "discovery")
    _clear_md_files(vault / "design")

    for batch in db.list_batches():
        if batch["type"] == "discovery":
            _write_discovery_batch(vault, batch)
        elif batch["type"] == "design":
            _write_design_batch(vault, batch)

    for session in db.list_sessions():
        _write_session(vault, session)

    _write_index(vault)
    return str(vault)


# --- helpers ---

def _slug(text: str, max_len: int = 40) -> str:
    """Convert text to a filesystem-safe lowercase hyphenated slug."""
    text = text.lower()[:max_len]
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    return re.sub(r"[\s-]+", "-", text).strip("-")


def _date(ts: str) -> str:
    return str(ts)[:10] if ts else "0000-00-00"


def _frontmatter(fields: dict) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if v is None:
            lines.append(f"{k}:")
        elif isinstance(v, str) and any(c in v for c in ':"{}[]|>&*!'):
            escaped = v.replace('"', '\\"')
            lines.append(f'{k}: "{escaped}"')
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def _pretty_json(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), indent=2)
    except (json.JSONDecodeError, TypeError):
        return raw or ""


def _write_discovery_batch(vault: Path, batch: dict):
    date = _date(batch["created_at"])
    query = batch["query"] or "full-scan"
    slug = _slug(query)
    prefix = f"{date}-{batch['batch_run_id']}-{slug}"
    topics = db.list_topics_for_batch(batch["id"])

    # --- context file ---
    fm = _frontmatter({
        "batch_run_id": batch["batch_run_id"],
        "type": "discovery-context",
        "query": query,
        "created_at": date,
        "topic_count": len(topics),
    })
    context = batch.get("context_text") or "_No KG context stored._"
    ctx_body = f"""{fm}

# KG Context — {query}

{context}
"""
    (vault / "discovery" / f"{prefix}-context.md").write_text(ctx_body)

    # --- topics file ---
    fm2 = _frontmatter({
        "batch_run_id": batch["batch_run_id"],
        "type": "discovery-topics",
        "query": query,
        "created_at": date,
        "topic_count": len(topics),
    })
    rows = "\n".join(
        f"| {t['id']} | {t['topic']} "
        f"| {t.get('format_suggestion') or '—'} "
        f"| {t.get('template_id') or '—'} |"
        for t in topics
    )
    raw_pretty = _pretty_json(batch.get("raw_response") or "")
    topics_body = f"""{fm2}

# Topics — {query}

| ID | Topic | Format | Template |
|---|---|---|---|
{rows}

## Agent Raw Response

```json
{raw_pretty}
```
"""
    (vault / "discovery" / f"{prefix}-topics.md").write_text(topics_body)


def _write_design_batch(vault: Path, batch: dict):
    date = _date(batch["created_at"])
    query = batch["query"] or "unknown-topic"
    slug = _slug(query)
    prefix = f"{date}-{batch['batch_run_id']}-{slug}"
    designs = db.list_designs_for_batch(batch["id"])

    # --- context file (session_md) ---
    fm = _frontmatter({
        "batch_run_id": batch["batch_run_id"],
        "type": "design-context",
        "topic": query,
        "created_at": date,
        "design_count": len(designs),
    })
    context = batch.get("context_text") or "_No session context stored._"
    ctx_body = f"""{fm}

# Session Context — {query}

{context}
"""
    (vault / "design" / f"{prefix}-context.md").write_text(ctx_body)

    # --- designs file ---
    fm2 = _frontmatter({
        "batch_run_id": batch["batch_run_id"],
        "type": "design-list",
        "topic": query,
        "created_at": date,
        "design_count": len(designs),
    })
    design_rows = []
    for d in designs:
        try:
            p = json.loads(d.get("params_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            p = {}
        goal = (p.get("goal") or "")[:80]
        selected = "✓" if d.get("selected") else ""
        design_rows.append(
            f"| {d['id']} | {p.get('topic', '—')} | {goal} "
            f"| {d.get('template_id') or '—'} | {selected} |"
        )
    rows = "\n".join(design_rows)
    raw_pretty = _pretty_json(batch.get("raw_response") or "")

    designs_body = f"""{fm2}

# Designs — {query}

| ID | Topic | Goal | Template | Selected |
|---|---|---|---|---|
{rows}

## Agent Raw Response

```json
{raw_pretty}
```
"""
    (vault / "design" / f"{prefix}-designs.md").write_text(designs_body)


def _write_session(vault: Path, session: dict):
    sid = session["id"]
    date = _date(session.get("created_at", ""))
    hid = (session.get("harmonica_session_id") or "unknown")[:8]
    design_id = session.get("design_id")
    fm = _frontmatter({
        "id": sid,
        "type": "session",
        "design_id": design_id,
        "harmonica_session_id": session.get("harmonica_session_id", ""),
        "status": session.get("status", ""),
        "created_at": date,
    })
    body = f"""{fm}

# Session — {date}

**Status:** {session.get('status') or '—'} | **Design ID:** {design_id or '—'}

## Harmonica Session ID

`{session.get('harmonica_session_id') or '—'}`

## Join URL

{session.get('join_url') or '—'}
"""
    (vault / "sessions" / f"{date}-session-{hid}.md").write_text(body)


def _write_index(vault: Path):
    body = """# Canon — Knowledge Index

## Discovery Batches

```dataview
TABLE query, topic_count, created_at
FROM "discovery"
WHERE type = "discovery-topics"
SORT created_at DESC
```

## Design Batches

```dataview
TABLE topic, design_count, created_at
FROM "design"
WHERE type = "design-list"
SORT created_at DESC
```

## Sessions

```dataview
TABLE harmonica_session_id, status, created_at
FROM "sessions"
SORT created_at DESC
```

---

*Auto-generated by Canon. Refreshed after every `--discover` and `--design` run.*
*Manual refresh: `python main.py --export-vault`*
"""
    (vault / "index.md").write_text(body)
