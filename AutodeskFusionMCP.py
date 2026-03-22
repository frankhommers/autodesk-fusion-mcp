# -*- coding: utf-8 -*-
"""
Autodesk Fusion MCP - Add-in entry point.

Starts a standalone MCP server inside Autodesk Fusion that allows
AI agents (Claude, etc.) to control Fusion directly.
"""


def run(context):
    """Entry point - Fusion calls this when the add-in starts."""
    try:
        from . import addon_runtime

        addon_runtime.run(context)
    except Exception as e:
        print(f"[AutodeskFusionMCP] Failed to start: {e}")
        import traceback

        traceback.print_exc()


def stop(context):
    """Shutdown - Fusion calls this when the add-in stops."""
    try:
        from . import addon_runtime

        addon_runtime.stop(context)
    except Exception as e:
        print(f"[AutodeskFusionMCP] Error during shutdown: {e}")
