from __future__ import annotations

import json


def parse_json_object(raw: str) -> dict[str, object]:
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = candidate.replace("json", "", 1).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Expected JSON from LLM provider, got invalid output: {raw[:160]}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object payload from LLM provider.")
    return payload
