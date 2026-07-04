"""Builder agent: a CAP provider that takes a natural-language coding task from
a human/agent requester, generates code+tests, then — before delivering —
acts as a CAP requester itself and pays the Verifier agent to check the work.
This is the human-facing half of the two-agent pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging

from croo import DeliverableType, DeliverOrderRequest, EventType

from common.cap_client import EventWaiter, make_client
from common.config import AgentConfig

from .codegen import generate_code
from .requester import hire_verifier

logger = logging.getLogger("agent_builder")

PAYMENT_WAIT_SECONDS = 900
CODEGEN_ATTEMPTS = 3
CODEGEN_RETRY_SECONDS = 3.0


async def _generate_code_with_retries(task: str) -> dict[str, str] | None:
    # Groq (and the CAP API itself) have shown transient connection hiccups
    # in practice -- confirmed live 2026-07-04 -- and generate_code() used to
    # be a single unguarded call, so one bad request would leave the order
    # hanging for the buyer's full poll timeout with no feedback at all.
    for attempt in range(1, CODEGEN_ATTEMPTS + 1):
        try:
            return await generate_code(task)
        except Exception:
            logger.exception("codegen attempt %d/%d failed", attempt, CODEGEN_ATTEMPTS)
            if attempt < CODEGEN_ATTEMPTS:
                await asyncio.sleep(CODEGEN_RETRY_SECONDS)
    return None


def _parse_task(requirements: str) -> str:
    # CROO's API rejects non-JSON `requirements` even for services configured
    # with requirements_type=Text (confirmed live 2026-07-04: bare text 400s
    # with "requirements must be valid JSON") -- so a plain task description
    # arrives JSON-encoded as a string literal, e.g. '"do the thing"'.
    try:
        payload = json.loads(requirements)
    except json.JSONDecodeError as e:
        raise ValueError(f"requirements must be valid JSON: {e}") from e
    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("requirements JSON must be a non-empty string")
    return payload.strip()


async def _wait_for_payment(client, stream, order_id: str) -> bool:
    waiter = EventWaiter(stream, EventType.ORDER_PAID, lambda e: e.order_id == order_id)
    order = await client.get_order(order_id)
    if order.status == "paid":
        return True
    try:
        await waiter.wait(timeout=PAYMENT_WAIT_SECONDS)
        return True
    except asyncio.TimeoutError:
        order = await client.get_order(order_id)
        return order.status == "paid"


async def handle_negotiation(client, stream, negotiation_id: str, verifier_service_id: str) -> None:
    negotiation = await client.get_negotiation(negotiation_id)

    try:
        task = _parse_task(negotiation.requirements)
    except Exception as e:
        logger.warning("rejecting malformed negotiation %s: %s", negotiation_id, e)
        await client.reject_negotiation(negotiation_id, f"malformed task: {e}")
        return

    accept_result = await client.accept_negotiation(negotiation_id)
    order = accept_result.order
    logger.info("accepted negotiation=%s order=%s", negotiation_id, order.order_id)

    paid = await _wait_for_payment(client, stream, order.order_id)
    if not paid:
        logger.warning("order %s never paid within timeout, abandoning", order.order_id)
        return

    files = await _generate_code_with_retries(task)
    if files is None:
        logger.error("codegen failed after %d attempts, delivering error bundle for order %s",
                     CODEGEN_ATTEMPTS, order.order_id)
        bundle = {"files": None, "verification": {"overall_pass": False, "codegen_error": "codegen unavailable"}}
        await client.deliver_order(
            order.order_id,
            DeliverOrderRequest(deliverable_type=DeliverableType.TEXT, deliverable_text=json.dumps(bundle)),
        )
        return

    try:
        report = await hire_verifier(client, verifier_service_id, files)
    except Exception as e:
        logger.exception("verifier hire failed for order %s", order.order_id)
        report = {"overall_pass": False, "verifier_error": str(e)}

    bundle = {"files": files, "verification": report}
    await client.deliver_order(
        order.order_id,
        DeliverOrderRequest(deliverable_type=DeliverableType.TEXT, deliverable_text=json.dumps(bundle)),
    )
    logger.info(
        "delivered order=%s verifier_pass=%s", order.order_id, report.get("overall_pass")
    )


async def run(cfg: AgentConfig, verifier_service_id: str) -> None:
    client = make_client(cfg)
    stream = await client.connect_websocket()

    def on_negotiation(event) -> None:
        if event.service_id and event.service_id != cfg.service_id:
            return
        asyncio.create_task(
            handle_negotiation(client, stream, event.negotiation_id, verifier_service_id)
        )

    stream.on(EventType.NEGOTIATION_CREATED, on_negotiation)
    logger.info(
        "builder agent listening (service_id=%s, verifier_service_id=%s)",
        cfg.service_id, verifier_service_id,
    )

    try:
        await asyncio.Event().wait()
    finally:
        await stream.close()
        await client.close()


if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(AgentConfig.from_env("BUILDER"), os.environ["CROO_VERIFIER_SERVICE_ID"]))
