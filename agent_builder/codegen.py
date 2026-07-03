"""Turns a task spec into a code+test bundle via an LLM call. Kept separate
from the CAP provider/requester logic so it can be unit-tested (or swapped)
without touching the negotiation/payment flow.

Two providers, picked via CODEGEN_PROVIDER:

- "ollama" (default): a locally-running Ollama model. Zero cost, no API key,
  no signup -- this pipeline's whole point is that the Verifier independently
  checks the output, so codegen quality doesn't need to be trusted, and a
  free local model is the right default for that reason alone, not just cost.
  Confirmed working live against gemma4:e4b on 2026-07-03.
- "anthropic": Claude Haiku 4.5, for when you have an API key and want higher
  quality. Requires ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv

# Safe to call even if common.config already did -- idempotent, and this
# keeps codegen.py usable standalone (e.g. from a test script) without
# depending on import order elsewhere.
load_dotenv()

CODEGEN_PROVIDER = os.environ.get("CODEGEN_PROVIDER", "ollama")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
ANTHROPIC_MODEL = os.environ.get("CODEGEN_MODEL", "claude-haiku-4-5")
MAX_TOKENS = 3000

SYSTEM_PROMPT = (
    "You write a single self-contained Python module and its pytest test file "
    "for the given task. solution.py must use only the standard library. "
    "test_solution.py must import from solution and cover the happy path plus "
    "at least one edge case."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {
            "type": "object",
            "properties": {
                "solution.py": {"type": "string"},
                "test_solution.py": {"type": "string"},
            },
            "required": ["solution.py", "test_solution.py"],
            "additionalProperties": False,
        },
    },
    "required": ["files"],
    "additionalProperties": False,
}


async def _generate_ollama(task: str) -> dict[str, str]:
    import ollama

    client = ollama.AsyncClient()
    response = await client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ],
        format=OUTPUT_SCHEMA,
    )
    payload = json.loads(response.message.content)
    return payload["files"]


async def _generate_anthropic(task: str) -> dict[str, str]:
    import anthropic

    client = anthropic.AsyncAnthropic()
    # No `thinking`/`effort` here on purpose: Haiku 4.5 doesn't support the
    # effort parameter (400s), and this task is simple enough that thinking
    # wouldn't change the outcome -- the structured-output schema already
    # constrains the shape, and the Verifier catches actual mistakes.
    response = await client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": task}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    payload = json.loads(text)
    return payload["files"]


async def generate_code(task: str) -> dict[str, str]:
    if CODEGEN_PROVIDER == "anthropic":
        return await _generate_anthropic(task)
    return await _generate_ollama(task)
