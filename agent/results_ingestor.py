from bonfires import BonfiresClient

from harmonica.client import HarmonicaClient


_INGEST_PROMPT = """\
You are a knowledge graph curator. Below is a summary from a
Harmonica deliberation session. Extract all meaningful entities
(people, concepts, organizations, places, topics) and the
relationships between them. Add them to the knowledge graph.

Session summary:
{summary_text}

Focus on:
- Novel concepts or themes that emerged
- Relationships and tensions between ideas
- Concrete facts, decisions, or insights stated by participants
"""


# ResultsIngestor runs the reverse of SurveyDesigner: reads a Harmonica session
# summary and pushes new entities/edges back into the KG.
# → next: agent/results_ingestor.py:39
class ResultsIngestor:
    """Ingests a completed Harmonica session summary back into the Bonfires KG."""

    def __init__(
        self,
        bonfire_client: BonfiresClient,
        harmonica_client: HarmonicaClient,
    ):
        self.bonfire = bonfire_client
        self.harmonica = harmonica_client

    # graph_mode="append" is critical — "adaptive" would let the agent overwrite
    # existing nodes; "append" only adds new ones, preserving prior KG state.
    # → next: main.py:15
    def ingest(self, session_id: str, kengram_id: str) -> dict:
        """
        Fetch the Harmonica session summary, extract entities/relationships via
        the Bonfires agent, sync them to the KG, then pin the top surfaced
        entities to the given kengram.

        Returns: { "entities_pinned": int, "kengram_id": str }
        """
        summary = self.harmonica.get_summary(session_id)
        summary_text = self._extract_summary_text(summary)

        prompt = _INGEST_PROMPT.format(summary_text=summary_text)
        self.bonfire.agents.chat(message=prompt, graph_mode="append")

        self.bonfire.agents.sync(message=summary_text)

        kg_results = self.bonfire.kg.search(summary_text[:200], num_results=5)
        entities = kg_results.get("entities", [])

        pinned = 0
        for entity in entities:
            uuid = entity.get("uuid")
            if uuid:
                self.bonfire.kengrams.pin(kengram_id, uuid)
                pinned += 1

        return {
            "entities_pinned": pinned,
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
