from __future__ import annotations

import os
from dataclasses import dataclass


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
        def require(name: str) -> str:
            key = f"{prefix}_{name}"
            val = os.environ.get(key, "")
            if not val:
                raise ValueError(f"missing required env var: {key}")
            return val

        return cls(
            sdk_key=require("SDK_KEY"),
            service_id=require("SERVICE_ID"),
            base_url=require("API_URL"),
            ws_url=require("WS_URL"),
            rpc_url=os.environ.get("CROO_RPC_URL", ""),
        )
