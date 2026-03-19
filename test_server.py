#!/usr/bin/env python3
"""Start the MCP server with a dummy tool handler for protocol testing.

Usage:
    python3 test_server.py

Then connect with MCP Inspector:
    npx @modelcontextprotocol/inspector --transport streamable-http http://localhost:8765/mcp
"""

import sys
import os

# Allow direct import of the lib package.
sys.path.insert(0, os.path.dirname(__file__))

from lib.mcp_server import MCPServer


def dummy_tool_handler(arguments: dict) -> dict:
    """Echo handler that returns whatever was sent."""
    return {
        "content": [{"type": "text", "text": f"echo: {arguments}"}],
        "isError": False,
    }


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9765
    server = MCPServer(
        port=port,
        tool_handler=dummy_tool_handler,
        tool_name="autodesk_fusion",
        tool_description="Autodesk Fusion MCP (test mode -- dummy handler)",
        log_callback=lambda msg: print(msg),
    )
    server.start()
    print()
    print(f"MCP server running at http://127.0.0.1:{port}/mcp")
    print()
    print("Connect with MCP Inspector:")
    print("  npx @modelcontextprotocol/inspector")
    print(f"  Then enter URL: http://127.0.0.1:{port}/mcp")
    print()
    print("Press Ctrl+C to stop.")
    try:
        server.server_thread.join()
    except KeyboardInterrupt:
        print("\nStopping...")
        server.stop()


if __name__ == "__main__":
    main()
