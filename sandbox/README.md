# Verification sandbox

Executes an untrusted code+test bundle (LLM-generated, never trust it) and
produces a JSON report. Build once:

```
docker build -t pairproof-sandbox ./sandbox
```

Run per verification (bundle JSON piped in on stdin, report JSON out on
stdout). The flags matter — this is untrusted code:

```
docker run --rm -i \
  --network none \
  --memory 256m --cpus 0.5 --pids-limit 128 \
  --read-only --tmpfs /tmp \
  pairproof-sandbox < bundle.json > report.json
```

`agent_verifier/provider.py` shells out with exactly these flags. For local
iteration without Docker, call `sandbox.run_checks.run_checks(files)` directly
— same logic, no isolation, fine for trusted test fixtures only.
