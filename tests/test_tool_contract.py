"""Verify the public MCP tool surface: operation names, field names, and
schema structure.  No reference to old / renamed identifiers and no
source-tree scanning tricks."""

import importlib
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Mock adsk modules for testing (not available outside Fusion runtime)
# ---------------------------------------------------------------------------
# Must be installed BEFORE any fusion_bridge imports so that transitive
# imports (dispatch.py, value_builders.py, python_exec.py, selection.py,
# viewport.py, general_utils.py) all resolve against the mock.

_adsk_mock = types.ModuleType("adsk")
_adsk_mock.core = types.ModuleType("adsk.core")
_adsk_mock.fusion = types.ModuleType("adsk.fusion")

# Minimal Application stub — general_utils.py evaluates
#   app = adsk.core.Application.get()
#   ui  = app.userInterface
# at module level, so get() must return an object with .userInterface and .log().
_MockUI = type("UserInterface", (), {"messageBox": lambda self, msg: None})
_MockApp = type(
    "Application",
    (),
    {
        "userInterface": _MockUI(),
        "log": lambda self, *a, **kw: None,
        "activeProduct": None,
    },
)
_adsk_mock.core.Application = type(
    "Application", (), {"get": staticmethod(lambda: _MockApp())}
)
_adsk_mock.core.LogLevels = type(
    "LogLevels",
    (),
    {"InfoLogLevel": 0, "ErrorLogLevel": 1, "WarningLogLevel": 2},
)
_adsk_mock.core.LogTypes = type("LogTypes", (), {"FileLogType": 0, "ConsoleLogType": 1})
_adsk_mock.core.CustomEventHandler = type(
    "CustomEventHandler", (), {"__init__": lambda self: None}
)
_adsk_mock.core.Event = type("Event", (), {"add": lambda self, handler: None})
# Stubs for value_builders.py constructors
_adsk_mock.core.ValueInput = type(
    "ValueInput",
    (),
    {
        "createByString": staticmethod(lambda s: None),
        "createByReal": staticmethod(lambda v: None),
    },
)
_adsk_mock.core.ObjectCollection = type(
    "ObjectCollection",
    (),
    {
        "create": staticmethod(lambda: None),
    },
)
_adsk_mock.core.Matrix3D = type(
    "Matrix3D",
    (),
    {
        "create": staticmethod(lambda: None),
    },
)
_adsk_mock.core.Point3D = type(
    "Point3D",
    (),
    {
        "create": staticmethod(lambda x=0, y=0, z=0: None),
    },
)
_adsk_mock.core.Vector3D = type(
    "Vector3D",
    (),
    {
        "create": staticmethod(lambda x=0, y=0, z=0: None),
    },
)
_adsk_mock.core.Point2D = type(
    "Point2D",
    (),
    {
        "create": staticmethod(lambda x=0, y=0: None),
    },
)

sys.modules.setdefault("adsk", _adsk_mock)
sys.modules.setdefault("adsk.core", _adsk_mock.core)
sys.modules.setdefault("adsk.fusion", _adsk_mock.fusion)

# ---------------------------------------------------------------------------
# Package-structure shim: make the repo root a synthetic parent package
# ---------------------------------------------------------------------------
# fusion_bridge submodules use relative imports like ``from .. import settings``
# and ``from ..lib import fusionAddInUtils``.  When the test runner adds ROOT
# to sys.path, fusion_bridge becomes a top-level package and those ``..``
# imports fail.  Fix: register the root as a real package so fusion_bridge
# is a sub-package of it.

_PARENT_PKG = "_addin_root"

if _PARENT_PKG not in sys.modules:
    _root_pkg = types.ModuleType(_PARENT_PKG)
    _root_pkg.__path__ = [str(ROOT)]
    _root_pkg.__package__ = _PARENT_PKG
    sys.modules[_PARENT_PKG] = _root_pkg

    # Import the real sub-packages/modules that fusion_bridge's relatives need.
    # settings  (from .. import settings)
    _settings = importlib.import_module("settings")
    sys.modules[f"{_PARENT_PKG}.settings"] = _settings
    _root_pkg.settings = _settings

    # lib.fusionAddInUtils  (from ..lib import fusionAddInUtils)
    _lib = importlib.import_module("lib")
    sys.modules[f"{_PARENT_PKG}.lib"] = _lib
    _root_pkg.lib = _lib

    _futil = importlib.import_module("lib.fusionAddInUtils")
    sys.modules[f"{_PARENT_PKG}.lib.fusionAddInUtils"] = _futil
    _lib.fusionAddInUtils = _futil

    _mcp_srv = importlib.import_module("lib.mcp_server")
    sys.modules[f"{_PARENT_PKG}.lib.mcp_server"] = _mcp_srv
    _lib.mcp_server = _mcp_srv

    # Re-register fusion_bridge as a child of the synthetic parent
    import fusion_bridge as _fb

    sys.modules[f"{_PARENT_PKG}.fusion_bridge"] = _fb
    _fb.__package__ = f"{_PARENT_PKG}.fusion_bridge"
    _fb.__name__ = f"{_PARENT_PKG}.fusion_bridge"
    _root_pkg.fusion_bridge = _fb

