"""Wraps a single Claude API call that turns a task spec into a code+test
bundle. Kept separate from the CAP provider/requester logic so it can be
unit-tested (or swapped) without touching the negotiation/payment flow.
"""

from __future__ import annotations

import json

import anthropic

MODEL = "claude-opus-4-8"
MAX_TOKENS = 8000

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


async def generate_code(task: str) -> dict[str, str]:
    client = anthropic.AsyncAnthropic()
    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
        messages=[{"role": "user", "content": task}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    payload = json.loads(text)
    return payload["files"]
