import json
import re

from bonfires import BonfiresClient

from harmonica.client import HarmonicaClient


_DESIGN_PROMPT = """\
You are a survey design expert. Based on the knowledge graph context below, design a \
Harmonica deliberation session.

Knowledge graph context:
{kg_context}

Produce a JSON object with exactly these keys:
  topic          - concise English title (max 10 words)
  goal           - what we want to discover (1-2 sentences, English)
  prompt         - AI facilitator instructions (2-4 sentences; guide participants to \
share concrete experiences and opinions; English only)
  questions      - list of 2-4 pre-session intake question objects, each with key "text"
  cross_pollination - true if cross-pollination of ideas between participants is useful
  summary_prompt - custom directive for the summary analysis (1 sentence, English)

Return only the JSON object, no markdown fences.
"""


class SurveyDesigner:
    """Uses a Bonfires KG agent to generate Harmonica session parameters from graph context."""

    def __init__(self, bonfire_client: BonfiresClient, harmonica_client: HarmonicaClient):
        self.bonfire = bonfire_client
        self.harmonica = harmonica_client

    def build_survey_params(self, topic_query: str) -> dict:
        """
        Search the KG for context on topic_query, then ask the Bonfires agent
        to produce structured Harmonica session parameters.

        Returns a dict ready to pass to HarmonicaClient.create_session().
        """
        kg_results = self.bonfire.kg.search(topic_query, num_results=10)
        entities = kg_results.get("entities", [])
        kg_context = self._format_entities(entities)

        prompt = _DESIGN_PROMPT.format(kg_context=kg_context)
        response = self.bonfire.agents.chat(message=prompt, graph_mode="adaptive")
        raw_text = self._extract_text(response)
        params = self._parse_json(raw_text)
        return params

    def create_session(self, topic_query: str) -> dict:
        """Full flow: design survey from KG context, create Harmonica session, return session dict."""
        params = self.build_survey_params(topic_query)
        session = self.harmonica.create_session(**params)
        return session

    # --- helpers ---

    def _format_entities(self, entities: list[dict]) -> str:
        if not entities:
            return "(no entities found)"
        lines = []
        for e in entities:
            name = e.get("name", "unknown")
            summary = e.get("summary", "")
            labels = ", ".join(e.get("labels", []))
            lines.append(f"- {name} [{labels}]: {summary}")
        return "\n".join(lines)

    def _extract_text(self, response) -> str:
        if isinstance(response, dict):
            for key in ("message", "content", "text", "response"):
                if key in response:
                    return str(response[key])
        return str(response)

    def _parse_json(self, text: str) -> dict:
        # Strip markdown fences if the model added them despite instructions
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Agent did not return valid JSON for survey params:\n{text}") from exc
