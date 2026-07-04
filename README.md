# PairProof

Two autonomous agents that trade real money to keep each other honest.

**Builder** takes a plain-English coding task, writes code + tests, then — before
it will accept payment for that work — hires **Verifier** over CROO's Agent
Protocol (CAP) to independently run the result in a locked-down sandbox.
Neither agent trusts the other's word; only a signed, escrow-settled report.

Submission for the **CROO Agent Hackathon** — Developer Tooling + Open tracks.

## Why

An LLM that writes code will hand you code that's confidently wrong, and
there's no way to know without checking it yourself. PairProof makes that
check structural instead of optional: the code-writing agent cannot get paid
until it has already paid a second, independent agent to verify its own work.

The verification isn't cosmetic. Asked for a password generator, Builder's
codegen reaches for `random.choice` — it works, its own tests pass — and
Verifier's sandbox flags it anyway, because `bandit` catches insecure
randomness that no unit test would ever catch. That's the whole thesis, in
one run.

## How a task flows

```
  you                    Builder                  Verifier
   |--- negotiate + pay ---->|                         |
   |      (Order 1)          |--- negotiate + pay ---->|
   |                         |      (Order 2)          |
   |                         |                         |--- runs sandbox
   |                         |<--- deliver + clear ----|    (pytest, ruff,
   |<--- deliver + clear ----|      (Order 2)          |     bandit)
   |      (Order 1)          |
```

Every arrow above is a real CAP order: negotiate → lock (escrow) → deliver
(proof) → clear (settlement + reputation update). Order 2 is invisible to the
original requester — it's Builder spending its own money to buy a second
opinion before it'll stand behind its own work.

## Status

Both agents are registered, funded, and live on the CROO Agent Store. The
full loop has been confirmed end-to-end with real USDC settled on Base on
both legs — human → Builder, and Builder → Verifier.

- `sandbox/` — the verification harness (pytest + ruff + bandit), unit-tested
  in `tests/` against known-good, logic-broken, and insecure fixtures.
- `agent_verifier/provider.py` — CAP provider: accepts a code+test bundle,
  waits for payment, runs the Docker sandbox, delivers the signed report.
- `agent_builder/codegen.py` — turns a task into a code+test bundle. Default
  provider is Groq's free tier (fast, no cost); Ollama and Claude Haiku 4.5
  are available as swap-in alternatives via `CODEGEN_PROVIDER`.
- `agent_builder/provider.py` + `requester.py` — the human-facing order, and
  the A2A leg that hires Verifier.
- `scripts/smoke_test.py` — drives one task through the full pipeline as a
  human requester would, end to end.

## Setup

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
docker build -t pairproof-sandbox ./sandbox
copy .env.example .env   # fill in your own SDK keys / service IDs
```

Register each agent (Builder, Verifier, and a throwaway requester identity)
at `agent.croo.network` to get its `*_SDK_KEY` / `*_SERVICE_ID`, and fund
each agent's on-chain wallet with a small amount of USDC on Base — CROO's
paymaster sponsors gas, but still needs the payer to hold some of the token
it's sponsoring.

Run each agent in its own terminal, or use `scripts/run_agents.ps1` /
`stop_agents.ps1` to start and stop both as background processes:

```
python -m agent_verifier.provider
python -m agent_builder.provider
```

Then drive a real task through the pipeline:

```
python scripts/smoke_test.py "Write a function that generates a random alphanumeric password of a given length."
```

## Testing without spending real USDC

```
.venv\Scripts\pytest tests -v
```

Exercises `sandbox/run_checks.py` directly against known-good, known-bad, and
insecure fixtures — no Docker, no CAP, no cost. It doesn't exercise the
negotiate/pay/deliver loop itself, which needs real credentials and real
USDC (CROO has no testnet/sandbox mode as of this writing).
