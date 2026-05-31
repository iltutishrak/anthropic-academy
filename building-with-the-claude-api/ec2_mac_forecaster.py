"""
ec2_mac_forecaster.py

A supply-chain demand-forecasting and intelligence assistant for the AWS EC2 Mac
instance family, built on the Claude API. One file, written to be read.

I built this for the Anthropic Academy "Building with the Claude API" track. It
demonstrates, end to end, the things that course teaches:

  1. the Messages API           -> the one endpoint everything goes through
  2. a system prompt            -> the "Role" block, given its own field
  3. multi-turn history         -> the API is STATELESS; we resend the transcript
  4. streaming                  -> tokens arrive as they're generated
  5. tool use                   -> Claude calls get_demand_forecast / get_capacity,
                                   we run them, hand back results, it continues
  6. prompt caching             -> the big static "capacity handbook" is cached so
                                   we don't reprocess it every turn
  7. extended (adaptive) thinking -> Claude reasons before answering hard questions

The key idea I learned and wanted to make concrete: the model has no memory, can't
fetch live data on its own, and is expensive to re-feed. Every feature here is a
direct answer to one of those limits.

Setup (never hardcode the key):
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 ec2_mac_forecaster.py

The key is read from the ANTHROPIC_API_KEY environment variable by the SDK. It is
never written in this file.
"""

from __future__ import annotations

import json
import os

import anthropic


# Default to the most capable model. Swap to "claude-sonnet-4-6" or
# "claude-haiku-4-5" if you want cheaper/faster runs while learning.
MODEL = "claude-opus-4-8"


# ============================================================================ #
#  PART 1 - THE CACHED CONTEXT ("the capacity handbook")
#
#  This is a large, STATIC block of domain knowledge. It never changes between
#  turns, so it is the perfect thing to mark for prompt caching: Claude processes
#  it once, then reuses it on every later call at ~10% of the cost. In a real
#  product this would be your runbooks, product docs, or policy manuals.
#
#  Caching note: caching only kicks in above the model's minimum cacheable prefix
#  (~4096 tokens for Opus 4.8). Watch usage.cache_creation_input_tokens in the
#  output: if it's 0, this handbook is below the threshold and won't cache. That
#  is itself a real lesson - in production your cached context is usually far
#  larger than this demo's.
# ============================================================================ #

CAPACITY_HANDBOOK = """\
# EC2 Mac Instance Family - Capacity & Demand Planning Handbook

## 1. The instance family
AWS EC2 Mac instances are dedicated Mac mini hosts rented on a per-host basis.
They are unique in the EC2 fleet: each is a physical Apple machine, allocated to a
single tenant on a Dedicated Host, with a mandatory 24-hour minimum host
allocation period before the host can be released. This 24-hour floor is the
single most important fact in capacity planning for this family - you cannot
rapidly scale a host pool up and down the way you can with virtualized instances.

Instance types in scope for this handbook:
- mac1.metal     : Intel x86, Mac mini (2018). Legacy, declining demand.
- mac2.metal     : Apple M1, Mac mini (2020). Mature, steady demand.
- mac2-m2.metal  : Apple M2, Mac mini (2023). Growing demand, primary build fleet.
- mac2-m2pro.metal : Apple M2 Pro, Mac mini (2023). High-end CI, bursty demand.

## 2. Who uses these and why
The dominant workload is iOS / macOS continuous integration and build farms. Apple
requires builds for the App Store to be produced on Apple hardware, so any company
shipping an iPhone or Mac app needs Mac build capacity. Secondary workloads:
Xcode-based test automation, Safari web compatibility testing, and Apple-silicon
performance benchmarking.

The demand shape that follows from this is strongly weekday-business-hours, with
sharp spikes around major Apple events (WWDC in June, September iPhone launch) when
every app developer scrambles to rebuild against new OS betas. Plan for 2x to 3x
baseline demand in the two weeks following a major iOS beta release.

## 3. The capacity constraints that matter
- 24-hour minimum allocation: releasing a host you provisioned an hour ago still
  bills 24 hours. Over-provisioning is expensive and slow to unwind.
- Host warm-up: a freshly allocated Mac host needs scrubbing and re-imaging
  between tenants, so effective lead time to usable capacity is hours, not seconds.
- Regional scarcity: Mac hosts are physically racked and far scarcer than standard
  EC2. us-east-1 and us-west-2 carry the deepest pools; eu-west-1 is thinner and
  hits allocation limits first under spikes; other regions are best-effort.
- Apple-silicon migration: demand is steadily shifting off mac1 (Intel) onto the
  M-series. Treat mac1 demand as in structural decline and do not grow that pool.

## 4. Forecasting guidance
- Baseline on a trailing 8-week median of weekday peak concurrent hosts, not the
  mean - the mean is dragged down by weekends and holidays.
- Apply an event uplift multiplier for any week within 14 days of a known Apple
  release: 2.0x for a major iOS/macOS GA, 1.5x for a developer beta.
- Hold a buffer of at least 15% above forecast peak for the M-series pools, given
  their bursty CI nature, and at least 25% in eu-west-1 to absorb its thinner pool.
- Forecast in units of "peak concurrent hosts per region per instance type," since
  the 24-hour floor means host-count, not instance-hours, is the planning unit.

## 5. Reading a healthy vs at-risk signal
- Utilization sustained above 85% of allocated hosts in a region means you are one
  spike away from queueing builds. Pre-allocate before the next event window.
- Utilization below 40% sustained for 2+ weeks means an over-provisioned pool that
  is burning the 24-hour-floor premium. Plan a controlled drawdown.
- A rising ratio of mac2-m2pro to mac2-m2 requests signals heavier CI matrices
  (more parallel test targets) and usually precedes an overall demand step-up.

## 6. How to advise
When asked for a recommendation, always tie it back to: the trailing-median
baseline, the relevant event uplift, the regional buffer policy, and the 24-hour
allocation floor. Never recommend a same-day large drawdown - the floor makes it
wasteful. Prefer gradual, event-aware adjustments.
"""


