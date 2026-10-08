"""Configurable LLM provider. Any OpenAI-compatible /chat/completions endpoint
works — set the env vars for the provider of your choice (OpenAI, DeepSeek,
AgentRouter, Anthropic-via-proxy, local Ollama, etc.). Mirrors the governance
platform's agentrouter.service pattern.

    AI_API_KEY   provider key (required to enable LLM features)
    AI_BASE_URL  default https://agentrouter.org/v1
    AI_MODEL     default deepseek-v4-flash
"""
import json
import os
import re
import requests

DEFAULT_BASE_URL = "https://agentrouter.org/v1"
DEFAULT_MODEL = "deepseek-v4-flash"


def is_configured():
    return bool(os.getenv("AI_API_KEY", "").strip())


def complete(system_prompt, user_prompt, max_tokens=600):
    """Single-turn completion. Returns raw model text."""
    key = os.getenv("AI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("LLM not configured (set AI_API_KEY)")
    base = os.getenv("AI_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    model = os.getenv("AI_MODEL", DEFAULT_MODEL).strip()
    res = requests.post(
        f"{base}/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # AgentRouter gates access to the codex CLI client; mirror its headers
            # (same as the governance platform's agentrouter.service).
            "User-Agent": "codex_cli_rs/0.149.1",
            "originator": "codex_cli_rs",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        },
        timeout=60,
    )
    res.raise_for_status()
    data = res.json()
    msg = data["choices"][0]["message"]
    return msg.get("content") or msg.get("reasoning_content") or ""


def extract_json(content):
    """Robust JSON extraction from model output (handles ```json fences)."""
    if not content:
        return {}
    try:
        return json.loads(content)
    except ValueError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if m:
        try:
            return json.loads(m.group(1))
        except ValueError:
            pass
    i, j = content.find("{"), content.rfind("}")
    if i != -1 and j > i:
        try:
            return json.loads(content[i:j + 1])
        except ValueError:
            pass
    return {}
