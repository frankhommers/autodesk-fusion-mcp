"""Verify the public MCP tool surface: operation names, field names, and
schema structure.  No reference to old / renamed identifiers and no
source-tree scanning tricks."""

import unittest

import _fusion_test_bootstrap  # noqa: F401  (installs adsk mock + parent pkg shim)

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
