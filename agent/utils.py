import json
import re


def extract_text(response) -> str:
    if isinstance(response, dict):
        for key in ("reply", "message", "content", "text", "response"):
            if key in response:
                return str(response[key])
    return str(response)


def parse_json(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, list) and result:
            return result[0]
        return result
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent did not return valid JSON:\n{text}") from exc


def parse_json_list(text: str) -> list[dict]:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("topics", "suggestions", "results"):
                if key in result and isinstance(result[key], list):
                    return result[key]
        return [result]
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent did not return valid JSON:\n{text}") from exc
