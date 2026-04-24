import json
import tempfile
from pathlib import Path

from bonfires import BonfiresClient

from harmonica.client import HarmonicaClient
import store.db as db
from agent.utils import extract_text, parse_json, parse_json_list


_DESIGN_PROMPT = (
    Path(__file__).parent / "prompts" / "design_prompt.md"
).read_text()

_FORMATS_LIBRARY_PATH = str(
    Path(__file__).parent / "data" / "facilitation_formats.md"
)


def _load_format_prompt(format_name: str) -> str | None:
    text = Path(_FORMATS_LIBRARY_PATH).read_text()
    sections = text.split("\n---\n")
    for section in sections:
        heading_line = next(
            (line for line in section.splitlines() if line.startswith("## ")), ""
        )
        if format_name.lower() in heading_line.lower():
            marker = "### Facilitation Prompt\n"
            idx = section.find(marker)
            if idx != -1:
                return section[idx + len(marker):].strip()
    return None


INTAKE_QUESTIONS = [
    {"text": "Name"},
    {"text": "Wallet Address"},
    {"text": "Email Address"},
]

# <N> must be replaced with str(n) before sending — see build_survey_params_from_topic
_DESIGN_PROMPT_BATCH_SUFFIX = (
    "\n\nIMPORTANT: You must generate exactly <N> design variations for the "
    "SAME topic described in the session context above. Do NOT invent different "
    "topics. Each variation should differ in framing, emphasis, or facilitation "
    "angle — but all must be designs for that exact topic.\n\n"
    "Return a JSON array of exactly <N> objects (same fields as above). "
    "Return only the array, no markdown fences."
)


class SurveyDesigner:
    """Generates Harmonica session parameters from Bonfires KG context."""

    def __init__(
        self,
        bonfire_client: BonfiresClient,
        harmonica_client: HarmonicaClient,
    ):
        self.bonfire = bonfire_client
        self.harmonica = harmonica_client

    def build_survey_params(self, topic_query: str) -> dict:
        """
        Single-result path. Accepts a raw topic string.
        Kept for direct use and backwards compatibility.
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
        return parse_json(extract_text(response))

    def build_survey_params_from_topic(
        self, topic_id: int, n: int = 1
    ) -> list[dict]:
        """
        Batch path. Reads topic from DB by ID, generates n design variations,
        stores each to DB, returns list of dicts with 'id' key added.
        """
        topic_row = db.get_topic(topic_id)
        topic_query = topic_row["topic"]
        format_suggestion = topic_row.get("format_suggestion")

        kg_results = self.bonfire.kg.search(topic_query, num_results=10)
        entities = kg_results.get("entities", [])
        session_md_content = self._build_session_md_content(
            topic_query, entities, format_suggestion
        )
        session_md_path = self._write_session_md_from_content(session_md_content)

        self.bonfire.agents.sync(
            message=f"Session context for: {topic_query}",
            file_path=session_md_path,
            title=f"Session: {topic_query}",
        )
        formats_content = Path(_FORMATS_LIBRARY_PATH).read_text()
        formats_block = (
            "\n\n---\n# Facilitation Formats Reference Library\n\n"
            + formats_content
            + "\n---\n\n"
        )
        topic_anchor = (
            f"The deliberation topic is: \"{topic_query}\"\n"
            f"Recommended format: {format_suggestion or 'Open Dialogue'}\n\n"
        )
        if n == 1:
            response = self.bonfire.agents.chat(
                message=topic_anchor + _DESIGN_PROMPT + formats_block,
                graph_mode="adaptive",
            )
            params_list = [parse_json(extract_text(response))]
        else:
            prompt = (
                topic_anchor
                + _DESIGN_PROMPT
                + formats_block
                + _DESIGN_PROMPT_BATCH_SUFFIX
            ).replace("<N>", str(n))
            response = self.bonfire.agents.chat(
                message=prompt, graph_mode="adaptive"
            )
            params_list = parse_json_list(extract_text(response))

        batch_run_id = db.new_batch_id()
        batch_id = db.insert_batch(
            batch_run_id=batch_run_id,
            type="design",
            query=topic_query,
            context_text=session_md_content,
            raw_response=extract_text(response),
        )
        results = []
        for params in params_list:
            design_id = db.insert_design(
                batch_id=batch_id,
                topic_id=topic_id,
                params_json=json.dumps(params),
                template_id=params.get("template_id"),
            )
            results.append({**params, "id": design_id, "batch_run_id": batch_run_id})

        return results

    def create_session(self, topic_query: str) -> dict:
        """Single-shot: design from raw query + create Harmonica session."""
        params = self.build_survey_params(topic_query)
        return self.harmonica.create_session(**params)

    def create_session_from_design(
        self,
        design_id: int,
        template_id: str | None = None,
        cross_pollination: bool = True,
    ) -> dict:
        """Create a Harmonica session from a stored design row."""
        design = db.get_design(design_id)
        params = json.loads(design["params_json"])
        tid = template_id or design.get("template_id")
        format_name = params.pop("format", "") or ""
        if format_name:
            loaded = _load_format_prompt(format_name)
            if loaded:
                params["prompt"] = loaded
        params["questions"] = INTAKE_QUESTIONS
        params["cross_pollination"] = cross_pollination
        session = self.harmonica.create_session(**params, template_id=tid)
        db.mark_selected(design_id)
        harmonica_id = session.get("id") or session.get("session_id", "")
        join_url = (
            session.get("join_url") or session.get("url")
            or session.get("participant_url", "")
        )
        db.insert_session(
            design_id=design_id,
            harmonica_session_id=harmonica_id,
            join_url=join_url,
        )
        return session

    # --- helpers ---

    def _build_session_md_content(
        self,
        topic_query: str,
        entities: list[dict],
        format_suggestion: str | None = None,
    ) -> str:
        lines = [f"# Session Context: {topic_query}\n"]
        if format_suggestion:
            lines.append(f"**Recommended format:** {format_suggestion}\n")
        for e in entities:
            name = e.get("name", "unknown")
            summary = e.get("summary", "")
            labels = ", ".join(e.get("labels", []))
            lines.append(f"## {name}")
            if labels:
                lines.append(f"**Labels:** {labels}\n")
            if summary:
                lines.append(f"{summary}\n")
        return "\n".join(lines)

    def _write_session_md(
        self, topic_query: str, entities: list[dict]
    ) -> str:
        content = self._build_session_md_content(topic_query, entities)
        return self._write_session_md_from_content(content)

    def _write_session_md_from_content(self, content: str) -> str:
        # Uses a temp file to avoid polluting the working directory
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, prefix="canon_session_"
        ) as tmp:
            tmp.write(content)
            return tmp.name
