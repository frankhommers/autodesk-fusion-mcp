# Autodesk Fusion MCP Server

Standalone MCP server that runs inside Autodesk Fusion as an add-in.
AI agents connect over **Streamable HTTP** -- the current MCP transport
specification (2025-03-26) -- with no external proxy, middleware, or
dependencies required.

## Highlights

- **Streamable HTTP transport** -- implements the MCP Streamable HTTP spec
  natively; no legacy SSE polling or sidecar servers.
- **Zero external dependencies** -- uses only Python's standard library and
  the Fusion SDK (`adsk.*`).
- **Thread-safe bridge** -- HTTP requests are relayed to Fusion's main thread
  via a Custom Event / work-queue dispatcher, preventing crashes.
- **Single tool surface** -- one MCP tool (`autodesk_fusion`) that multiplexes
  generic API calls, Python execution, viewport capture, documentation
  lookup, and script management.

## Quick start

1. Clone this repository into your Fusion add-ins folder
   (`~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
   on macOS, `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\` on
   Windows).
2. Open Fusion, press **Shift+S**, select the **Add-Ins** tab, and run
   **AutodeskFusionMCP**.
3. The server listens on `http://127.0.0.1:8765/mcp`.
4. Point your MCP client (Claude Desktop, Cursor, etc.) at that endpoint.

## Operations

| Operation | Description |
|---|---|
| *(generic API call)* | Resolve a dotted API path and invoke it with args/kwargs |
| `execute_python` | Run Python code inside the live Fusion session |
| `capture_viewport` | Capture the viewport as a base64-encoded PNG |
| `fetch_api_documentation` | Search Fusion API metadata via runtime introspection |
| `fetch_online_documentation` | Fetch Autodesk cloudhelp docs for a class/member |
| `fetch_design_guide` | Read the bundled design guide |
| `save_script` / `load_script` / `list_scripts` / `delete_script` | Manage reusable Python scripts |

## Generic API example

```json
{
  "api_path": "rootComponent.sketches.add",
  "args": ["rootComponent.xYConstructionPlane"],
  "remember_as": "my_sketch"
}
```

Path shortcuts: `app`, `ui`, `design`, `rootComponent`, `$stored_name`.

Constructors accepted in args: `Point3D`, `Vector3D`, `Point2D`,
`ValueInput`, `ObjectCollection`, `Matrix3D`.

## Architecture

```
AI agent
  |  Streamable HTTP (POST/GET/DELETE /mcp)
  v
lib/mcp_server.py          -- HTTP server (threading, stdlib only)
  |
fusion_bridge/dispatch.py  -- Custom Event queue relay
  |
fusion_bridge/operations.py -- tool router + generic API execution
  |
adsk.core / adsk.fusion    -- Fusion 360 SDK (main thread)
```

## Testing

### Unit tests

Run the test suite (no Fusion required):

```
python3 -m unittest discover -s tests
```

CI runs these tests on every push and pull request via GitHub Actions.

### Protocol compliance with MCP Inspector

The official [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
can verify Streamable HTTP compliance against a running server.

**Against the live Fusion add-in** (port 8765):

```
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8765/mcp --transport http --method tools/list
```

**Against the standalone test server** (no Fusion required):

```
python3 test_server.py                  # starts a dummy server on port 9765
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:9765/mcp --transport http --method tools/list
```

For interactive testing, launch the Inspector UI and select **Streamable HTTP**:

```
npx @modelcontextprotocol/inspector
# open http://localhost:6274, set transport to Streamable HTTP,
# enter URL http://127.0.0.1:8765/mcp (or 9765 for the test server)
```

## License

See LICENSE for terms.
