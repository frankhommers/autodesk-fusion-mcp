# Log Timestamps and Command Duration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prefix every bridge log line with an ISO 8601 local timestamp, and log how long each MCP tool command took to run.

**Architecture:** Two changes, both in the project's own bridge code (the vendored `lib/fusionAddInUtils/general_utils.py` is frozen by a hash test and must not change). Timestamps are added at the single logging chokepoint `fusion_bridge/dispatch.py:log()`. Per-command duration is added at the single command chokepoint `fusion_bridge/runtime.py:handle_any_tool()`, which is promoted from a nested closure to a module-level function so it can be unit-tested.

**Tech Stack:** Python 3.12, `unittest` (CI runs `python -m unittest discover -s tests`), stdlib `datetime` and `time.perf_counter`.

**Design doc:** `docs/plans/2026-06-16-log-timestamps-and-command-duration-design.md`

---

## Background the executor must know

- All bridge logging funnels through `fusion_bridge/dispatch.py:log()` → `lib/fusionAddInUtils/general_utils.py:log()` → `print()`. The MCP server's logs also route here via `log_callback=log` (`fusion_bridge/runtime.py:46`).
- `dispatch.log()` runs immediately on the main thread, but **defers** background-thread messages into `_deferred_messages` for later replay by `drain_logs()`. Timestamps must therefore be applied **at log-call time** (before deferring), not at flush time.
- Every MCP tool executes through `handle_any_tool()` in `runtime.py`, currently a closure nested inside `create_server()`. It calls `handler(call_data)` on the Fusion main thread for all 11 tools.
- Tool handlers return an envelope dict like `{"content": [...], "isError": bool}`. An exception from a handler propagates up to `dispatch._flush_pending`, which formats it; this propagation must be preserved.
- Tests cannot `import adsk` (only exists inside Fusion). The existing `tests/test_tool_contract.py` installs a mock `adsk` plus a synthetic `_addin_root` parent package (its lines 22–144) before importing `fusion_bridge`. The CI runner is `unittest` (not pytest), so a `conftest.py` would NOT run — shared setup must be an importable module. `tests/` has no `__init__.py`, so sibling modules import by bare name.

---

## Task 1: Extract a shared test bootstrap module

**Why:** New tests need the same mock-`adsk` + parent-package shim as `test_tool_contract.py`. Extract it once (DRY) so both files share it.

**Files:**
- Create: `tests/_fusion_test_bootstrap.py`
- Modify: `tests/test_tool_contract.py`

**Step 1: Create the shared bootstrap module**

Create `tests/_fusion_test_bootstrap.py` containing the environment setup currently inline in `tests/test_tool_contract.py`. Move the block that is **lines 5–144** of `tests/test_tool_contract.py` (from `ROOT = pathlib.Path(...)` through the end of the `_addin_root` package shim that ends with `_root_pkg.fusion_bridge = _fb`). Prepend the needed imports. The file must be:

```python
"""Shared test bootstrap: install a mock ``adsk`` package and a synthetic
parent package so ``fusion_bridge`` relative imports resolve outside Fusion.

Importing this module for its side effects is enough:

    import _fusion_test_bootstrap  # noqa: F401

All setup is idempotent (``setdefault`` / ``if name not in sys.modules``), so it
is safe to import alongside any other copy of the same bootstrap.
"""

import importlib
import pathlib
import sys
import types

# <<< paste lines 11-144 of the original tests/test_tool_contract.py here,
#     i.e. everything from `ROOT = pathlib.Path(__file__).resolve().parents[1]`
#     through `_root_pkg.fusion_bridge = _fb`. Do NOT include the test-specific
#     `from fusion_bridge import tool_surface` / `from lib.mcp_server import MCPServer`
#     lines (those stay in the test file). >>>
```

`pathlib.Path(__file__).resolve().parents[1]` still resolves to the repo root because this module also lives in `tests/`.

**Step 2: Refactor `tests/test_tool_contract.py` to use it**

