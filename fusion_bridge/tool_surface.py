"""Central definitions for the public MCP tool surface."""

EXECUTE_PYTHON = "execute_python"
CAPTURE_VIEWPORT = "capture_viewport"
FETCH_API_DOCUMENTATION = "fetch_api_documentation"
FETCH_ONLINE_DOCUMENTATION = "fetch_online_documentation"
FETCH_DESIGN_GUIDE = "fetch_design_guide"
SAVE_SCRIPT = "save_script"
LOAD_SCRIPT = "load_script"
LIST_SCRIPTS = "list_scripts"
DELETE_SCRIPT = "delete_script"

TOOL_OPERATIONS = {
    EXECUTE_PYTHON: "Run Python code inside the active Fusion session.",
    CAPTURE_VIEWPORT: "Capture the current Fusion viewport as a PNG image.",
    FETCH_API_DOCUMENTATION: "Search live Fusion API metadata through introspection.",
    FETCH_ONLINE_DOCUMENTATION: "Fetch Autodesk cloudhelp documentation for a class or member.",
    FETCH_DESIGN_GUIDE: "Read the bundled Fusion design guide.",
    SAVE_SCRIPT: "Save a reusable Python script under user storage.",
    LOAD_SCRIPT: "Load a previously saved Python script.",
    LIST_SCRIPTS: "List saved Python scripts.",
    DELETE_SCRIPT: "Delete a saved Python script.",
}

RESOURCE_URI = "fusion://design-guide"
RESOURCE_NAME = "Autodesk Fusion Design Guide"
RESOURCE_DESCRIPTION = "Workflow guidance, API patterns, naming rules, and modeling habits for Autodesk Fusion."


def build_operation_handlers(
    *,
    run_python,
    capture_viewport,
    fetch_api_documentation,
    fetch_online_documentation,
    fetch_design_guide,
    save_script,
    load_script,
    list_scripts,
    delete_script,
):
    return {
        EXECUTE_PYTHON: run_python,
        CAPTURE_VIEWPORT: capture_viewport,
        FETCH_API_DOCUMENTATION: fetch_api_documentation,
        FETCH_ONLINE_DOCUMENTATION: fetch_online_documentation,
        FETCH_DESIGN_GUIDE: fetch_design_guide,
        SAVE_SCRIPT: save_script,
        LOAD_SCRIPT: load_script,
        LIST_SCRIPTS: list_scripts,
        DELETE_SCRIPT: delete_script,
    }


def tool_description():
    operations_list = "\n".join(f"- {name}" for name in TOOL_OPERATIONS)
    return f"""
Autodesk Fusion MCP integration tool.

Use this single tool for API calls, script execution, viewport capture, and docs lookup.

Request format:
{{
  "api_path": "rootComponent.sketches.add",
  "args": [],
  "kwargs": {{}},
  "remember_as": "my_sketch",
  "return_properties": ["name", "isVisible"],
  "description": "optional short activity note"
}}

Path shortcuts:
- app
- ui
- design
- rootComponent
- $stored_name for previously stored objects

Generic API example:
{{
  "api_path": "rootComponent.sketches.add",
  "args": ["rootComponent.xYConstructionPlane"],
  "remember_as": "my_sketch"
}}

Rectangle example:
{{
  "api_path": "$my_sketch.sketchCurves.sketchLines.addTwoPointRectangle",
  "args": [
    {{"type": "Point3D", "x": 0, "y": 0, "z": 0}},
    {{"type": "Point3D", "x": 5, "y": 3, "z": 0}}
  ]
}}

Available operations:
{operations_list}

execute_python example:
{{
  "operation": "execute_python",
  "description": "inspect active document",
  "code": "print(app.activeDocument.name if app.activeDocument else 'no document')",
  "session_id": "session_a",
  "persistent": true
}}

Constructors accepted in args/kwargs:
- Point3D
- Vector3D
- Point2D
- ValueInput (value or expression)
- ObjectCollection
- Matrix3D

Autodesk Fusion must be open with this add-in active.
"""


def tool_input_schema():
    operation_names = ", ".join(TOOL_OPERATIONS)
    return {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": f"Operation type: {operation_names}. Omit for generic API calls.",
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
                "description": "Optional short description of what the code or operation does, shown in the Fusion console when provided",
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
