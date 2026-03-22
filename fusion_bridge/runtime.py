"""Fusion bridge server assembly and startup/shutdown wiring."""

import traceback

import adsk.core

from .. import settings
from ..lib import mcp_server as mcp_server_module
from . import doc_lookup, python_exec, tool_surface
from .dispatch import (
    dispatch_to_main_thread,
    drain_logs,
    get_shutdown_flag,
    init_main_thread_dispatch,
    log,
    set_tool_handler,
    stop_main_thread_dispatch,
)


_server = None


def create_server():
    from . import operations

    def handle_any_tool(call_data):
        """Route to the correct handler based on tool name in call_data."""
        tool_name = call_data.get("params", {}).get("name", "")
        handler = operations.TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return {
                "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                "isError": True,
            }
        return handler(call_data)

    set_tool_handler(handle_any_tool)

    server = mcp_server_module.MCPServer(
        port=settings.MCP_SERVER_PORT,
        tools=tool_surface.TOOL_DEFINITIONS,
        tool_handlers={
            name: dispatch_to_main_thread for name in operations.TOOL_HANDLERS
        },
        log_callback=log,
    )

    server.resources.append(
        {
            "uri": tool_surface.RESOURCE_URI,
            "name": tool_surface.RESOURCE_NAME,
            "description": tool_surface.RESOURCE_DESCRIPTION,
            "mimeType": "text/markdown",
            "content_fn": doc_lookup.read_design_guide,
        }
    )

    try:
        info = python_exec.get_version_info(python_exec.get_addin_dir())
        if "(" in info:
            server.git_commit = info.split("(")[1].rstrip(")")
    except Exception:
        pass

    return server


def _start_server():
    global _server

    if _server and _server.is_running:
        log("MCP server already running")
        return True

    log(f"Starting MCP server on port {settings.MCP_SERVER_PORT}...")
    attempt = 0
    shutdown_flag = get_shutdown_flag()
    while not shutdown_flag.is_set():
        try:
            _server = create_server()
            _server.start()
            break
        except OSError as exc:
            if "Address already in use" not in str(exc):
                raise
            attempt += 1
            delay = 2 if attempt <= 60 else min(2 ** (attempt - 60), 60)
            log(
                f"Port {settings.MCP_SERVER_PORT} busy, retrying in {delay}s (attempt {attempt})..."
            )
            shutdown_flag.wait(delay)
    else:
        log("MCP server start aborted (add-in stopping)")
        return False

    version_info = python_exec.get_version_info(python_exec.get_addin_dir())
    log(
        f"[SUCCESS] MCP server {version_info} running at http://127.0.0.1:{settings.MCP_SERVER_PORT}/mcp"
    )
    return True


def start():
    version_info = python_exec.get_version_info(python_exec.get_addin_dir())
    log(f"MCP Integration starting... {version_info}")

    try:
        init_main_thread_dispatch()
    except Exception as exc:
        log(
            f"ERROR: Failed to initialize main-thread dispatch: {exc}",
            adsk.core.LogLevels.ErrorLogLevel,
        )
        log(traceback.format_exc(), adsk.core.LogLevels.ErrorLogLevel)
        return False

    if settings.MCP_AUTO_CONNECT:
        try:
            if not _start_server():
                stop_main_thread_dispatch()
                return False
            log("MCP Integration started successfully")
        except Exception as exc:
            log(
                f"ERROR: Failed to start MCP server: {exc}",
                adsk.core.LogLevels.ErrorLogLevel,
            )
            log(traceback.format_exc(), adsk.core.LogLevels.ErrorLogLevel)
            stop_main_thread_dispatch()
            return False
    else:
        log("MCP_AUTO_CONNECT is False - MCP server disabled")
        log("Set MCP_AUTO_CONNECT = True in settings.py to enable")

    drain_logs()
    return True


def stop():
    global _server

    log("MCP Integration stopping...")
    stop_main_thread_dispatch()

    if _server:
        _server.stop()
        _server = None

    log("MCP Integration stopped")
    drain_logs()
