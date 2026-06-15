# Design: Log timestamps and command execution duration

Date: 2026-06-16

## Goal

Two small, related logging improvements:

1. Prefix every bridge log line with an ISO 8601 local timestamp.
2. Log how long each MCP tool command took to execute.

## Context

All project logging funnels through a single chokepoint:
`fusion_bridge/dispatch.py:log()` → `lib/fusionAddInUtils/general_utils.py:log()`
(vendored Autodesk template) → bare `print(message)`.

The MCP server's own logs also route through this same `log()` via the
`log_callback=log` wiring in `fusion_bridge/runtime.py:46`, so `[MCP-Server]`,
`JSON:`, `SSE:`, and `HTTP:` lines all pass through it.

Every MCP tool command executes through one chokepoint as well:
`handle_any_tool()` in `fusion_bridge/runtime.py:27-36`, which calls
`handler(call_data)` on the Fusion main thread for all 11 registered tools.

There is no timestamping and no duration measurement today. The vendored
`general_utils.py` should be left untouched (template code; changes get
clobbered on template updates).

## Chosen approach

Approach A: centralize both changes in the project's own bridge code.

- Timestamps in `fusion_bridge/dispatch.py:log()` (single log chokepoint).
- Duration in `fusion_bridge/runtime.py:handle_any_tool()` (single command
  chokepoint, covers all tools).

Rejected:
- Approach B (modify vendored `general_utils.py`): touches Autodesk template
  code; gets overwritten on template updates.
- Approach C (switch to stdlib `logging` + `Formatter`): replaces the whole
  print-based system and fights the Fusion `app.log()` path. Too large; YAGNI.

## Design

### 1. Timestamps — `fusion_bridge/dispatch.py`

Stamp the message inside `log()` using:

```python
from datetime import datetime
ts = datetime.now().isoformat(timespec="milliseconds")  # 2026-06-16T14:23:01.123
stamped = f"{ts} {message}"
```

Stamp **before** deferring background-thread messages: prepend the timestamp,
then enqueue the already-stamped string into `_deferred_messages`. This means a
deferred line shows the time it was *logged*, not the time it was later flushed.
`drain_logs()` requires no change because it already replays the stored strings.

Local time is used (not UTC).

Example output:

```
2026-06-16T14:23:01.123 [MCP-Server] JSON: tools/call (id=5)
2026-06-16T14:23:01.246 [MCP] run_python completed in 122ms
```

### 2. Duration — `fusion_bridge/runtime.py` `handle_any_tool()`

Wrap the `handler(call_data)` call with `time.perf_counter()` in a
`try/finally`. After it returns (or raises), emit one completion line with the
tool name, status, and elapsed time. Exceptions still propagate unchanged to the
existing handler in `dispatch.py:_flush_pending`.

- Status is `completed` for a normal result, `failed` if the result envelope has
  `isError` true or an exception propagated.
- The unknown-tool early return is left as-is (no timing line).

Example output:

```
[MCP] run_python completed in 122ms
[MCP] call_autodesk_api failed in 8ms
```

### Adaptive duration format

A small helper formats the elapsed milliseconds:

- `< 1000ms` → integer milliseconds, e.g. `122ms` (sub-millisecond shows `0ms`).
- `>= 1000ms` → seconds with 2 decimals, e.g. `4.52s`.

## Error handling

- Timestamping is a pure string prefix; it cannot fail in normal operation and
  adds no new failure modes.
- Duration uses `try/finally` so the completion line is always logged and the
  original exception/result flow is preserved.

## Known trade-offs / out of scope

- A few non-bridge lines remain un-stamped: top-level `print()` in
  `AutodeskFusionMCP.py` (start/stop failures), `handle_error()` direct
  `futil.log()` calls, and the standalone `test_server.py` harness. These sit
  outside the bridge chokepoint and are acceptable for now.

## Testing

- Unit-test the adaptive duration formatter (boundaries: 0, 999, 1000, large).
- Verify `log()` prepends a well-formed ISO 8601 timestamp and that deferred
  (background-thread) messages are stamped at log time, not flush time.
- Verify `handle_any_tool()` emits a `completed`/`failed` line with a duration
  and still returns the handler result / propagates exceptions unchanged.
