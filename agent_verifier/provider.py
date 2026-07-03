"""Verifier agent: a CAP provider that independently checks a code+test bundle
(pytest + ruff + bandit, in a locked-down Docker sandbox) and delivers the
report as proof. Never trusts the submitted code — it only ever executes it
inside sandbox/Dockerfile's container.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess

from croo import DeliverableType, DeliverOrderRequest, EventType
from croo.errors import APIError

from common.cap_client import EventWaiter, make_client
from common.config import AgentConfig

logger = logging.getLogger("agent_verifier")

SANDBOX_IMAGE = "verified-build-sandbox"
DOCKER_TIMEOUT_SECONDS = 60
PAYMENT_WAIT_SECONDS = 900  # give the requester time to see the order and pay


def run_sandbox(files: dict[str, str]) -> dict:
    payload = json.dumps({"files": files})
    proc = subprocess.run(
        [
            "docker", "run", "--rm", "-i",
            "--network", "none",
            "--memory", "256m", "--cpus", "0.5", "--pids-limit", "128",
            "--read-only", "--tmpfs", "/tmp",
            SANDBOX_IMAGE,
        ],
        input=payload, capture_output=True, text=True, timeout=DOCKER_TIMEOUT_SECONDS,
    )
    if not proc.stdout.strip():
        raise RuntimeError(
            f"sandbox produced no output (exit {proc.returncode}): {proc.stderr[:2000]}"
        )
    return json.loads(proc.stdout)


def _parse_bundle(requirements: str) -> dict[str, str]:
    payload = json.loads(requirements)
    files = payload["files"]
    if not isinstance(files, dict) or not files:
        raise ValueError("'files' must be a non-empty object")
    return files


async def _wait_for_payment(client, stream, order_id: str) -> bool:
    """Returns True once the order is paid, False if it expired/timed out."""
    waiter = EventWaiter(stream, EventType.ORDER_PAID, lambda e: e.order_id == order_id)

    # The payment may have already landed between accept and registering the
    # waiter above — check once immediately before committing to a long wait.
    order = await client.get_order(order_id)
    if order.status == "paid":
        return True

    try:
        await waiter.wait(timeout=PAYMENT_WAIT_SECONDS)
        return True
    except asyncio.TimeoutError:
        order = await client.get_order(order_id)
        return order.status == "paid"


async def handle_negotiation(client, stream, negotiation_id: str) -> None:
    negotiation = await client.get_negotiation(negotiation_id)

    try:
        files = _parse_bundle(negotiation.requirements)
    except Exception as e:
        logger.warning("rejecting malformed negotiation %s: %s", negotiation_id, e)
        try:
            await client.reject_negotiation(negotiation_id, f"malformed requirements: {e}")
        except APIError:
            logger.exception("failed to reject negotiation %s", negotiation_id)
        return

    accept_result = await client.accept_negotiation(negotiation_id)
    order = accept_result.order
    logger.info("accepted negotiation=%s order=%s", negotiation_id, order.order_id)

    paid = await _wait_for_payment(client, stream, order.order_id)
    if not paid:
        logger.warning("order %s never paid within timeout, abandoning", order.order_id)
        return

    try:
        report = run_sandbox(files)
    except Exception as e:
        logger.exception("sandbox harness failed for order %s", order.order_id)
        report = {"overall_pass": False, "harness_error": str(e)}

    await client.deliver_order(
        order.order_id,
        DeliverOrderRequest(deliverable_type=DeliverableType.TEXT, deliverable_text=json.dumps(report)),
    )
    logger.info("delivered verification report for order=%s pass=%s", order.order_id, report.get("overall_pass"))


async def run(cfg: AgentConfig) -> None:
    client = make_client(cfg)
    stream = await client.connect_websocket()

    def on_negotiation(event) -> None:
        if event.service_id and event.service_id != cfg.service_id:
            return
        asyncio.create_task(handle_negotiation(client, stream, event.negotiation_id))

    stream.on(EventType.NEGOTIATION_CREATED, on_negotiation)
    logger.info("verifier agent listening (service_id=%s)", cfg.service_id)

    try:
        await asyncio.Event().wait()
    finally:
        await stream.close()
        await client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(AgentConfig.from_env("VERIFIER")))
