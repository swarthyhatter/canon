import json
import re
from pathlib import Path

from bonfires import BonfiresClient

from harmonica.client import HarmonicaClient


# The design prompt lives in an .md file so it can be tuned without touching Python.
# It instructs the KG agent to return all Harmonica session fields as JSON.
# → next: agent/survey_designer.py:32
_DESIGN_PROMPT = (
    Path(__file__).parent / "prompts" / "design_prompt.md"
).read_text()


class SurveyDesigner:
    """Generates Harmonica session parameters from Bonfires KG context."""

    def __init__(
        self,
        bonfire_client: BonfiresClient,
        harmonica_client: HarmonicaClient,
    ):
        self.bonfire = bonfire_client
        self.harmonica = harmonica_client

    # Three-step flow: KG search → write session.md → ask agent for JSON params.
    # session.md is synced as a file so the agent reads it as a document, not inline text.
    # → next: agent/survey_designer.py:68
    def build_survey_params(self, topic_query: str) -> dict:
        """
        Search the KG for context on topic_query, write a session.md document,
        sync it to the Bonfires agent, then ask the agent to produce all
        Harmonica session parameters as a JSON object.

        Returns a dict ready to pass to HarmonicaClient.create_session().
        """
        kg_results = self.bonfire.kg.search(topic_query, num_results=10)
        entities = kg_results.get("entities", [])

        session_md_path = self._write_session_md(topic_query, entities)
        self.bonfire.agents.sync(
            message=f"Session context for: {topic_query}",
            file_path=session_md_path,
            title=f"Session: {topic_query}",
        )

        response = self.bonfire.agents.chat(
            message=_DESIGN_PROMPT, graph_mode="adaptive"
        )
        raw_text = self._extract_text(response)
        params = self._parse_json(raw_text)
        return params

    def create_session(self, topic_query: str) -> dict:
        """Design survey from KG context, create Harmonica session."""
        params = self.build_survey_params(topic_query)
        session = self.harmonica.create_session(**params)
        return session

    # --- helpers ---

    # _write_session_md serializes KG entities to Markdown — the agent produces
    # better facilitation output from readable prose than from raw JSON dicts.
    # → next: agent/results_ingestor.py:25
    def _write_session_md(
        self, topic_query: str, entities: list[dict]
    ) -> str:
        lines = [f"# Session Context: {topic_query}\n"]
        for e in entities:
            name = e.get("name", "unknown")
            summary = e.get("summary", "")
            labels = ", ".join(e.get("labels", []))
            lines.append(f"## {name}")
            if labels:
                lines.append(f"**Labels:** {labels}\n")
            if summary:
                lines.append(f"{summary}\n")
        path = "session.md"
        with open(path, "w") as f:
            f.write("\n".join(lines))
        return path

    def _extract_text(self, response) -> str:
        if isinstance(response, dict):
            for key in ("reply", "message", "content", "text", "response"):
                if key in response:
                    return str(response[key])
        return str(response)

    def _parse_json(self, text: str) -> dict:
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Agent did not return valid JSON:\n{text}"
            ) from exc
