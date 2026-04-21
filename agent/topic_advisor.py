import json
import tempfile
from pathlib import Path

from bonfires import BonfiresClient

import store.db as db
from agent.utils import extract_text, parse_json_list

_DISCOVERY_PROMPT = (
    Path(__file__).parent / "prompts" / "discovery_prompt.md"
).read_text()


class TopicAdvisor:
    """Queries the Bonfires KG and suggests deliberation topics + formats."""

    def __init__(self, bonfire_client: BonfiresClient):
        self.bonfire = bonfire_client

    def discover(self, query: str | None = None) -> dict:
        """Return a single topic suggestion. Convenience wrapper around discover_batch."""
        return self.discover_batch(query=query, n=1)[0]

    def discover_batch(self, query: str | None = None, n: int = 3) -> list[dict]:
        """
        Query the KG and return n topic suggestions with format recommendations.
        Each suggestion is stored to the DB. Returns list of dicts with 'id' key.

        With query:    uses kg.search(query) to surface relevant entities.
        Without query: uses kg.get_latest_episodes() for a broad KG scan.
        """
        entities_md, raw_context = self._build_context(query)
        batch_run_id = db.new_batch_id()

        # agents.sync() requires a file path — write context to a temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, prefix="canon_discovery_"
        ) as tmp:
            tmp.write(f"# Discovery Context\n\n{entities_md}")
            tmp_path = tmp.name

        prompt = _DISCOVERY_PROMPT.replace("<N>", str(n))
        self.bonfire.agents.sync(
            message=f"Discovery context{f': {query}' if query else ' (full scan)'}",
            file_path=tmp_path,
            title=f"Discovery: {query or 'full scan'}",
        )
        Path(tmp_path).unlink(missing_ok=True)

        response = self.bonfire.agents.chat(
            message=prompt, graph_mode="adaptive"
        )
        raw_text = extract_text(response)
        suggestions = parse_json_list(raw_text)

        batch_id = db.insert_batch(
            batch_run_id=batch_run_id,
            type="discovery",
            query=query,
            context_text=entities_md,
            raw_response=raw_text,
        )
        results = []
        for suggestion in suggestions:
            topic_id = db.insert_topic(
                batch_id=batch_id,
                topic=suggestion.get("topic", ""),
                format_suggestion=suggestion.get("format_suggestion"),
                template_id=suggestion.get("template_id"),
            )
            results.append({**suggestion, "id": topic_id, "batch_run_id": batch_run_id})

        return results

    # --- helpers ---

    def _build_context(self, query: str | None) -> tuple[str, str]:
        """Return (entities_md, raw_json_string) from KG."""
        if query:
            result = self.bonfire.kg.search(query, num_results=20)
            entities = result.get("entities", [])
            raw = json.dumps(result)
        else:
            agent_id = getattr(self.bonfire, "agent_id", None)
            result = self.bonfire.kg.get_latest_episodes(
                agent_id=agent_id, limit=20
            )
            episodes = result if isinstance(result, list) else result.get("episodes", [])
            entities = []
            for ep in episodes:
                if isinstance(ep, dict):
                    entities.append({
                        "name": ep.get("name") or ep.get("source_node_uuid", ""),
                        "summary": ep.get("content") or ep.get("episode_body", ""),
                        "labels": [],
                    })
            raw = json.dumps(result)

        return self._entities_to_md(entities), raw

    def _entities_to_md(self, entities: list[dict]) -> str:
        lines = []
        for e in entities:
            name = e.get("name", "unknown")
            summary = e.get("summary", "")
            labels = ", ".join(e.get("labels", []))
            lines.append(f"## {name}")
            if labels:
                lines.append(f"**Labels:** {labels}\n")
            if summary:
                lines.append(f"{summary}\n")
        return "\n".join(lines) if lines else "_No entities found._"
