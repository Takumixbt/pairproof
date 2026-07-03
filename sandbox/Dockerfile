FROM python:3.12-slim

RUN pip install --no-cache-dir pytest==8.* ruff==0.* bandit==1.*

WORKDIR /sandbox
COPY run_checks.py .

# No CMD network access, no persistent state: each verification run is a
# throwaway container (see sandbox/README.md for the required `docker run`
# flags — network disabled, memory/cpu/pids capped, read-only root fs).
ENTRYPOINT ["python", "run_checks.py"]
