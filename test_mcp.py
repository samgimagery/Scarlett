"""
Test script to list MCP tools.
"""
import asyncio
import json
import sys
sys.path.insert(0, '.')

async def test():
    from mcp_client import MCPClient
    client = MCPClient()
    await client.start()
    
    # List available tools
    result = await client._send_request("tools/list", {})
    print("Available tools:")
    print(json.dumps(result, indent=2))
    
    await client.stop()

asyncio.run(test())