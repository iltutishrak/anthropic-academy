"""
vision_demo.py

When the data is a picture, not text.

Capacity data often lives in a dashboard screenshot or a chart, not a tidy table.
Vision lets Claude read an image. Here we generate a utilization bar chart, hand
Claude the image, and ask it to assess risk - exactly the "here's a screenshot of
our graph, what's wrong?" workflow.

This script generates its own chart so it runs without you supplying an image.
It needs matplotlib for the chart step:

    pip install anthropic matplotlib
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 vision_demo.py
"""

from __future__ import annotations

import base64
import os

import anthropic


MODEL = "claude-opus-4-8"
CHART_PATH = "utilization_chart.png"


def make_chart() -> bool:
    """Generate a utilization bar chart. Returns False if matplotlib is missing."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # no display needed
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    pools = ["m2/us-east-1", "m2/eu-west-1", "m2pro/us-east-1", "mac2/us-east-1", "mac1/us-east-1"]
    utilization = [0.95, 0.95, 0.65, 0.48, 0.18]
    colors = ["#d62728" if u >= 0.85 else "#2ca02c" if u >= 0.4 else "#ff7f0e" for u in utilization]

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(pools, utilization, color=colors)
    ax.axhline(0.85, linestyle="--", color="gray", label="0.85 pre-event threshold")
    ax.set_ylabel("Utilization")
    ax.set_title("EC2 Mac Fleet Utilization by Pool")
    ax.set_ylim(0, 1.0)
    ax.legend()
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(CHART_PATH, dpi=90)
    return True


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first:  export ANTHROPIC_API_KEY=sk-ant-...")

    if not make_chart():
        raise SystemExit("This demo needs matplotlib for the chart:  pip install matplotlib")
    print(f"Generated {CHART_PATH}\n")

    client = anthropic.Anthropic()

    # Read the image and base64-encode it - that's how an image goes into a message.
    with open(CHART_PATH, "rb") as f:
        image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=(
            "You are a supply-chain demand-planning analyst for the AWS EC2 Mac "
            "instance family. Pools at or above 0.85 utilization are one spike from "
            "queueing builds; below 0.40 sustained is over-provisioned."
        ),
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                },
                {"type": "text", "text": "Read this utilization chart. Which pools are at risk, "
                                         "which are over-provisioned, and what should I prioritize?"},
            ],
        }],
    )

    answer = next((b.text for b in response.content if b.type == "text"), "")
    print("=" * 64)
    print("CLAUDE READING THE CHART")
    print("=" * 64)
    print(answer.strip())


if __name__ == "__main__":
    main()
