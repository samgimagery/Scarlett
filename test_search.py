"""Test MCP search directly."""
import asyncio
import json
import sys
sys.path.insert(0, '.')

async def test():
    from mcp_client import MCPClient
    client = MCPClient()
    await client.start()
    
    # Test search
    result = await client._send_request("tools/call", {
        "name": "search_notes",
        "arguments": {
            "query": "receptionist bot",
            "limit": 5,
            "threshold": 0.3
        }
    })
    print("Search result:")
    print(json.dumps(result, indent=2, default=str))
    
    await client.stop()

asyncio.run(test())