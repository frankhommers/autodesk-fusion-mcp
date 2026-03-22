# -*- coding: utf-8 -*-
"""Autodesk Fusion MCP add-in runtime wiring."""

from . import commands, settings
from .fusion_bridge import runtime as fusion_runtime
from .lib import fusionAddInUtils as futil


def run(context):
    del context
    try:
        fusion_runtime.log("Autodesk Fusion MCP starting...")
        fusion_runtime.log(f"  MCP_AUTO_CONNECT: {settings.MCP_AUTO_CONNECT}")
        fusion_runtime.log(f"  MCP_SERVER_PORT: {settings.MCP_SERVER_PORT}")
        if not fusion_runtime.start():
            fusion_runtime.log("ERROR: Autodesk Fusion MCP startup aborted")
            return
        commands.start()
        fusion_runtime.log("[OK] Autodesk Fusion MCP started")
    except Exception:
        futil.handle_error("run")


def stop(context):
    del context
    try:
        fusion_runtime.log("Autodesk Fusion MCP stopping...")
        fusion_runtime.stop()
        commands.stop()
        futil.clear_handlers()
        fusion_runtime.log("[OK] Autodesk Fusion MCP stopped")
    except Exception:
        futil.handle_error("stop")
