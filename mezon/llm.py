"""Client for the local OpenAI-compatible model server (vLLM on the box). Decision text never goes to a cloud API."""

import json

import httpx

from mezon import config


class LLMUnavailable(RuntimeError):
    pass


def _model(client: httpx.Client) -> str:
    if config.LLM_MODEL:
        return config.LLM_MODEL
    data = client.get(f"{config.LLM_BASE_URL}/models").json()["data"]
    return data[0]["id"]


def chat_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    """One JSON-only completion at temperature 0; raises LLMUnavailable when the box is off or the reply isn't JSON."""
    try:
        with httpx.Client(timeout=config.LLM_TIMEOUT_S) as client:
            body = {
                "model": _model(client),
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            }
            r = client.post(f"{config.LLM_BASE_URL}/chat/completions", json=body)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError) as e:
        raise LLMUnavailable(str(e)) from e
    try:
        return json.loads(text[text.find("{"): text.rfind("}") + 1])
    except json.JSONDecodeError as e:
        raise LLMUnavailable(f"non-JSON reply: {text[:120]}") from e
