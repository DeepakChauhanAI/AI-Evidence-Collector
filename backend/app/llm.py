"""Configurable LLM provider. Any OpenAI-compatible /chat/completions endpoint
works — set the env vars for the provider of your choice (OpenAI, DeepSeek,
AgentRouter, Anthropic-via-proxy, local Ollama, etc.). Mirrors the governance
platform's agentrouter.service pattern.

    AI_API_KEY   provider key (required to enable LLM features)
    AI_BASE_URL  default https://agentrouter.org/v1
    AI_MODEL     default deepseek-v4-flash
"""
import base64
import json
import os
import re
import requests

DEFAULT_BASE_URL = "https://agentrouter.org/v1"
DEFAULT_MODEL = "deepseek-v4-flash"


def is_configured():
    return bool(os.getenv("AI_API_KEY", "").strip())


def _config():
    """(key, base_url, model) from the environment. Raises when the key is unset."""
    key = os.getenv("AI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("LLM not configured (set AI_API_KEY)")
    return (key,
            os.getenv("AI_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/"),
            os.getenv("AI_MODEL", DEFAULT_MODEL).strip())


def _headers(key):
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        # AgentRouter gates access to the codex CLI client; mirror its headers
        # (same as the governance platform's agentrouter.service).
        "User-Agent": "codex_cli_rs/0.149.1",
        "originator": "codex_cli_rs",
    }


def _chat(base, key, payload, timeout=60):
    """POST a chat completion and return the assistant text."""
    res = requests.post(f"{base}/chat/completions", headers=_headers(key),
                        json=payload, timeout=timeout)
    res.raise_for_status()
    msg = res.json()["choices"][0]["message"]
    return msg.get("content") or msg.get("reasoning_content") or ""


def complete(system_prompt, user_prompt, max_tokens=600):
    """Single-turn text completion. Returns raw model text."""
    key, base, model = _config()
    return _chat(base, key, {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    })


def describe_image(png_bytes, prompt, max_tokens=300):
    """Single-turn completion with a PNG attached, as an OpenAI-style image content
    block. Verified against the configured gateway: image blocks are forwarded and the
    model reads them (a three-band test image came back as "red green blue", in order).
    """
    key, base, model = _config()
    data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode()
    return _chat(base, key, {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "temperature": 0,
        "max_tokens": max_tokens,
    })


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
