"""One-shot end-to-end smoke test: acts as the Tester agent (playing the
"human requester" role), submits one coding task to the Builder via CAP, and
prints the final verified bundle.

Requires:
- agent_verifier.provider and agent_builder.provider already running in
  their own processes (this script only drives the Tester side).
- TESTER_SDK_KEY, BUILDER_SERVICE_ID set in .env, and the Tester wallet
  funded with a small amount of USDC on Base.

Usage: python scripts/smoke_test.py ["optional task description"]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from croo import ListOptions, NegotiateOrderRequest, NegotiationStatus, OrderStatus
from dotenv import load_dotenv

from common.cap_client import make_client, poll_until
from common.config import AgentConfig

load_dotenv()

DEFAULT_TASK = "Write a function that checks whether a number is prime."


async def main() -> None:
    task = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TASK

    cfg = AgentConfig(
        sdk_key=os.environ["TESTER_SDK_KEY"],
        service_id="",  # Tester never sells a service, only requests
        base_url=os.environ["CROO_API_URL"],
        ws_url=os.environ["CROO_WS_URL"],
        rpc_url=os.environ.get("CROO_RPC_URL", ""),
    )
    builder_service_id = os.environ["BUILDER_SERVICE_ID"]
    client = make_client(cfg)

    print(f"Task: {task!r}")
    print(f"Negotiating with Builder service {builder_service_id}...")
    negotiation = await client.negotiate_order(
        NegotiateOrderRequest(service_id=builder_service_id, requirements=task)
    )
    print(f"  negotiation_id={negotiation.negotiation_id} status={negotiation.status}")

    accepted = await poll_until(
        lambda: client.get_negotiation(negotiation.negotiation_id),
        lambda n: n.status != NegotiationStatus.PENDING,
        timeout=120,
    )
    if accepted.status != NegotiationStatus.ACCEPTED:
        raise RuntimeError(f"Builder rejected the negotiation: {accepted.reject_reason}")
    print("Negotiation accepted.")

    orders = await client.list_orders(ListOptions(role="requester"))
    order = next(o for o in orders if o.negotiation_id == negotiation.negotiation_id)
    print(f"Order created: {order.order_id} price={order.price} token={order.payment_token}")

    print("Paying order...")
    pay_result = await client.pay_order(order.order_id)
    print(f"  tx_hash={pay_result.tx_hash}")

    print("Waiting for Builder to generate, hire the Verifier, and deliver "
          "(this can take a while -- codegen + a full second CAP order)...")
    completed = await poll_until(
        lambda: client.get_order(order.order_id),
        lambda o: o.status in (OrderStatus.COMPLETED, OrderStatus.REJECTED, OrderStatus.EXPIRED),
        timeout=900,
        interval=5.0,
    )
    if completed.status != OrderStatus.COMPLETED:
        raise RuntimeError(f"order did not complete: {completed.status}")

    delivery = await client.get_delivery(order.order_id)
    bundle = json.loads(delivery.deliverable_text)
    print("\n=== DELIVERED BUNDLE ===")
    print(json.dumps(bundle, indent=2))

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
