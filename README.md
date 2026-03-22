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
- **11 dedicated MCP tools** -- each with a clean, focused schema for better
  LLM tool selection.

## Supported Platforms

- Windows
- Mac OS

## Installation

### Option A: Install from release zip (recommended)

1. Download `AutodeskFusionMCP-v*.zip` from the
   [Releases](https://github.com/frankhommers/autodesk-fusion-mcp/releases)
   page.
2. Extract the zip into your Fusion add-ins folder:
   - **macOS:** `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
   - **Windows:** `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
3. Make sure the extracted folder is named `AutodeskFusionMCP` (rename it if
   the zip extracts to a different name).
4. Open Fusion, press **Shift+S**, select the **Add-Ins** tab, and run
   **AutodeskFusionMCP**.
5. The server listens on `http://127.0.0.1:8765/mcp`.

### Option B: Clone from source

1. Clone this repository into your Fusion add-ins folder:
   - **macOS:** `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
   - **Windows:** `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`
2. Make sure the directory is named `AutodeskFusionMCP`.
3. Open Fusion, press **Shift+S**, select the **Add-Ins** tab, and run
   **AutodeskFusionMCP**.
4. The server listens on `http://127.0.0.1:8765/mcp`.

## MCP Client Configuration

Add to your MCP client config (Claude Desktop, Cursor, etc.):

```json
{
  "mcpServers": {
    "autodesk-fusion-mcp": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

## Tools

| Tool | Description |
|---|---|
| `call_autodesk_api` | Execute a generic Fusion API call via dotted path |
| `execute_python` | Run Python code inside the live Fusion session |
| `capture_viewport` | Capture the viewport as a PNG image |
| `get_active_selection` | Get objects currently selected in the viewport |
| `fetch_api_documentation` | Search Fusion API metadata via runtime introspection |
| `fetch_online_documentation` | Fetch Autodesk cloudhelp docs for a class/member |
| `fetch_design_guide` | Read the bundled design guide |
| `save_script` | Save a reusable Python script |
| `load_script` | Load a previously saved script |
| `list_scripts` | List saved scripts with metadata |
| `delete_script` | Delete a saved script |

### Generic API example

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

### Selection example

The `get_active_selection` tool returns details of objects selected in the
viewport and stores them as `$selection_0`, `$selection_1`, etc. for use in
follow-up API calls.

## Architecture

```
AI agent
  |  Streamable HTTP (POST/GET/DELETE /mcp)
  v
lib/mcp_server.py           -- HTTP server (threading, stdlib only)
  |
fusion_bridge/dispatch.py   -- Custom Event queue relay
  |
fusion_bridge/operations.py -- per-tool routing
  |
fusion_bridge/selection.py  -- viewport selection reader
fusion_bridge/python_exec.py -- Python execution
fusion_bridge/viewport.py   -- viewport capture
fusion_bridge/doc_lookup.py -- API docs introspection
fusion_bridge/script_store.py -- script CRUD
  |
adsk.core / adsk.fusion     -- Fusion 360 SDK (main thread)
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

## Reporting Issues

Please report any issues on the [Issues](https://github.com/frankhommers/autodesk-fusion-mcp/issues) page.

## Author

Frank Hommers / [Initialize](https://initialize.nl)

## License

This project is licensed under the terms of the MIT license. See [LICENSE](LICENSE).

## Changelog

- v 1.0.0
  - Initial release
  - 11 dedicated MCP tools with individual schemas
  - Streamable HTTP transport (MCP spec 2025-03-26)
  - Thread-safe main-thread dispatch
  - Viewport selection reader (`get_active_selection`)
  - Python code execution with persistent sessions
  - API documentation introspection
  - Script management (save/load/list/delete)
  - Zero external dependencies
