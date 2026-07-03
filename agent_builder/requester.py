"""Builder-as-requester: hires the Verifier agent via CAP before the Builder
ever delivers to its own (human) requester. This is the A2A leg.

Uses plain polling rather than the websocket event stream — the Builder isn't
listening for many concurrent orders here, it's driving one specific
negotiation it just created, so a poll loop is simpler and doesn't depend on
event-field semantics that aren't confirmed against a live server yet (see
the plan's "open items to resolve" note).
"""

from __future__ import annotations

import json

from croo import ListOptions, NegotiateOrderRequest, NegotiationStatus, Order, OrderStatus

from common.cap_client import poll_until

DEFAULT_TIMEOUT_SECONDS = 600


async def hire_verifier(
    client, verifier_service_id: str, files: dict[str, str], timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Negotiates, pays, and retrieves a verification report from the Verifier
    agent's CAP service. Raises on rejection, timeout, or a non-completed order.
    """
    requirements = json.dumps({"files": files})
    negotiation = await client.negotiate_order(
        NegotiateOrderRequest(service_id=verifier_service_id, requirements=requirements)
    )

    accepted = await poll_until(
        lambda: client.get_negotiation(negotiation.negotiation_id),
        lambda n: n.status != NegotiationStatus.PENDING,
        timeout=timeout,
    )
    if accepted.status != NegotiationStatus.ACCEPTED:
        raise RuntimeError(
            f"verifier rejected negotiation {negotiation.negotiation_id}: {accepted.reject_reason}"
        )

    orders = await client.list_orders(ListOptions(role="requester"))
    order: Order | None = next(
        (o for o in orders if o.negotiation_id == negotiation.negotiation_id), None
    )
    if order is None:
        raise RuntimeError(f"no order found for accepted negotiation {negotiation.negotiation_id}")

    await client.pay_order(order.order_id)

    completed = await poll_until(
        lambda: client.get_order(order.order_id),
        lambda o: o.status in (OrderStatus.COMPLETED, OrderStatus.REJECTED, OrderStatus.EXPIRED),
        timeout=timeout,
    )
    if completed.status != OrderStatus.COMPLETED:
        raise RuntimeError(f"verifier order {order.order_id} did not complete: {completed.status}")

    delivery = await client.get_delivery(order.order_id)
    return json.loads(delivery.deliverable_text)