Replace the moved block (original lines 5–144) with a single import placed before any `fusion_bridge`/`lib` import. The top of the file becomes:

```python
"""Verify the public MCP tool surface: operation names, field names, and
schema structure.  No reference to old / renamed identifiers and no
source-tree scanning tricks."""

import unittest

import _fusion_test_bootstrap  # noqa: F401  (installs adsk mock + parent pkg shim)

from fusion_bridge import tool_surface
from lib.mcp_server import MCPServer
```

Leave every test class below unchanged.

**Step 3: Verify the existing suite still passes**

Run: `python -m unittest discover -s tests -v`
Expected: PASS — same tests as before (tool-surface, resource, multi-tool, operations-registry, vendor-freeze), no errors or import failures.

**Step 4: Commit**

```bash
git add tests/_fusion_test_bootstrap.py tests/test_tool_contract.py
git commit -m "Extract shared adsk-mock test bootstrap"
```

---

## Task 2: Adaptive duration formatter

**Files:**
- Modify: `fusion_bridge/dispatch.py`
- Create: `tests/test_command_timing.py`

**Step 1: Write the failing test**

Create `tests/test_command_timing.py`:

```python
"""Tests for log timestamps and per-command duration logging."""

import re
import threading
import unittest

import _fusion_test_bootstrap  # noqa: F401  (installs adsk mock + parent pkg shim)

from fusion_bridge import dispatch


class FormatDurationTests(unittest.TestCase):
    def test_sub_millisecond_shows_zero_ms(self):
        self.assertEqual(dispatch.format_duration(0), "0ms")

    def test_under_one_second_shows_integer_ms(self):
        self.assertEqual(dispatch.format_duration(122), "122ms")
        self.assertEqual(dispatch.format_duration(999), "999ms")

    def test_one_second_boundary_shows_seconds(self):
        self.assertEqual(dispatch.format_duration(1000), "1.00s")

    def test_large_value_shows_seconds_two_decimals(self):
        self.assertEqual(dispatch.format_duration(4520), "4.52s")
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p "test_command_timing.py" -v`
Expected: FAIL with `AttributeError: module 'fusion_bridge.dispatch' has no attribute 'format_duration'`.

**Step 3: Implement `format_duration`**

In `fusion_bridge/dispatch.py`, add after the existing imports (the file already imports `queue`, `threading`, `traceback`, `adsk.core`, `futil`):

```python
from datetime import datetime
```

Then add this helper in the "Thread-safe logging" section, above `def log(`:

```python
def format_duration(elapsed_ms):
    """Human-readable elapsed time.

    Under one second -> integer milliseconds (e.g. ``122ms``);
    one second or longer -> seconds with two decimals (e.g. ``4.52s``).
    """
    if elapsed_ms < 1000:
        return f"{elapsed_ms:.0f}ms"
    return f"{elapsed_ms / 1000:.2f}s"
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p "test_command_timing.py" -v`
Expected: PASS (4 tests in `FormatDurationTests`).

**Step 5: Commit**

```bash
git add fusion_bridge/dispatch.py tests/test_command_timing.py
git commit -m "Add adaptive duration formatter"
```

---

## Task 3: Timestamp every log line

**Files:**
- Modify: `fusion_bridge/dispatch.py:40-46` (the `log` function)
- Modify: `tests/test_command_timing.py`

**Step 1: Write the failing test**

Append to `tests/test_command_timing.py`:

