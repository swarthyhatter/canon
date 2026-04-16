from bonfires import BonfiresClient

from harmonica.client import HarmonicaClient


_INGEST_PROMPT = """\
You are a knowledge graph curator. Below is a summary from a Harmonica deliberation session.
Extract all meaningful entities (people, concepts, organizations, places, topics) and the \
relationships between them. Add them to the knowledge graph.

Session summary:
{summary_text}

Focus on:
- Novel concepts or themes that emerged
- Relationships and tensions between ideas
- Concrete facts, decisions, or insights stated by participants
"""


class ResultsIngestor:
    """Ingests a completed Harmonica session summary back into the Bonfires KG."""

    def __init__(self, bonfire_client: BonfiresClient, harmonica_client: HarmonicaClient):
        self.bonfire = bonfire_client
        self.harmonica = harmonica_client

    def ingest(self, session_id: str, kengram_id: str) -> dict:
        """
        Fetch the Harmonica session summary, extract entities/relationships via the
        Bonfires agent, sync them to the KG, and pin them to the given kengram.

        Returns: { "entities_added": int, "edges_added": int, "kengram_id": str }
        """
        summary = self.harmonica.get_summary(session_id)
        summary_text = self._extract_summary_text(summary)

        prompt = _INGEST_PROMPT.format(summary_text=summary_text)
        self.bonfire.agents.chat(message=prompt, graph_mode="append")

        sync_result = self.bonfire.agents.sync()

        self.bonfire.kengrams.pin(kengram_id)

        entities_added = self._extract_count(sync_result, "entities")
        edges_added = self._extract_count(sync_result, "edges")

        return {
            "entities_added": entities_added,
            "edges_added": edges_added,
            "kengram_id": kengram_id,
        }

    # --- helpers ---

    def _extract_summary_text(self, summary: dict) -> str:
        for key in ("summary", "text", "content", "result"):
            if key in summary and summary[key]:
                return str(summary[key])
        themes = summary.get("themes", [])
        if themes:
            return "\n".join(str(t) for t in themes)
        return str(summary)

    def _extract_count(self, sync_result, entity_type: str) -> int:
        if not isinstance(sync_result, dict):
            return 0
        for key in (entity_type, f"{entity_type}_added", f"new_{entity_type}"):
            val = sync_result.get(key)
            if isinstance(val, int):
                return val
        return 0
