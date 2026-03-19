"""Python execution helpers and version metadata."""

import contextlib
import inspect
import io
import json
import os
import queue
import re
import threading
import time
import traceback
import urllib

import adsk.core
import adsk.fusion

from .. import settings
from ..lib import fusionAddInUtils as futil
from ..lib import mcp_server as mcp_server_module
from .dispatch import get_app


SCRIPT_SESSIONS = {}
_CACHED_VERSION_INFO = None


def get_addin_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_git_dirs(addin_dir):
    git_entry = os.path.join(addin_dir, ".git")
    if os.path.isdir(git_entry):
        git_dir = git_entry
    elif os.path.isfile(git_entry):
        with open(git_entry, "r", encoding="utf-8") as handle:
            raw = handle.read().strip()
        if not raw.startswith("gitdir:"):
            raise ValueError(f"Unsupported .git file format at {git_entry}")
        git_dir = raw.split(":", 1)[1].strip()
        if not os.path.isabs(git_dir):
            git_dir = os.path.normpath(os.path.join(addin_dir, git_dir))
    else:
        raise FileNotFoundError(f"Missing .git entry at {git_entry}")

    common_dir = git_dir
    commondir_file = os.path.join(git_dir, "commondir")
    if os.path.exists(commondir_file):
        with open(commondir_file, "r", encoding="utf-8") as handle:
            common_dir = handle.read().strip()
        if not os.path.isabs(common_dir):
            common_dir = os.path.normpath(os.path.join(git_dir, common_dir))

    return git_dir, common_dir


def _read_ref(git_dir, common_dir, ref_name):
    for base_dir in (git_dir, common_dir):
        ref_path = os.path.join(base_dir, ref_name)
        if os.path.exists(ref_path):
            with open(ref_path, "r", encoding="utf-8") as handle:
                return handle.read().strip()[:8]

    packed_refs = os.path.join(common_dir, "packed-refs")
    if os.path.exists(packed_refs):
        with open(packed_refs, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip().endswith(ref_name):
                    return line.split()[0][:8]

    return None


class MCPBridgeStub:
    def call(self, tool_name, arguments):
        del arguments
        return {
            "error": (
                "mcp.call() is not available in standalone mode. "
                f"Tool '{tool_name}' must be configured as a separate MCP server in Claude Desktop."
            )
        }


def create_mcp_bridge():
    return MCPBridgeStub()


def _build_runtime_globals():
    app = get_app()
    return {
        "__builtins__": __builtins__,
        "adsk": adsk,
        "app": app,
        "contextlib": contextlib,
        "futil": futil,
        "inspect": inspect,
        "io": io,
        "json": json,
        "mcp": create_mcp_bridge(),
        "mcp_server_module": mcp_server_module,
        "os": os,
        "queue": queue,
        "re": re,
        "settings": settings,
        "threading": threading,
        "time": time,
        "traceback": traceback,
        "ui": app.userInterface,
        "urllib": urllib,
    }


def run_python(arguments):
    code = arguments.get("code")
    if not code:
        return {
            "content": [{"type": "text", "text": "ERROR: 'code' parameter required"}],
            "isError": True,
        }

    session_id = arguments.get("session_id", "default")
    persistent = arguments.get("persistent", True)

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    try:
        runtime_globals = _build_runtime_globals()
        if persistent and session_id in SCRIPT_SESSIONS:
            runtime_globals.update(SCRIPT_SESSIONS[session_id])

        compiled = compile(code, "<mcp-script>", "exec")
        with (
            contextlib.redirect_stdout(stdout_buffer),
            contextlib.redirect_stderr(stderr_buffer),
        ):
            exec(compiled, runtime_globals)

        result_value = runtime_globals.pop("_mcp_result", None)

        if persistent:
            blocked = {
                "adsk",
                "app",
                "contextlib",
                "futil",
                "inspect",
                "io",
                "json",
                "mcp",
                "mcp_server_module",
                "os",
                "queue",
                "re",
                "settings",
                "threading",
                "time",
                "traceback",
                "ui",
                "urllib",
            }
            saved = {}
            for key, value in runtime_globals.items():
                if key.startswith("_") or key in blocked:
                    continue
                if (
                    inspect.ismodule(value)
                    or inspect.isfunction(value)
                    or callable(value)
                ):
                    continue
                saved[key] = value
            SCRIPT_SESSIONS[session_id] = saved

        payload = {
            "stdout": stdout_buffer.getvalue(),
            "stderr": stderr_buffer.getvalue(),
            "return_value": str(result_value) if result_value is not None else None,
            "session_variables": sorted(SCRIPT_SESSIONS.get(session_id, {}).keys())
            if persistent
            else [],
            "success": True,
        }
        return {
            "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
            "isError": False,
        }
    except Exception as exc:
        payload = {
            "stdout": stdout_buffer.getvalue(),
            "stderr": stderr_buffer.getvalue(),
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "success": False,
        }
        return {
            "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
            "isError": True,
        }


def get_version_info(addin_dir):
    global _CACHED_VERSION_INFO
    if _CACHED_VERSION_INFO is not None:
        return _CACHED_VERSION_INFO

    version = mcp_server_module.SERVER_INFO.get("version", "unknown")
    git_commit = None
    try:
        git_dir, common_dir = _resolve_git_dirs(addin_dir)
        head_file = os.path.join(git_dir, "HEAD")
        if os.path.exists(head_file):
            with open(head_file, "r", encoding="utf-8") as handle:
                head = handle.read().strip()
            if head.startswith("ref: "):
                ref_name = head[5:]
                git_commit = _read_ref(git_dir, common_dir, ref_name)
            else:
                git_commit = head[:8]
    except Exception as exc:
        futil.log(f"[version] git commit lookup failed: {exc}")

    _CACHED_VERSION_INFO = f"v{version} ({git_commit})" if git_commit else f"v{version}"
    return _CACHED_VERSION_INFO