```python
ISO_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3} ")


class LogTimestampTests(unittest.TestCase):
    def setUp(self):
        # Capture whatever dispatch hands to the underlying futil.log.
        self._captured = []
        self._orig_futil_log = dispatch.futil.log
        dispatch.futil.log = lambda *a, **kw: self._captured.append(a[0])
        # Isolate the deferred-message queue from other tests.
        with dispatch._msg_lock:
            dispatch._deferred_messages.clear()

    def tearDown(self):
        dispatch.futil.log = self._orig_futil_log
        with dispatch._msg_lock:
            dispatch._deferred_messages.clear()

    def test_main_thread_message_is_timestamped(self):
        dispatch.log("hello")
        self.assertEqual(len(self._captured), 1)
        self.assertRegex(self._captured[0], ISO_PREFIX_RE)
        self.assertTrue(self._captured[0].endswith(" hello"))

    def test_deferred_message_is_timestamped_at_log_time(self):
        # A background thread defers the message; nothing is logged yet.
        worker = threading.Thread(target=lambda: dispatch.log("deferred"))
        worker.start()
        worker.join()
        self.assertEqual(self._captured, [])
        # Flushing replays the already-stamped message.
        dispatch.drain_logs()
        self.assertEqual(len(self._captured), 1)
        self.assertRegex(self._captured[0], ISO_PREFIX_RE)
        self.assertTrue(self._captured[0].endswith(" deferred"))
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p "test_command_timing.py" -k Timestamp -v`
Expected: FAIL — captured messages are `"hello"` / `"deferred"` without the ISO prefix, so `assertRegex` fails.

**Step 3: Implement timestamping in `log`**

Replace the body of `log` in `fusion_bridge/dispatch.py` (currently lines 40-46):

```python
def log(message: str, level=None):
    """Log immediately on the main thread, or defer for later flushing.

    The message is timestamped at call time so deferred (background-thread)
    lines reflect when they were logged, not when they were flushed.
    """
    stamped = f"{datetime.now().isoformat(timespec='milliseconds')} {message}"
    if threading.current_thread() is threading.main_thread():
        futil.log(stamped) if level is None else futil.log(stamped, level)
        return
    with _msg_lock:
        _deferred_messages.append((stamped, level))
```

`drain_logs()` is unchanged: it already replays the stored (now pre-stamped) strings.

**Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p "test_command_timing.py" -k Timestamp -v`
Expected: PASS (2 tests).

**Step 5: Commit**

```bash
git add fusion_bridge/dispatch.py tests/test_command_timing.py
git commit -m "Prefix log lines with ISO 8601 timestamp"
```

---

## Task 4: Log per-command execution duration

**Files:**
- Modify: `fusion_bridge/runtime.py` (promote `handle_any_tool` to module level, add timing)
- Modify: `tests/test_command_timing.py`

**Step 1: Write the failing test**

Append to `tests/test_command_timing.py`:

```python
from fusion_bridge import operations, runtime


