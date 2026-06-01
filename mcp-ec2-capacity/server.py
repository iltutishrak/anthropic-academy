"""
server.py — an MCP server for EC2 Mac capacity intelligence.

This is the same forecasting capability from the Building-with-the-Claude-API
track, but exposed as a Model Context Protocol (MCP) server instead of baked into
one app. The difference is portability: any MCP-compatible host (Claude Code,
Claude Desktop, Cursor, ...) can plug into this server and use these tools. Write
once, plug in anywhere.

This server exposes TOOLS — functions the model can call. (The advanced track adds
resources and prompts.) It speaks MCP over stdio: the host launches it as a
subprocess and talks to it on stdin/stdout.

Setup:
    pip install "mcp[cli]"

Try it with the MCP Inspector (a UI for poking at your server):
    mcp dev server.py

Register it into Claude Code so its tools are available in your sessions:
    claude mcp add ec2-mac -- python3 "$(pwd)/server.py"

Then ask Claude (in a host that has it): "What's the demand forecast for
mac2-m2.metal in eu-west-1, and is capacity enough?" — and it will call these
tools.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


# The server. The name is how hosts identify it.
mcp = FastMCP("ec2-mac-capacity")


# Mock capacity data (same as the API-track demos). In production these tools
# would query a real forecasting service and capacity database.
_BASELINE_PEAK_HOSTS = {
    ("mac2-m2.metal", "us-east-1"): 220,
    ("mac2-m2.metal", "us-west-2"): 180,
    ("mac2-m2.metal", "eu-west-1"): 70,
    ("mac2-m2pro.metal", "us-east-1"): 95,
    ("mac2.metal", "us-east-1"): 140,
    ("mac1.metal", "us-east-1"): 40,
}
_ALLOCATED_HOSTS = {
    ("mac2-m2.metal", "us-east-1"): 260,
    ("mac2-m2.metal", "us-west-2"): 240,
    ("mac2-m2.metal", "eu-west-1"): 80,
    ("mac2-m2pro.metal", "us-east-1"): 110,
    ("mac2.metal", "us-east-1"): 200,
    ("mac1.metal", "us-east-1"): 120,
}


# The @mcp.tool() decorator turns a plain Python function into an MCP tool. The
# docstring becomes the tool's description, and the type hints become its input
# schema — the same schema Claude reads to know how to call it. The model decides
# when to call it; MCP handles the wiring.

@mcp.tool()
def get_demand_forecast(instance_type: str, region: str, horizon_weeks: int = 4) -> dict:
    """Forecast peak concurrent EC2 Mac hosts for an instance type in a region.

    Call this when asked about future demand, how many hosts will be needed, or
    upcoming capacity. Returns a per-week forecast with an event-uplift bump.
    """
    base = _BASELINE_PEAK_HOSTS.get((instance_type, region))
    if base is None:
        return {"error": f"no baseline for {instance_type} in {region}"}
    weeks = []
    for w in range(1, max(1, horizon_weeks) + 1):
        uplift = 2.0 if w == 3 else 1.0 + 0.04 * w  # week 3 = simulated iOS GA spike
        weeks.append({"week": w, "forecast_peak_hosts": round(base * uplift)})
    return {
        "instance_type": instance_type,
        "region": region,
        "baseline_peak_hosts": base,
        "weeks": weeks,
        "note": "Week 3 carries a 2.0x event uplift (simulated iOS GA window).",
    }


@mcp.tool()
def get_capacity(instance_type: str, region: str) -> dict:
    """Get current allocated hosts, in-use hosts, and utilization for a pool.

    Call this when asked about current capacity, utilization, headroom, or whether
    a pool is at risk of queueing builds.
    """
    allocated = _ALLOCATED_HOSTS.get((instance_type, region))
    base = _BASELINE_PEAK_HOSTS.get((instance_type, region))
    if allocated is None or base is None:
        return {"error": f"no capacity data for {instance_type} in {region}"}
    return {
        "instance_type": instance_type,
        "region": region,
        "allocated_hosts": allocated,
        "current_peak_in_use": base,
        "utilization": round(base / allocated, 2),
        "headroom_hosts": allocated - base,
    }


if __name__ == "__main__":
    # Run over stdio — the host launches this process and talks on stdin/stdout.
    mcp.run()