from fusion_bridge import tool_surface
from lib.mcp_server import MCPServer


class ToolSurfaceTests(unittest.TestCase):
    """Tests that tool_surface exposes correct tool definitions."""

    EXPECTED_TOOLS = {
        "call_autodesk_api",
        "execute_python",
        "capture_viewport",
        "fetch_api_documentation",
        "fetch_online_documentation",
        "fetch_design_guide",
        "save_script",
        "load_script",
        "list_scripts",
        "delete_script",
        "get_active_selection",
    }

    def test_all_expected_tools_present(self):
        names = {t["name"] for t in tool_surface.TOOL_DEFINITIONS}
        self.assertEqual(names, self.EXPECTED_TOOLS)

    def test_each_tool_has_description_and_schema(self):
        for tool_def in tool_surface.TOOL_DEFINITIONS:
            with self.subTest(tool=tool_def["name"]):
                self.assertIn("description", tool_def)
                self.assertTrue(len(tool_def["description"]) > 10)
                self.assertIn("inputSchema", tool_def)
                self.assertEqual(tool_def["inputSchema"]["type"], "object")

    def test_call_autodesk_api_has_api_path(self):
        for t in tool_surface.TOOL_DEFINITIONS:
            if t["name"] == "call_autodesk_api":
                self.assertIn("api_path", t["inputSchema"]["properties"])
                self.assertIn("remember_as", t["inputSchema"]["properties"])
                return
        self.fail("call_autodesk_api tool not found")

    def test_execute_python_has_code_field(self):
        for t in tool_surface.TOOL_DEFINITIONS:
            if t["name"] == "execute_python":
                self.assertIn("code", t["inputSchema"]["properties"])
                self.assertNotIn("api_path", t["inputSchema"]["properties"])
                return
        self.fail("execute_python tool not found")

    def test_get_active_selection_has_no_required_params(self):
        for t in tool_surface.TOOL_DEFINITIONS:
            if t["name"] == "get_active_selection":
                props = t["inputSchema"].get("properties", {})
                self.assertTrue(len(props) <= 1)  # Only optional description allowed
                return
        self.fail("get_active_selection tool not found")


class ResourceTests(unittest.TestCase):
    """Tests that resource constants are defined."""

    def test_resource_uri(self):
        self.assertTrue(tool_surface.RESOURCE_URI.startswith("fusion://"))

    def test_resource_name_nonempty(self):
        self.assertTrue(len(tool_surface.RESOURCE_NAME) > 0)


class MultiToolServerTests(unittest.TestCase):
    """Tests that MCPServer supports multiple tools."""

    def test_server_accepts_tools_list(self):
        tools = [
            {
                "name": "tool_a",
                "description": "Tool A",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "tool_b",
                "description": "Tool B",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]
        handlers = {"tool_a": lambda args: None, "tool_b": lambda args: None}
        server = MCPServer(port=0, tools=tools, tool_handlers=handlers)
        self.assertEqual(len(server.tools), 2)

    def test_server_legacy_single_tool_still_works(self):
        server = MCPServer(
            port=0,
            tool_handler=lambda args: None,
            tool_name="legacy_tool",
            tool_description="Legacy",
            tool_input_schema={"type": "object", "properties": {}},
        )
        self.assertEqual(len(server.tools), 1)
        self.assertEqual(server.tools[0]["name"], "legacy_tool")


class OperationsRegistryTests(unittest.TestCase):
    """Tests that operations exports the correct handler registry."""

    def test_tool_handlers_matches_definitions(self):
        from fusion_bridge import operations, tool_surface

        expected_names = {t["name"] for t in tool_surface.TOOL_DEFINITIONS}
        actual_names = set(operations.TOOL_HANDLERS.keys())
        self.assertEqual(actual_names, expected_names)

    def test_all_handlers_are_callable(self):
        from fusion_bridge import operations

        for name, handler in operations.TOOL_HANDLERS.items():
            with self.subTest(tool=name):
                self.assertTrue(
                    callable(handler), f"Handler for {name} is not callable"
                )


if __name__ == "__main__":
    unittest.main()