class HandleAnyToolTimingTests(unittest.TestCase):
    TOOL = "__timing_test_tool__"

    def setUp(self):
        self._logs = []
        self._orig_log = runtime.log
        runtime.log = lambda message, *a, **kw: self._logs.append(message)
        self._had_tool = self.TOOL in operations.TOOL_HANDLERS
        self._saved = operations.TOOL_HANDLERS.get(self.TOOL)

    def tearDown(self):
        runtime.log = self._orig_log
        if self._had_tool:
            operations.TOOL_HANDLERS[self.TOOL] = self._saved
        else:
            operations.TOOL_HANDLERS.pop(self.TOOL, None)

    def _call(self):
        return runtime.handle_any_tool(
            {"params": {"name": self.TOOL, "arguments": {}}}
        )

    def test_successful_call_logs_completed_with_duration(self):
        operations.TOOL_HANDLERS[self.TOOL] = lambda cd: {"content": [], "isError": False}
        result = self._call()
        self.assertFalse(result["isError"])
        self.assertEqual(len(self._logs), 1)
        self.assertRegex(
            self._logs[0],
            r"^\[MCP\] " + re.escape(self.TOOL) + r" completed in \d",
        )

    def test_error_result_logs_failed(self):
        operations.TOOL_HANDLERS[self.TOOL] = lambda cd: {"content": [], "isError": True}
        self._call()
        self.assertIn("failed in", self._logs[0])

    def test_exception_propagates_and_logs_failed(self):
        def boom(cd):
            raise ValueError("boom")

        operations.TOOL_HANDLERS[self.TOOL] = boom
        with self.assertRaises(ValueError):
            self._call()
        self.assertEqual(len(self._logs), 1)
        self.assertIn("failed in", self._logs[0])

    def test_unknown_tool_returns_error_without_timing_line(self):
        result = runtime.handle_any_tool(
            {"params": {"name": "no_such_tool", "arguments": {}}}
        )
        self.assertTrue(result["isError"])
        self.assertEqual(self._logs, [])
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p "test_command_timing.py" -k Timing -v`
Expected: FAIL with `AttributeError: module 'fusion_bridge.runtime' has no attribute 'handle_any_tool'` (it is currently a nested closure).

**Step 3: Promote `handle_any_tool` to module level and add timing**

In `fusion_bridge/runtime.py`:

(a) Add `import time` near the top (with the other imports, e.g. after `import traceback`).

(b) Add `format_duration` to the existing `from .dispatch import (...)` block so it reads:

```python
from .dispatch import (
    dispatch_to_main_thread,
    drain_logs,
    format_duration,
    get_shutdown_flag,
    init_main_thread_dispatch,
    log,
    set_tool_handler,
    stop_main_thread_dispatch,
)
```

(c) Add a module-level function (place it just above `def create_server():`):

```python
def handle_any_tool(call_data):
    """Route to the correct handler based on tool name, timing execution."""
    from . import operations

    tool_name = call_data.get("params", {}).get("name", "")
    handler = operations.TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
            "isError": True,
        }

    start = time.perf_counter()
    result = None
    try:
        result = handler(call_data)
        return result
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        is_error = result is None or (
            isinstance(result, dict) and result.get("isError")
        )
        status = "failed" if is_error else "completed"
        log(f"[MCP] {tool_name} {status} in {format_duration(elapsed_ms)}")
```

(d) Delete the nested `def handle_any_tool(...)` block inside `create_server()` (original `runtime.py:27-36`). Keep the `from . import operations` line at the top of `create_server` (it is still used at the `tool_handlers={name: ... for name in operations.TOOL_HANDLERS}` line) and keep the `set_tool_handler(handle_any_tool)` call, which now refers to the module-level function.

**Step 4: Run the timing tests, then the whole file**

Run: `python -m unittest discover -s tests -p "test_command_timing.py" -k Timing -v`
Expected: PASS (4 tests).

Run: `python -m unittest discover -s tests -p "test_command_timing.py" -v`
Expected: PASS (all 10 tests: 4 formatter + 2 timestamp + 4 timing).

**Step 5: Commit**

```bash
git add fusion_bridge/runtime.py tests/test_command_timing.py
git commit -m "Log per-command execution duration"
```

---

## Task 5: Final verification

**Step 1: Run the full suite exactly as CI does**

Run: `python -m unittest discover -s tests`
Expected: PASS — all tests across `test_command_timing.py`, `test_tool_contract.py`, and `test_autodesk_vendor_freeze.py`. The vendor-freeze test confirms `general_utils.py` was not touched.

**Step 2: Quick manual sanity check (optional)**

Run:
```bash
python -c "import sys; sys.path.insert(0,'tests'); import _fusion_test_bootstrap; from fusion_bridge import dispatch; dispatch.log('sanity check'); print('->', dispatch.format_duration(42), dispatch.format_duration(1500))"
```
Expected: a line like `2026-06-16T14:23:01.123 sanity check` followed by `-> 42ms 1.50s`.

**Step 3: Confirm clean tree**

Run: `git status`
Expected: nothing to commit, working tree clean (all changes committed across Tasks 1-4).

---

## Notes / out of scope

- A few non-bridge lines remain un-stamped by design: top-level `print()` in `AutodeskFusionMCP.py`, `handle_error()` direct `futil.log()` calls, and the standalone `test_server.py` harness. These sit outside the bridge chokepoint.
- Duration is logged once per command in `handle_any_tool`; the pre-existing `[MCP] Tool call: ...` line in `operations.py:82` (generic API only) is left as-is.
