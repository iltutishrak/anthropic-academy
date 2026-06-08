# mcp-ec2-capacity — an MCP server

A Model Context Protocol server exposing EC2 Mac capacity-intelligence tools, built
for the Anthropic Academy "Introduction to MCP" track.

It takes the forecasting capability from the Building-with-the-Claude-API track and
exposes it as an MCP server instead of baking it into one app — so any MCP host
(Claude Code, Claude Desktop, Cursor) can plug in and use it. Write once, plug in
anywhere.

## What it exposes — all three MCP primitives

**Tools** (model-controlled functions):
- `get_demand_forecast(instance_type, region, horizon_weeks)` — per-week peak-host forecast
- `get_capacity(instance_type, region)` — current allocation, utilization, headroom

**Resources** (app/user-controlled data, read into context by URI):
- `handbook://capacity` — the capacity planning handbook (static reference)
- `pool://{instance_type}/{region}` — a live pool snapshot (templated)

**Prompts** (user-invoked reusable templates, like slash commands):
- `weekly_capacity_review(region)` — a full per-pool review instruction

The mental model: **tools are verbs** the model calls, **resources are nouns** the
host reads, **prompts are templates** the user triggers.

## How it works

`server.py` uses `FastMCP`. The `@mcp.tool()` decorator turns a typed Python
function into an MCP tool: the docstring becomes the description, the type hints
become the input schema. It speaks MCP over stdio — the host launches it as a
subprocess and talks on stdin/stdout.

## Run / test it

```bash
pip install "mcp[cli]"
```

**Poke at it with the MCP Inspector** (a UI to list and call the tools):
```bash
mcp dev server.py
```

**Register it into Claude Code** so its tools are live in your sessions:
```bash
claude mcp add ec2-mac -- python3 "$(pwd)/server.py"
```
Then in a Claude Code session: *"What's the demand forecast for mac2-m2.metal in
eu-west-1, and is current capacity enough?"* — Claude will call these tools.

Remove it with `claude mcp remove ec2-mac`.

## The lesson

Tool use (the API track) wires a tool into one app. MCP makes that tool portable
across every MCP-compatible host. This server is the same capability, now reusable.
