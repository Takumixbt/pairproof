from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Loaded once at import time so every entrypoint (agent_verifier.provider,
# agent_builder.provider, ad-hoc test scripts) picks up .env automatically --
# nobody has to `export` keys into the shell by hand.
load_dotenv()


@dataclass
class AgentConfig:
    """Env-driven config for one CAP agent identity (Builder or Verifier)."""

    sdk_key: str
    service_id: str
    base_url: str
    ws_url: str
    rpc_url: str = ""

    @classmethod
    def from_env(cls, prefix: str) -> "AgentConfig":
        def require(key: str) -> str:
            val = os.environ.get(key, "")
            if not val:
                raise ValueError(f"missing required env var: {key}")
            return val

        return cls(
            sdk_key=require(f"{prefix}_SDK_KEY"),
            service_id=require(f"{prefix}_SERVICE_ID"),
            # Shared across both agents -- not per-prefix, per .env.example.
            base_url=require("CROO_API_URL"),
            ws_url=require("CROO_WS_URL"),
            rpc_url=os.environ.get("CROO_RPC_URL", ""),
        )