# ============================================================================ #
#  PART 2 - THE TOOLS
#
#  Claude cannot know live forecast or capacity numbers (master key: it's strong
#  only when the info is IN the prompt). So we give it tools. When Claude needs a
#  number, it does not guess - it asks us to run get_demand_forecast or
#  get_capacity, we return real data, and it continues with grounded facts.
#
#  These implementations are mocked but deterministic, so the demo is reproducible.
#  In production they'd hit your forecasting service and capacity database.
# ============================================================================ #

# Mock data keyed by (instance_type, region). Numbers are illustrative.
_BASELINE_PEAK_HOSTS = {
    ("mac2-m2.metal", "us-east-1"): 220,
    ("mac2-m2.metal", "us-west-2"): 180,
    ("mac2-m2.metal", "eu-west-1"): 70,
    ("mac2-m2pro.metal", "us-east-1"): 95,
    ("mac2-m2pro.metal", "us-west-2"): 60,
    ("mac2.metal", "us-east-1"): 140,
    ("mac1.metal", "us-east-1"): 40,
}
_ALLOCATED_HOSTS = {
    ("mac2-m2.metal", "us-east-1"): 260,
    ("mac2-m2.metal", "us-west-2"): 240,
    ("mac2-m2.metal", "eu-west-1"): 80,
    ("mac2-m2pro.metal", "us-east-1"): 110,
    ("mac2-m2pro.metal", "us-west-2"): 95,
    ("mac2.metal", "us-east-1"): 200,
    ("mac1.metal", "us-east-1"): 120,
}


def get_demand_forecast(instance_type: str, region: str, horizon_weeks: int = 4) -> dict:
    """Forecast peak concurrent hosts for an instance type/region over N weeks.

    Returns a per-week list with a small event-uplift bump applied to illustrate
    the handbook's guidance. Deterministic for reproducibility."""
    base = _BASELINE_PEAK_HOSTS.get((instance_type, region))
    if base is None:
        return {"error": f"no baseline for {instance_type} in {region}"}
    weeks = []
    for w in range(1, max(1, horizon_weeks) + 1):
        # toy model: gentle growth + a synthetic event spike on week 3
        uplift = 2.0 if w == 3 else 1.0 + 0.04 * w
        weeks.append({"week": w, "forecast_peak_hosts": round(base * uplift)})
    return {
        "instance_type": instance_type,
        "region": region,
        "baseline_peak_hosts": base,
        "weeks": weeks,
        "note": "Week 3 carries a 2.0x event uplift (simulated iOS GA window).",
    }


def get_capacity(instance_type: str, region: str) -> dict:
    """Current allocated vs in-use hosts and utilization for an instance/region."""
    allocated = _ALLOCATED_HOSTS.get((instance_type, region))
    base = _BASELINE_PEAK_HOSTS.get((instance_type, region))
    if allocated is None or base is None:
        return {"error": f"no capacity data for {instance_type} in {region}"}
    utilization = base / allocated
    return {
        "instance_type": instance_type,
        "region": region,
        "allocated_hosts": allocated,
        "current_peak_in_use": base,
        "utilization": round(utilization, 2),
        "headroom_hosts": allocated - base,
    }


