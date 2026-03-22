"""Central definitions for the public MCP tool surface."""

# Tool name constants
CALL_AUTODESK_API = "call_autodesk_api"
EXECUTE_PYTHON = "execute_python"
CAPTURE_VIEWPORT = "capture_viewport"
FETCH_API_DOCUMENTATION = "fetch_api_documentation"
FETCH_ONLINE_DOCUMENTATION = "fetch_online_documentation"
FETCH_DESIGN_GUIDE = "fetch_design_guide"
SAVE_SCRIPT = "save_script"
LOAD_SCRIPT = "load_script"
LIST_SCRIPTS = "list_scripts"
DELETE_SCRIPT = "delete_script"
GET_ACTIVE_SELECTION = "get_active_selection"

# Resource constants
RESOURCE_URI = "fusion://design-guide"
RESOURCE_NAME = "Autodesk Fusion Design Guide"
RESOURCE_DESCRIPTION = "Workflow guidance, API patterns, naming rules, and modeling habits for Autodesk Fusion."

# Each tool: {"name", "description", "inputSchema"}
TOOL_DEFINITIONS = [
    {
        "name": CALL_AUTODESK_API,
        "description": (
            "Execute a generic Autodesk Fusion API call. "
            "Resolve a dotted API path, invoke it with args/kwargs, and optionally store the result.\n\n"
            "Path shortcuts: app, ui, design, rootComponent, $stored_name\n\n"
            "Constructors accepted in args/kwargs: Point3D, Vector3D, Point2D, "
            "ValueInput, ObjectCollection, Matrix3D\n\n"
            'Example: {"api_path": "rootComponent.sketches.add", '
            '"args": ["rootComponent.xYConstructionPlane"], "remember_as": "my_sketch"}'
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "api_path": {
                    "type": "string",
                    "description": (
                        "Dotted path to Fusion API method/property "
                        "(e.g. 'rootComponent.sketches.add'). "
                        "Shortcuts: app, ui, design, rootComponent, $stored_var"
                    ),
                },
                "args": {
                    "type": "array",
                    "items": {},
                    "description": (
                        "Positional arguments. Can be literals, API paths, "
                        "$references, or constructors like "
                        '{"type": "Point3D", "x": 0, "y": 0, "z": 0}'
                    ),
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
                "description": {
                    "type": "string",
                    "description": "Short description of what this API call does",
                },
            },
        },
    },
    {
        "name": EXECUTE_PYTHON,
        "description": (
            "Run Python code inside the active Fusion 360 session with access "
            "to the full SDK. Variables persist across calls within the same session_id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID for persistent variables (default: 'default')",
                },
                "persistent": {
                    "type": "boolean",
                    "description": "Whether to persist session variables (default: true)",
                },
                "description": {
                    "type": "string",
                    "description": (
                        "Short description of what the code does, "
                        "shown in Fusion console"
                    ),
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": CAPTURE_VIEWPORT,
        "description": "Capture the current Fusion 360 viewport as a PNG image.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "width": {
                    "type": "integer",
                    "description": "Image width in pixels (default: 800)",
                },
                "height": {
                    "type": "integer",
                    "description": "Image height in pixels (default: 600)",
                },
            },
        },
    },
    {
        "name": FETCH_API_DOCUMENTATION,
        "description": (
            "Search live Fusion API metadata through runtime introspection. "
            "Returns scored results with class overviews, properties, "
            "and function signatures."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "search_term": {
                    "type": "string",
                    "description": (
                        "Search term (e.g. 'BRepBody', 'sketches', "
                        "'adsk.fusion.Sketch.add')"
                    ),
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Search category: class_name, member_name, description, or all"
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 3)",
                },
            },
            "required": ["search_term"],
        },
    },
    {
        "name": FETCH_ONLINE_DOCUMENTATION,
        "description": (
            "Fetch Autodesk cloudhelp documentation for a specific "
            "Fusion API class or member."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "class_name": {
                    "type": "string",
                    "description": "API class name (e.g. 'BRepBody', 'Sketch')",
                },
                "member_name": {
                    "type": "string",
                    "description": "Optional member name (e.g. 'add', 'name')",
                },
            },
            "required": ["class_name"],
        },
    },
    {
        "name": FETCH_DESIGN_GUIDE,
        "description": (
            "Read the bundled Fusion design guide with workflow guidance, "
            "API patterns, naming rules, and modeling habits."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": SAVE_SCRIPT,
        "description": "Save a reusable Python script to the user scripts directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Script filename (e.g. 'my_script.py')",
                },
                "code": {
                    "type": "string",
                    "description": "Python code to save",
                },
                "description": {
                    "type": "string",
                    "description": "Optional description of the script",
                },
            },
            "required": ["filename", "code"],
        },
    },
    {
        "name": LOAD_SCRIPT,
        "description": "Load a previously saved Python script by filename.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Script filename to load",
                },
            },
            "required": ["filename"],
        },
    },
    {
        "name": LIST_SCRIPTS,
        "description": (
            "List all saved Python scripts with metadata "
            "(filename, size, modified date)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": DELETE_SCRIPT,
        "description": "Delete a saved Python script by filename.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Script filename to delete",
                },
            },
            "required": ["filename"],
        },
    },
    {
        "name": GET_ACTIVE_SELECTION,
        "description": (
            "Get the objects currently selected by the user in the Fusion 360 viewport. "
            "Returns detailed info per item (type, name, entityToken, parent component, "
            "and type-specific properties like area, volume, material). "
            "Each selected object is stored as $selection_0, $selection_1, etc. "
            "for use in follow-up API calls."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]

_TOOL_NAMES = {t["name"] for t in TOOL_DEFINITIONS}


def build_tool_handlers(
    *,
    generic_api_call,
    run_python,
    capture_viewport,
    fetch_api_documentation,
    fetch_online_documentation,
    fetch_design_guide,
    save_script,
    load_script,
    list_scripts,
    delete_script,
    get_active_selection,
):
    """Build a dict mapping tool name to handler function.

    All 11 tool names must have a corresponding handler. A RuntimeError
    is raised if the handler keys don't match TOOL_DEFINITIONS.
    """
    handlers = {
        CALL_AUTODESK_API: generic_api_call,
        EXECUTE_PYTHON: run_python,
        CAPTURE_VIEWPORT: capture_viewport,
        FETCH_API_DOCUMENTATION: fetch_api_documentation,
        FETCH_ONLINE_DOCUMENTATION: fetch_online_documentation,
        FETCH_DESIGN_GUIDE: fetch_design_guide,
        SAVE_SCRIPT: save_script,
        LOAD_SCRIPT: load_script,
        LIST_SCRIPTS: list_scripts,
        DELETE_SCRIPT: delete_script,
        GET_ACTIVE_SELECTION: get_active_selection,
    }
    if set(handlers) != _TOOL_NAMES:
        raise RuntimeError(f"Handler registry mismatch: {set(handlers) ^ _TOOL_NAMES}")
    return handlers
