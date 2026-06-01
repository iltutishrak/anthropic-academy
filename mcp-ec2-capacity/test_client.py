"""
test_client.py — a tiny MCP client that talks to server.py.

`mcp dev` (the Inspector) needs Node.js. This is the pure-Python alternative, and
it teaches more: it shows the CLIENT side of MCP. It launches server.py as a
subprocess over stdio, does the MCP handshake, lists the tools the server exposes,
and calls one — exactly what a host like Claude Code does under the hood.

    pip install "mcp[cli]"
    python3 test_client.py
"""

import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    # Tell the client how to launch our server (host launches server as subprocess).
    server = StdioServerParameters(command="python3", args=["server.py"])

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            # 1. MCP handshake.
            await session.initialize()

            # 2. Discover what the server exposes — this is how a host learns the
            #    tools without you hardcoding them anywhere.
            tools = await session.list_tools()
            print("=" * 60)
            print("TOOLS THIS SERVER EXPOSES")
            print("=" * 60)
            for t in tools.tools:
                print(f"  - {t.name}: {t.description.splitlines()[0]}")

            # 3. Call a tool, just like the model would.
            print("\n" + "=" * 60)
            print("CALLING get_demand_forecast(mac2-m2.metal, eu-west-1)")
            print("=" * 60)
            result = await session.call_tool(
                "get_demand_forecast",
                {"instance_type": "mac2-m2.metal", "region": "eu-west-1"},
            )
            for block in result.content:
                if block.type == "text":
                    print(json.dumps(json.loads(block.text), indent=2))

            # 4. And the capacity tool.
            print("\n" + "=" * 60)
            print("CALLING get_capacity(mac2-m2.metal, eu-west-1)")
            print("=" * 60)
            result = await session.call_tool(
                "get_capacity",
                {"instance_type": "mac2-m2.metal", "region": "eu-west-1"},
            )
            for block in result.content:
                if block.type == "text":
                    print(json.dumps(json.loads(block.text), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