# JSON Schemas Claude reads to know HOW to call each tool. Descriptions are
# prescriptive about WHEN to call - recent Opus models reach for tools more
# conservatively, so spelling out the trigger condition improves call rate.
TOOLS = [
    {
        "name": "get_demand_forecast",
        "description": (
            "Forecast peak concurrent EC2 Mac hosts for an instance type in a "
            "region over a horizon. Call this whenever the user asks what demand "
            "will be, how many hosts will be needed, or about future capacity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instance_type": {
                    "type": "string",
                    "description": "e.g. mac2-m2.metal, mac2-m2pro.metal, mac2.metal, mac1.metal",
                },
                "region": {"type": "string", "description": "e.g. us-east-1, us-west-2, eu-west-1"},
                "horizon_weeks": {"type": "integer", "description": "Weeks to forecast, default 4"},
            },
            "required": ["instance_type", "region"],
        },
    },
    {
        "name": "get_capacity",
        "description": (
            "Get current allocated hosts, in-use hosts, and utilization for an "
            "instance type in a region. Call this whenever the user asks about "
            "current capacity, utilization, headroom, or whether a pool is at risk."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instance_type": {"type": "string", "description": "EC2 Mac instance type"},
                "region": {"type": "string", "description": "AWS region"},
            },
            "required": ["instance_type", "region"],
        },
    },
]

TOOL_FUNCTIONS = {
    "get_demand_forecast": get_demand_forecast,
    "get_capacity": get_capacity,
}


# The system prompt: a list of blocks. Block 1 is the role/instructions; block 2 is
# the big handbook with cache_control on it. The breakpoint on the last system
# block caches tools + system together, in render order (tools -> system).
SYSTEM = [
    {
        "type": "text",
        "text": (
            "You are a supply-chain demand-planning analyst for the AWS EC2 Mac "
            "instance family. You help capacity planners decide how many Mac hosts "
            "to allocate, where, and when. Ground every recommendation in the "
            "capacity handbook below and in live numbers from your tools. Be "
            "concrete: cite the forecast, the utilization, and the handbook policy "
            "you're applying. Lead with the recommendation, then the reasoning."
        ),
    },
    {
        "type": "text",
        "text": CAPACITY_HANDBOOK,
        "cache_control": {"type": "ephemeral"},  # <-- cache the stable handbook
    },
]


# ============================================================================ #
#  PART 3 - THE CONVERSATION LOOP
#
#  This is the agentic loop with streaming. For each user turn we:
#    - stream Claude's thinking + text so the user sees progress immediately,
#    - if Claude asked for tools, run them and feed results back, then loop,
#    - otherwise the turn is done.
#  The whole `messages` list is the conversation memory we maintain by hand,
#  because the API itself remembers nothing between calls.
# ============================================================================ #

def converse(client: anthropic.Anthropic, messages: list[dict]) -> None:
    """Run one user turn to completion, handling any tool calls along the way."""
    while True:
        with client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            # Adaptive thinking lets Claude decide how hard to think.
            # display="summarized" makes the reasoning visible (default is omitted).
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": "high"},
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        ) as stream:
            printed_thinking_header = printed_answer_header = False
            for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "thinking_delta":
                        if not printed_thinking_header:
                            print("\n  [thinking] ", end="", flush=True)
                            printed_thinking_header = True
                        print(event.delta.thinking, end="", flush=True)
                    elif event.delta.type == "text_delta":
                        if not printed_answer_header:
                            print("\n  [answer] ", end="", flush=True)
                            printed_answer_header = True
                        print(event.delta.text, end="", flush=True)
            final = stream.get_final_message()

        # Show the caching payoff: on later turns the handbook should read from
        # cache (cache_read_input_tokens > 0) instead of being reprocessed.
        u = final.usage
        print(
            f"\n  [usage] input={u.input_tokens} "
            f"cache_write={getattr(u, 'cache_creation_input_tokens', 0)} "
            f"cache_read={getattr(u, 'cache_read_input_tokens', 0)} "
            f"output={u.output_tokens}"
        )

        # Append Claude's full response (text + any tool_use blocks) to history.
        messages.append({"role": "assistant", "content": final.content})

        # Done if Claude isn't asking for a tool.
        if final.stop_reason != "tool_use":
            return

        # Otherwise run each requested tool and hand the results back.
        tool_results = []
        for block in final.content:
            if block.type == "tool_use":
                print(f"\n  [tool] {block.name}({json.dumps(block.input)})")
                result = TOOL_FUNCTIONS[block.name](**block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
        messages.append({"role": "user", "content": tool_results})
        # Loop: Claude now continues with the grounded numbers.


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "Set ANTHROPIC_API_KEY first:  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "(The key is read from the environment and never stored in this file.)"
        )

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    # The conversation memory. We start empty and grow it turn by turn.
    messages: list[dict] = []

    # A scripted multi-turn conversation that exercises both tools and shows the
    # cache warming up across turns. Each item is one user turn.
    user_turns = [
        "How does demand for mac2-m2.metal in us-east-1 look over the next 4 weeks, "
        "and is our current capacity there enough?",
        "What about eu-west-1 for the same instance type - any risk there?",
        "Given all that, what should I do about the M2 pools before the next iOS GA?",
    ]

    for i, user_text in enumerate(user_turns, 1):
        print("\n" + "=" * 72)
        print(f"USER TURN {i}: {user_text}")
        print("=" * 72)
        messages.append({"role": "user", "content": user_text})
        converse(client, messages)
        print()


if __name__ == "__main__":
    main()
