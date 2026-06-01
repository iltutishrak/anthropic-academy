"""
batch_forecast.py

Forecasting the WHOLE fleet at once, asynchronously, at half price.

Forecasting one pool is a live API call (ec2_mac_forecaster.py). But a capacity
team re-forecasts every pool nightly. Doing that live is slow and full-price. The
Batches API is the answer: submit up to 100k requests as one job, processed
asynchronously at 50% cost. Perfect for "re-forecast the fleet overnight."

Trade-off: it is NOT real-time. A batch usually finishes in minutes but can take
up to an hour. This script submits the batch and then polls until it's done, so
expect it to wait. That waiting IS the lesson - batches trade latency for cost.

    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 batch_forecast.py
"""

from __future__ import annotations

import os
import time

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request


MODEL = "claude-opus-4-8"

SYSTEM = (
    "You are a supply-chain demand-planning analyst for the AWS EC2 Mac instance "
    "family. Given a pool snapshot, reply in ONE sentence: the risk level (low/"
    "moderate/high) and the single action to take. Be terse."
)

# The fleet: every pool we want re-forecast tonight. In production this list would
# be generated from your inventory, not hand-written.
POOLS = [
    ("mac2-m2.metal", "us-east-1", "median peak 220, allocated 260, week-3 GA spike to 440"),
    ("mac2-m2.metal", "eu-west-1", "median peak 70, allocated 80, week-3 GA spike to 140 (thin pool)"),
    ("mac2-m2pro.metal", "us-east-1", "median peak 95, allocated 110, rising CI matrix demand"),
    ("mac2.metal", "us-east-1", "median peak 140, allocated 200, mature/steady"),
    ("mac1.metal", "us-east-1", "median peak 40, allocated 120, Intel, structural decline"),
]


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first:  export ANTHROPIC_API_KEY=sk-ant-...")

    client = anthropic.Anthropic()

    # 1. Build one Request per pool. custom_id lets us match results back to pools.
    #    Note: custom_id must match ^[a-zA-Z0-9_-]{1,64}$ — no dots — so we replace
    #    the "." in instance types like "mac2-m2.metal" with "-".
    requests = [
        Request(
            custom_id=f"{itype}__{region}".replace(".", "-"),
            params=MessageCreateParamsNonStreaming(
                model=MODEL,
                max_tokens=256,
                system=SYSTEM,
                messages=[{
                    "role": "user",
                    "content": f"Pool: {itype} in {region}. Snapshot: {snap}.",
                }],
            ),
        )
        for itype, region, snap in POOLS
    ]

    # 2. Submit the whole batch as a single job (50% cheaper than live calls).
    batch = client.messages.batches.create(requests=requests)
    print(f"Submitted batch {batch.id} with {len(requests)} pools.")
    print("Batches are asynchronous - polling until it finishes (minutes, sometimes longer)...")

    # 3. Poll until the batch ends. time.sleep is fine here - this is your machine.
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        print(f"  status={batch.processing_status} "
              f"processing={batch.request_counts.processing} "
              f"succeeded={batch.request_counts.succeeded}")
        time.sleep(15)

    # 4. Collect results. Order isn't guaranteed - match on custom_id.
    print("\n" + "=" * 64)
    print("FLEET FORECAST (one batch, half price)")
    print("=" * 64)
    for result in client.messages.batches.results(batch.id):
        if result.result.type == "succeeded":
            msg = result.result.message
            text = next((b.text for b in msg.content if b.type == "text"), "")
            print(f"  {result.custom_id:<28} {text.strip()}")
        else:
            print(f"  {result.custom_id:<28} [{result.result.type}]")


if __name__ == "__main__":
    main()
