# PairProof

Two-agent submission for the CROO Agent Hackathon (Developer Tooling + Open
tracks). **Builder** takes a coding task, generates code+tests, then
autonomously pays **Verifier** via CAP to independently run the code in a
sandboxed Docker container before delivering the verified bundle to the
original requester. Full design rationale: `C:\Users\Takum\.claude\plans\sunny-zooming-hearth.md`.

## Status

Built and locally verified without live CAP credentials:

- `sandbox/` — pytest+ruff+bandit verification harness. Unit-tested
  (`tests/test_run_checks.py`) against known-good, logic-broken, and
  insecure code samples — all three cases correctly detected.
- `agent_verifier/provider.py` — CAP provider: accepts a code+test bundle,
  waits for payment, runs the Docker sandbox, delivers the report.
- `agent_builder/codegen.py` — turns a task spec into a code+test bundle via
  structured JSON output. Defaults to a **free local Ollama model**
  (`gemma4:e4b`, no API key, no signup — confirmed working live) with Claude
  Haiku 4.5 as an optional paid override (`CODEGEN_PROVIDER=anthropic`).
- `agent_builder/provider.py` + `requester.py` — the human-facing order plus
  the A2A leg that hires the Verifier.
- All modules import cleanly and fail exactly at the expected point (missing
  env var) when run without credentials — confirmed via `python -m
  agent_verifier.provider` / `python -m agent_builder.provider`.

**Not yet done** (needs you, not more code — see the plan's Phase 0):

1. Register both agents + their services on the CROO dashboard → get
   `*_SDK_KEY` / `*_SERVICE_ID` values.
2. Fund each agent's on-chain wallet (shown on the dashboard after
   registration) with a small amount of ETH (gas) + USDC (test payment).
   The SDK authenticates via `X-SDK-Key` only — no private key is ever
   generated or handled by this code.
3. Confirm `CROO_API_URL` / `CROO_WS_URL` (not documented anywhere we could
   find — pull from the dashboard).
4. Fill in `.env` (copy `.env.example`) and run both agents.
5. List both agents on the CROO Agent Store, record the demo, submit.

## Setup

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
docker build -t pairproof-sandbox ./sandbox
copy .env.example .env   # then fill in real values
```

(Use `python -m pip`, not `pip.exe` directly — renaming this folder after venv
creation breaks the `pip.exe` launcher's baked-in path; `python -m pip`
doesn't have that problem.)

Codegen defaults to a local Ollama model — no cost, no key. Make sure
`ollama serve` is running and `OLLAMA_MODEL` (default `gemma4:e4b`) is pulled:

```
ollama pull gemma4:e4b
```

Run each agent in its own terminal, with `.env` loaded:

```
python -m agent_verifier.provider
python -m agent_builder.provider
```

## Testing without spending real USDC

```
.venv\Scripts\pytest tests -v
```

This exercises `sandbox/run_checks.py` directly (no Docker, no CAP) against
known-good/bad/insecure fixtures. It does **not** exercise the CAP
negotiate/pay/deliver loop — that requires real credentials and, per CROO's
docs, real USDC (no confirmed testnet/sandbox mode as of this writing).
