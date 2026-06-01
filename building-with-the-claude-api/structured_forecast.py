"""
structured_forecast.py

Turning Claude's analysis into typed, validated data instead of prose.

This is the companion to ec2_mac_forecaster.py and the single most important
feature for building real products on the Claude API: structured outputs. Instead
of getting back a paragraph you have to parse with fragile string-matching, you
hand Claude a schema and the response is GUARANTEED to match it - validated and
typed, every time.

Theme stays the same: an EC2 Mac capacity recommendation. But here the output is a
machine-usable ForecastReport object your code (a dashboard, an alerting system, an
auto-scaler) could act on directly.

    pip install "anthropic" pydantic
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 structured_forecast.py

Key is read from the environment, never hardcoded.
"""

from __future__ import annotations

import os
from enum import Enum

import anthropic
from pydantic import BaseModel, Field


MODEL = "claude-opus-4-8"


# ============================================================================ #
#  THE SCHEMA
#
#  This Pydantic model IS the contract. Claude's response is constrained to fit
#  it exactly - the SDK validates the JSON against this before handing it back, so
#  downstream code can rely on the shape. Enums limit fields to known values, so
#  you never get "kinda high" where you expected "high".
# ============================================================================ #

class RiskLevel(str, Enum):
    low = "low"
    moderate = "moderate"
    high = "high"


class Action(str, Enum):
    grow_pool = "grow_pool"
    hold = "hold"
    drawdown = "drawdown"
    pre_allocate_for_event = "pre_allocate_for_event"


class ForecastReport(BaseModel):
    instance_type: str = Field(description="EC2 Mac instance type assessed")
    region: str = Field(description="AWS region assessed")
    risk_level: RiskLevel = Field(description="Overall capacity risk")
    recommended_action: Action = Field(description="The single primary action to take")
    recommended_buffer_pct: int = Field(description="Buffer to hold above forecast peak, percent")
    rationale: str = Field(description="One or two sentences tying the call to the numbers")
    confidence: float = Field(description="0.0 to 1.0 confidence in this recommendation")


# A compact snapshot we hand Claude in the prompt. In production this would come
# from your forecasting service + capacity DB (the tools in ec2_mac_forecaster.py).
SNAPSHOT = """\
Pool: mac2-m2.metal in eu-west-1
- Trailing 8-week median weekday peak: 70 hosts
- Allocated hosts: 80  (utilization 0.88)
- 4-week forecast peak hosts: [73, 76, 140, 78]  (week 3 = simulated iOS GA, 2.0x uplift)
- Handbook policy: eu-west-1 is a thin pool; hold >=25% buffer; never same-day drawdown
  (24-hour host allocation floor makes rapid drawdown wasteful).
"""

SYSTEM = (
    "You are a supply-chain demand-planning analyst for the AWS EC2 Mac instance "
    "family. Assess the capacity snapshot and return a single structured "
    "recommendation. Apply the handbook policy in the snapshot. Be decisive."
)


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "Set ANTHROPIC_API_KEY first:  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "(Read from the environment; never stored in this file.)"
        )

    client = anthropic.Anthropic()

    # messages.parse() is the structured-output helper: pass a Pydantic model as
    # output_format and it returns a validated instance on .parsed_output.
    response = client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Assess this pool:\n\n{SNAPSHOT}"}],
        output_format=ForecastReport,
    )

    report = response.parsed_output  # a real ForecastReport, not a string

    # Because it's typed, downstream code can use it directly - no parsing, no
    # guessing. This is what makes Claude wireable into a real system.
    print("=" * 64)
    print("STRUCTURED FORECAST REPORT  (validated ForecastReport object)")
    print("=" * 64)
    print(f"  pool            : {report.instance_type} / {report.region}")
    print(f"  risk_level      : {report.risk_level.value}")
    print(f"  recommended     : {report.recommended_action.value}")
    print(f"  buffer_pct      : {report.recommended_buffer_pct}%")
    print(f"  confidence      : {report.confidence:.0%}")
    print(f"  rationale       : {report.rationale}")
    print()

    # Proof it's real structured data: branch on it like any object.
    if report.risk_level == RiskLevel.high:
        print("  -> ALERT: high risk. An auto-scaler could trigger pre-allocation here.")
    print(f"  -> JSON your API could return verbatim:\n{report.model_dump_json(indent=2)}")


if __name__ == "__main__":
    main()
