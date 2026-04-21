import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

_DEFAULT_BASE_URL = "https://app.harmonica.chat"
_MAX_RETRIES = 3


class HarmonicaError(Exception):
    pass


# HarmonicaClient holds a persistent httpx.Client — auth headers are set once at
# init so individual methods stay free of credential boilerplate.
# → next: harmonica/client.py:45
class HarmonicaClient:
    """Thin Python wrapper around the Harmonica REST API v1."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or os.environ["HARMONICA_API_KEY"]
        self.base_url = (
            base_url or os.getenv("HARMONICA_API_URL", _DEFAULT_BASE_URL)
        ).rstrip("/")
        self._client = httpx.Client(
            base_url=f"{self.base_url}/api/v1",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

    # _request is the single network gateway; all public methods delegate here.
    # 429 retries use Retry-After if present, otherwise exponential backoff (2^attempt).
    # → next: harmonica/client.py:70
    def _request(self, method: str, path: str, **kwargs) -> Any:
        for attempt in range(_MAX_RETRIES):
            resp = self._client.request(method, path, **kwargs)
            if resp.status_code == 429:
                if attempt < _MAX_RETRIES - 1:
                    retry_after = int(
                        resp.headers.get("Retry-After", 2 ** attempt)
                    )
                    time.sleep(retry_after)
                    continue
                raise HarmonicaError(
                    "Max retries exceeded due to rate limiting"
                )
            if resp.status_code >= 400:
                raise HarmonicaError(
                    f"HTTP {resp.status_code}: {resp.text}"
                )
            return resp.json()
        raise HarmonicaError("Max retries exceeded due to rate limiting")

    # --- Sessions ---

    # create_session omits None fields — Harmonica rejects explicit null values for
    # optional params rather than treating them as absent.
    # → next: agent/__init__.py:1
    def create_session(
        self,
        topic: str,
        goal: str,
        prompt: str | None = None,
        questions: list[dict] | None = None,
        cross_pollination: bool = False,
        summary_prompt: str | None = None,
        context: str | None = None,
        distribution: list | None = None,
        template_id: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "topic": topic,
            "goal": goal,
            "cross_pollination": cross_pollination,
        }
        if prompt:
            body["prompt"] = prompt
        if questions:
            body["questions"] = questions
        if summary_prompt:
            body["summary_prompt"] = summary_prompt
        if context:
            body["context"] = context
        if distribution:
            body["distribution"] = distribution
        if template_id:
            body["template_id"] = template_id
        return self._request("POST", "/sessions", json=body)

    def get_session(self, session_id: str) -> dict:
        return self._request("GET", f"/sessions/{session_id}")

    def list_sessions(
        self,
        status: str | None = None,
        keyword: str | None = None,
    ) -> list[dict]:
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if keyword:
            params["keyword"] = keyword
        return self._request("GET", "/sessions", params=params)

    def update_session(self, session_id: str, **fields) -> dict:
        return self._request(
            "PATCH", f"/sessions/{session_id}", json=fields
        )

    def search_sessions(self, query: str) -> list[dict]:
        return self._request(
            "GET", "/sessions", params={"keyword": query}
        )

    # --- Participants & Responses ---

    def list_participants(self, session_id: str) -> list[dict]:
        return self._request(
            "GET", f"/sessions/{session_id}/participants"
        )

    def get_responses(
        self,
        session_id: str,
        since: str | None = None,
        participant_name: str | None = None,
        min_messages: int | None = None,
        limit: int | None = None,
        last_seen_message_id: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if since:
            params["since"] = since
        if participant_name:
            params["participant_name"] = participant_name
        if min_messages is not None:
            params["min_messages"] = min_messages
        if limit is not None:
            params["limit"] = limit
        if last_seen_message_id:
            params["last_seen_message_id"] = last_seen_message_id
        return self._request(
            "GET", f"/sessions/{session_id}/responses", params=params
        )

    def get_questions(self, session_id: str) -> list[dict]:
        return self._request(
            "GET", f"/sessions/{session_id}/questions"
        )

    # --- Chat ---

    def chat_message(self, session_id: str, message: str) -> dict:
        return self._request(
            "POST",
            "/chat",
            json={"session_id": session_id, "message": message},
        )

    def submit_questions(
        self, session_id: str, answers: list[dict]
    ) -> dict:
        return self._request(
            "POST",
            f"/sessions/{session_id}/questions",
            json={"answers": answers},
        )

    # --- Summaries ---

    def generate_summary(
        self, session_id: str, prompt: str | None = None
    ) -> dict:
        body: dict[str, Any] = {}
        if prompt:
            body["prompt"] = prompt
        return self._request(
            "POST", f"/sessions/{session_id}/summary", json=body
        )

    def get_summary(self, session_id: str) -> dict:
        return self._request(
            "GET", f"/sessions/{session_id}/summary"
        )

    # --- Distribution ---

    def list_telegram_groups(self) -> list[dict]:
        return self._request("GET", "/telegram/groups")

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
