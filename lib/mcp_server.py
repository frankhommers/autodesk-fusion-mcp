"""
File: mcp_server.py
Project: Autodesk Fusion MCP Server (Standalone)
Component: Streamable HTTP MCP server using only Python standard library
Author: Frank Hommers
Created: 2026-01-23

Standalone MCP server that runs inside the Autodesk Fusion add-in.
Implements the MCP Streamable HTTP transport (spec 2025-03-26).

MCP clients connect directly:
  {"mcpServers": {"autodesk-fusion-mcp": {"type": "http", "url": "http://localhost:8765/mcp"}}}

Endpoints:
  POST /mcp    - All client→server JSON-RPC messages (single or batch)
  GET  /mcp    - Server→client SSE stream (server-initiated messages)
  DELETE /mcp  - Session termination
  GET  /health - Health check (non-MCP)
"""

import json
import uuid
import threading
import time
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse
from typing import Callable, Dict, Optional


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTP server that handles each request in a new thread."""

    daemon_threads = True


# MCP Protocol version
MCP_PROTOCOL_VERSION = "2025-03-26"

# Server info
SERVER_INFO = {"name": "autodesk-fusion-mcp", "version": "1.0.0"}

# Server capabilities
SERVER_CAPABILITIES = {"tools": {}, "resources": {}}


class MCPServer:
    """
    Standalone MCP server with Streamable HTTP transport.

    Runs an HTTP server on localhost that speaks the MCP protocol.
    All communication goes through POST /mcp (Streamable HTTP).

    Responses are either:
    - application/json for simple requests (initialize, tools/list, ping, etc.)
    - text/event-stream for tools/call (SSE streaming on the POST response)
    """

    def __init__(
        self,
        port: int = 8765,
        tool_handler: Callable = None,
        tool_name: str = "call_autodesk_api",
        tool_description: str = "",
        tool_input_schema: dict = None,
        log_callback: Callable = None,
        tools: list = None,
        tool_handlers: dict = None,
    ):
        self.port = port
        # Keep legacy single-tool attributes for backwards compat
        self.tool_handler = tool_handler
        self.tool_name = tool_name
        self.tool_description = tool_description
        self.tool_input_schema = tool_input_schema or {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "Operation type: execute_python, capture_viewport, fetch_api_documentation, fetch_online_documentation, fetch_design_guide, save_script, load_script, list_scripts, delete_script. Omit for generic API calls.",
                },
                "api_path": {
                    "type": "string",
                    "description": "Dotted path to Autodesk Fusion API method/property (e.g. 'rootComponent.sketches.add'). Shortcuts: app, ui, design, rootComponent, $stored_var",
                },
                "args": {
                    "type": "array",
                    "items": {},
                    "description": 'Positional arguments. Can be literals, API paths, $references, or constructors like {"type": "Point3D", "x": 0, "y": 0, "z": 0}',
                },
                "kwargs": {
                    "type": "object",
                    "description": "Keyword arguments for the API call",
                },
                "remember_as": {
                    "type": "string",
                    "description": "Store the result with this name for later use via $name",
                },
                "return_properties": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Which properties to return from the result object",
                },
                "code": {
                    "type": "string",
                    "description": "Python code to execute (when operation='execute_python')",
                },
                "description": {
                    "type": "string",
                    "description": "Short description of what the code/operation does (REQUIRED for execute_python, shown in Fusion console)",
                },
                "session_id": {
                    "type": "string",
                    "description": "Python session ID for persistent variables",
                },
                "persistent": {
                    "type": "boolean",
                    "description": "Whether to persist Python session variables (default true)",
                },
                "search_term": {
                    "type": "string",
                    "description": "Search term for API documentation",
                },
                "category": {
                    "type": "string",
                    "description": "Search category: class_name, member_name, description, or all",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of documentation results",
                },
                "class_name": {
                    "type": "string",
                    "description": "Class name for online documentation lookup",
                },
                "member_name": {
                    "type": "string",
                    "description": "Member name for online documentation lookup",
                },
                "filename": {
                    "type": "string",
                    "description": "Script filename for save/load/delete operations",
                },
                "width": {
                    "type": "integer",
                    "description": "Image width in pixels for capture_viewport (default: 800)",
                },
                "height": {
                    "type": "integer",
                    "description": "Image height in pixels for capture_viewport (default: 600)",
                },
            },
        }
        self.log_callback = log_callback

        # Multi-tool support: if explicit tools/tool_handlers provided, use them.
        # Otherwise, build from legacy single-tool parameters.
        if tools is not None and tool_handlers is not None:
            self.tools = list(tools)
            self.tool_handlers = dict(tool_handlers)
        else:
            self.tools = [
                {
                    "name": self.tool_name,
                    "description": self.tool_description,
                    "inputSchema": self.tool_input_schema,
                }
            ]
            self.tool_handlers = (
                {self.tool_name: self.tool_handler} if self.tool_handler else {}
            )

        self.sessions: Dict[str, dict] = {}  # Streamable HTTP sessions
        self.sessions_lock = threading.Lock()
        self.resources: list = []  # MCP Resources (static content)
        self.git_commit: Optional[str] = None  # Set externally after creation
        self.httpd: Optional[HTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.is_running = False
        self._start_time: Optional[float] = None

    def log(self, message: str):
        """Log a message."""
        if self.log_callback:
            self.log_callback(f"[MCP-Server] {message}")

    def start(self):
        """Start the MCP server in a background thread."""
        if self.is_running:
            self.log("Server already running")
            return

        server_ref = self

        class MCPRequestHandler(BaseHTTPRequestHandler):
            """HTTP request handler for MCP Streamable HTTP transport."""

            protocol_version = "HTTP/1.1"

            def log_message(self, format, *args):
                """Suppress default HTTP logging."""
                server_ref.log(f"HTTP: {format % args}")

            # ----------------------------------------------------------
            # HTTP method routing
            # ----------------------------------------------------------

            def do_GET(self):
                """Handle GET requests."""
                parsed = urlparse(self.path)
                if parsed.path == "/mcp":
                    self._handle_mcp_get()
                elif parsed.path == "/health":
                    self._handle_health()
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                """Handle POST requests."""
                parsed = urlparse(self.path)
                if parsed.path == "/mcp":
                    self._handle_mcp_post()
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_DELETE(self):
                """Handle DELETE requests (session termination)."""
                parsed = urlparse(self.path)
                if parsed.path == "/mcp":
                    session_id = self.headers.get("Mcp-Session-Id")
                    if session_id:
                        with server_ref.sessions_lock:
                            server_ref.sessions.pop(session_id, None)
                        server_ref.log(f"Session terminated: {session_id}")
                    self.send_response(200)
                    self.end_headers()
                else:
                    self.send_response(404)
                    self.end_headers()

            # ----------------------------------------------------------
            # Health check
            # ----------------------------------------------------------

            def _handle_health(self):
                """Handle GET /health - simple health check endpoint."""
                health = {
                    "status": "ok",
                    "server": SERVER_INFO["name"],
                    "version": SERVER_INFO["version"],
                    "git_commit": server_ref.git_commit,
                    "protocol": MCP_PROTOCOL_VERSION,
                    "uptime_seconds": int(time.time() - server_ref._start_time)
                    if server_ref._start_time
                    else None,
                }
                self._send_json_response(200, health)

            # ----------------------------------------------------------
            # GET /mcp - Server→client SSE stream
            # ----------------------------------------------------------

            def _handle_mcp_get(self):
                """
                Handle GET /mcp - open SSE stream for server-initiated messages.
                Per Streamable HTTP spec, this is optional and used for
                server→client notifications/requests.
                """
                # Validate Accept header
                accept = self.headers.get("Accept", "")
                if "text/event-stream" not in accept:
                    self.send_response(406)
                    self.end_headers()
                    return

                # Validate session if provided
                session_id = self.headers.get("Mcp-Session-Id")
                if session_id:
                    with server_ref.sessions_lock:
                        if session_id not in server_ref.sessions:
                            self.send_response(404)
                            self.end_headers()
                            return

                # Open SSE stream
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                # Keep alive until client disconnects or server stops
                try:
                    while server_ref.is_running:
                        try:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                            time.sleep(15)
                        except (BrokenPipeError, ConnectionResetError):
                            break
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

            # ----------------------------------------------------------
            # Request body reading (Content-Length and chunked)
            # ----------------------------------------------------------

            def _read_request_body(self):
                """Read the full request body, supporting both Content-Length and chunked transfer encoding."""
                transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
                if "chunked" in transfer_encoding:
                    return self._read_chunked_body()
                content_length = int(self.headers.get("Content-Length", 0))
                return self.rfile.read(content_length)

            def _read_chunked_body(self):
                """Decode an HTTP/1.1 chunked transfer-encoded body."""
                chunks = []
                while True:
                    size_line = self.rfile.readline().strip()
                    chunk_size = int(size_line, 16)
                    if chunk_size == 0:
                        self.rfile.readline()  # consume trailing CRLF
                        break
                    chunks.append(self.rfile.read(chunk_size))
                    self.rfile.readline()  # consume chunk-terminating CRLF
                return b"".join(chunks)

            # ----------------------------------------------------------
            # POST /mcp - Streamable HTTP transport (main entry point)
            # ----------------------------------------------------------

            def _handle_mcp_post(self):
                """
                Handle POST /mcp - Streamable HTTP transport.

                Supports:
                - Single JSON-RPC request/notification/response
                - Batch (array) of requests/notifications/responses
                - Responds with application/json or text/event-stream
                """
                # Validate Accept header
                accept = self.headers.get("Accept", "")
                if (
                    "application/json" not in accept
                    and "text/event-stream" not in accept
                    and "*/*" not in accept
                ):
                    self.send_response(406)
                    self.end_headers()
                    return

                # Read request body (supports both Content-Length and chunked transfer encoding)
                body = self._read_request_body()

                try:
                    payload = json.loads(body.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    self._send_json_response(
                        400,
                        {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {"code": -32700, "message": f"Parse error: {e}"},
                        },
                    )
                    return

                # Determine if this is a batch or single message
                is_batch = isinstance(payload, list)
                messages = payload if is_batch else [payload]

                if not messages:
                    self._send_json_response(
                        400,
                        {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {"code": -32600, "message": "Empty batch"},
                        },
                    )
                    return

                # Validate session for non-initialize requests
                session_id = self.headers.get("Mcp-Session-Id")
                has_initialize = any(
                    msg.get("method") == "initialize" for msg in messages
                )

                if not has_initialize and session_id:
                    with server_ref.sessions_lock:
                        if session_id not in server_ref.sessions:
                            # Accept unknown sessions gracefully
                            server_ref.log(
                                f"Unknown session {session_id}, accepting anyway"
                            )
                            server_ref.sessions[session_id] = {
                                "created_at": time.time()
                            }

                # Separate requests (have "id") from notifications/responses
                requests = []
                notifications = []
                for msg in messages:
                    if "method" in msg and "id" in msg:
                        requests.append(msg)
                    else:
                        notifications.append(msg)

                # Process notifications (no response needed)
                # (Notifications have "method" but no "id")
                # (Responses have "id" + "result"/"error" but no "method")
                # Both get 202 if there are no requests to respond to.

                if not requests:
                    self.send_response(202)
                    self.end_headers()
                    return

                # Check if any request is a tools/call (needs SSE streaming)
                has_tools_call = any(
                    req.get("method") == "tools/call" for req in requests
                )

                if has_tools_call:
                    self._handle_streaming_response(requests, notifications, session_id)
                else:
                    self._handle_json_response(requests, session_id)

            # ----------------------------------------------------------
            # JSON response path (fast calls)
            # ----------------------------------------------------------

            def _handle_json_response(self, requests, session_id):
                """
                Handle requests that return application/json.
                Used for initialize, tools/list, ping, resources/*, etc.
                """
                responses = []
                new_session_id = None

                for req in requests:
                    method = req.get("method", "")
                    request_id = req.get("id")
                    params = req.get("params", {})

                    server_ref.log(f"JSON: {method} (id={request_id})")

                    result, is_error = self._dispatch_method(method, params)

                    response = {"jsonrpc": "2.0", "id": request_id}
                    if is_error:
                        response["error"] = result
                    else:
                        response["result"] = result

                    # Track session creation for initialize
                    if method == "initialize" and not is_error:
                        new_session_id = str(uuid.uuid4())
                        with server_ref.sessions_lock:
                            server_ref.sessions[new_session_id] = {
                                "created_at": time.time()
                            }
                        server_ref.log(f"New session: {new_session_id}")

                    responses.append(response)

                # Send response
                result_body = responses if len(responses) > 1 else responses[0]

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                if new_session_id:
                    self.send_header("Mcp-Session-Id", new_session_id)

                encoded = json.dumps(result_body).encode("utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            # ----------------------------------------------------------
            # SSE streaming response path (tools/call)
            # ----------------------------------------------------------

            def _handle_streaming_response(self, requests, notifications, session_id):
                """
                Handle requests via SSE stream on the POST response.
                Used for tools/call which may be long-running.
                Each JSON-RPC response is sent as an SSE 'message' event.
                """
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                try:
                    for req in requests:
                        method = req.get("method", "")
                        request_id = req.get("id")
                        params = req.get("params", {})

                        server_ref.log(f"SSE: {method} (id={request_id})")

                        result, is_error = self._dispatch_method(method, params)

                        response = {"jsonrpc": "2.0", "id": request_id}
                        if is_error:
                            response["error"] = result
                        else:
                            response["result"] = result

                        # Send as SSE event
                        self._write_sse_event(json.dumps(response), event="message")

                except (BrokenPipeError, ConnectionResetError, OSError):
                    server_ref.log("Client disconnected during SSE stream")

            # ----------------------------------------------------------
            # Method dispatch (shared by JSON and SSE paths)
            # ----------------------------------------------------------

            def _dispatch_method(self, method, params):
                """
                Dispatch a JSON-RPC method to the appropriate handler.

                Returns:
                    (result_dict, is_error) tuple
                """
                try:
                    if method == "initialize":
                        return self._handle_initialize(params), False
                    elif method == "tools/list":
                        return self._handle_tools_list(params), False
                    elif method == "tools/call":
                        return self._handle_tools_call(params), False
                    elif method == "resources/list":
                        return self._handle_resources_list(params), False
                    elif method == "resources/read":
                        return self._handle_resources_read(params), False
                    elif method == "ping":
                        return {}, False
                    else:
                        return {
                            "code": -32601,
                            "message": f"Method not found: {method}",
                        }, True
                except Exception as e:
                    server_ref.log(f"Error processing {method}: {e}")
                    return {
                        "code": -32603,
                        "message": f"Internal error: {str(e)}",
                        "data": traceback.format_exc(),
                    }, True

            # ----------------------------------------------------------
            # MCP method handlers
            # ----------------------------------------------------------

            def _handle_initialize(self, params):
                """Handle MCP initialize request."""
                server_ref.log(f"Client initialized: {params.get('clientInfo', {})}")
                return {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": SERVER_CAPABILITIES,
                    "serverInfo": SERVER_INFO,
                }

            def _handle_tools_list(self, params):
                """Handle tools/list request."""
                return {"tools": server_ref.tools}

            def _handle_tools_call(self, params):
                """Handle tools/call request - dispatch to tool handler."""
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})

                handler = server_ref.tool_handlers.get(tool_name)
                if handler is None:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Unknown tool: {tool_name}",
                            }
                        ],
                        "isError": True,
                    }

                # Convert to the format the existing handler expects
                call_data = {"params": {"name": tool_name, "arguments": arguments}}
                return handler(call_data)

            def _handle_resources_list(self, params):
                """Handle resources/list request."""
                resources = []
                for res in server_ref.resources:
                    resources.append(
                        {
                            "uri": res["uri"],
                            "name": res["name"],
                            "description": res.get("description", ""),
                            "mimeType": res.get("mimeType", "text/plain"),
                        }
                    )
                return {"resources": resources}

            def _handle_resources_read(self, params):
                """Handle resources/read request."""
                uri = params.get("uri", "")
                for res in server_ref.resources:
                    if res["uri"] == uri:
                        content = res["content_fn"]()
                        return {
                            "contents": [
                                {
                                    "uri": uri,
                                    "mimeType": res.get("mimeType", "text/plain"),
                                    "text": content,
                                }
                            ]
                        }
                # Not found - raise so _dispatch_method returns error
                raise ValueError(f"Resource not found: {uri}")

            # ----------------------------------------------------------
            # Response helpers
            # ----------------------------------------------------------

            def _send_json_response(self, status_code, data):
                """Send a JSON HTTP response."""
                body = json.dumps(data).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _write_sse_event(self, data, event=None):
                """Write an SSE event to the response stream."""
                if event:
                    self.wfile.write(f"event: {event}\n".encode("utf-8"))
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                self.wfile.flush()

        # ----------------------------------------------------------
        # Create and start the HTTP server
        # ----------------------------------------------------------
        try:
            ThreadingHTTPServer.allow_reuse_address = True
            self.httpd = ThreadingHTTPServer(
                ("127.0.0.1", self.port), MCPRequestHandler
            )
            self.httpd.timeout = 1
            self.is_running = True
            self._start_time = time.time()

            self.server_thread = threading.Thread(
                target=self._serve_forever, daemon=True
            )
            self.server_thread.start()

            self.log(f"MCP Server started on http://127.0.0.1:{self.port}")
            self.log(f"  Streamable HTTP: http://127.0.0.1:{self.port}/mcp")
            self.log(f"  Health check:    http://127.0.0.1:{self.port}/health")
            self.log(f"Add to MCP client config:")
            self.log(
                f'  "autodesk-fusion-mcp": {{"type": "http", "url": "http://127.0.0.1:{self.port}/mcp"}}'
            )

        except OSError as e:
            self.log(f"Failed to start server: {e}")
            if "Address already in use" in str(e) or "Only one usage" in str(e):
                self.log(
                    f"Port {self.port} is already in use. Is another instance running?"
                )
            raise

    def _serve_forever(self):
        """Server loop that respects is_running flag."""
        while self.is_running:
            self.httpd.handle_request()

    def stop(self):
        """Stop the MCP server."""
        if not self.is_running:
            return

        self.log("Stopping MCP server...")
        self.is_running = False

        # Close the HTTP server socket
        if self.httpd:
            self.httpd.server_close()

        # Wait for server thread (should exit within ~1s due to httpd.timeout)
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=3)

        self.log("MCP server stopped")

    @property
    def is_connected(self) -> bool:
        """Check if any sessions are active."""
        with self.sessions_lock:
            return len(self.sessions) > 0
