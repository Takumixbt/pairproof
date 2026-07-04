"""Turns a task spec into a code+test bundle via an LLM call. Kept separate
from the CAP provider/requester logic so it can be unit-tested (or swapped)
without touching the negotiation/payment flow.

Three providers, picked via CODEGEN_PROVIDER:

- "ollama": a locally-running Ollama model. Zero cost, no API key, no signup
  -- this pipeline's whole point is that the Verifier independently checks
  the output, so codegen quality doesn't need to be trusted. Confirmed
  working live against gemma4:e4b on 2026-07-03, but confirmed on 2026-07-04
  that schema-constrained decoding on this CPU-only model runs at ~1.3
  tok/s (likely burning most of its budget on hidden "thinking" tokens the
  Ollama API doesn't surface separately) -- far too slow for a live demo or
  a judge's SLA window. Keep for offline/no-internet dev only.
- "groq" (default): free tier, runs open models (Llama 3.3 etc.) on
  dedicated fast inference hardware -- hundreds of tok/s, still $0. Requires
  GROQ_API_KEY from console.groq.com.
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

CODEGEN_PROVIDER = os.environ.get("CODEGEN_PROVIDER", "groq")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
ANTHROPIC_MODEL = os.environ.get("CODEGEN_MODEL", "claude-haiku-4-5")
MAX_TOKENS = 3000

SYSTEM_PROMPT = (
    "You write a single self-contained Python module and its pytest test file "
    "for the given task. solution.py must use only the standard library. "
    "test_solution.py must import from solution and cover the happy path plus "
    "at least one edge case."
)

# groq's llama-3.3-70b-versatile only supports the looser json_object response
# mode (confirmed live 2026-07-04: json_schema mode 400s with "model does not
# support response format json_schema"), which doesn't enforce a schema
# server-side -- so the shape has to be spelled out in the prompt instead.
JSON_OBJECT_INSTRUCTION = (
    ' Respond with only a JSON object of the exact shape '
    '{"files": {"solution.py": "<contents>", "test_solution.py": "<contents>"}}, '
    "with the file contents as properly escaped JSON strings."
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


async def _generate_groq(task: str) -> dict[str, str]:
    from groq import AsyncGroq

    client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
    response = await client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + JSON_OBJECT_INSTRUCTION},
            {"role": "user", "content": task},
        ],
        response_format={"type": "json_object"},
    )
    payload = json.loads(response.choices[0].message.content)
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
    if CODEGEN_PROVIDER == "groq":
        return await _generate_groq(task)
    return await _generate_ollama(task)
