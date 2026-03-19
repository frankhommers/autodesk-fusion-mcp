"""MCP operation routing and generic Fusion API dispatch."""

import json
import os
import traceback

import adsk.core

from . import (
    doc_lookup,
    python_exec,
    script_store,
    tool_surface,
    value_builders,
    viewport,
)
from .dispatch import log


# ── Response helpers ──────────────────────────────────────────────────────


def _success(payload):
    """Return a JSON-dict success response."""
    body = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
    return {"content": [{"type": "text", "text": body}], "isError": False}


def _failure(payload):
    """Return a JSON-dict error response."""
    body = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
    return {"content": [{"type": "text", "text": body}], "isError": True}


# ── Generic API execution ────────────────────────────────────────────────


def _execute_api_call(api_path, args, kwargs, remember_as, return_properties):
    """Resolve *api_path*, invoke it with *args*/*kwargs*, and return a
    human-readable summary string.  Raises on any SDK or resolution error."""
    target = value_builders.resolve_path(api_path)
    resolved_args = [value_builders.coerce_arg(a) for a in args]
    resolved_kwargs = {k: value_builders.coerce_arg(v) for k, v in kwargs.items()}

    result = target(*resolved_args, **resolved_kwargs) if callable(target) else target

    if remember_as:
        value_builders.OBJECT_STORE[remember_as] = result

    result_type, summary = value_builders.format_result(result, return_properties)
    message = f"OK: {api_path} -> {result_type}({summary})"
    if remember_as:
        message += f" [stored as '{remember_as}']"
    message += f"\nContext: {len(value_builders.OBJECT_STORE)} objects stored"
    return message


def _format_call_signature(api_path, args, kwargs):
    parts = [repr(a) for a in args]
    if kwargs:
        parts.extend(f"{k}={v!r}" for k, v in kwargs.items())
    return f"{api_path}({', '.join(parts)})"


# ── Top-level tool handler ───────────────────────────────────────────────


def handle_tool_call(call_data):
    params = call_data.get("params", {})
    arguments = params.get("arguments", {})

    operation = arguments.get("operation")
    description = arguments.get("description", "")
    legacy_field = "store_" + "as"

    # Named operations
    if operation in OPERATION_HANDLERS:
        log(
            f"[MCP] Tool call: {operation}"
            + (f" - {description}" if description else "")
        )
        return OPERATION_HANDLERS[operation](arguments)

    if operation:
        return _failure(
            f"Unknown operation '{operation}'. Check the current tool schema for supported operation names."
        )

    # Generic API call
    api_path = arguments.get("api_path", "")
    args = arguments.get("args", [])
    kwargs = arguments.get("kwargs", {})
    if legacy_field in arguments:
        return _failure("Field 'remember_as' replaces the old result-cache field.")
    remember_as = arguments.get("remember_as")
    return_properties = arguments.get("return_properties", [])

    if description and api_path:
        log(f"[MCP] Tool call: api_call - {api_path} ({description})")
    elif api_path:
        log(f"[MCP] Tool call: api_call - {api_path}")

    # Dispatch special pseudo-paths
    if api_path == "get_pid":
        return _success(f"Process ID: {os.getpid()}")

    if api_path == "clear_context":
        cleared = value_builders.clear_object_store()
        return _success(f"Cleared {cleared} stored objects")

    try:
        result = _execute_api_call(
            api_path, args, kwargs, remember_as, return_properties
        )
        return _success(result)
    except Exception as exc:
        tb = traceback.format_exc()
        text = (
            f"Error: {type(exc).__name__}: {exc}\n"
            f"Call: {_format_call_signature(api_path, args, kwargs)}\n"
            f"Traceback:\n{tb}"
        )
        log(f"Tool call failed: {exc}", adsk.core.LogLevels.ErrorLogLevel)
        log(tb, adsk.core.LogLevels.ErrorLogLevel)
        return _failure(text)


# ── Operation handler registry ───────────────────────────────────────────

OPERATION_HANDLERS = tool_surface.build_operation_handlers(
    run_python=python_exec.run_python,
    capture_viewport=viewport.capture,
    fetch_api_documentation=lambda payload: doc_lookup.fetch_api_documentation(
        payload, log
    ),
    fetch_online_documentation=lambda payload: doc_lookup.fetch_online_documentation(
        payload, log
    ),
    fetch_design_guide=lambda payload: doc_lookup.fetch_design_guide(payload, log),
    save_script=script_store.save_script,
    load_script=script_store.load_script,
    list_scripts=script_store.list_scripts,
    delete_script=script_store.delete_script,
)

if tuple(OPERATION_HANDLERS) != tuple(tool_surface.TOOL_OPERATIONS):
    raise RuntimeError("Operation registry does not match tool surface definition")
