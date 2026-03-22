import adsk.core
import os
from ...lib import fusionAddInUtils as futil
from ... import settings

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f"{settings.COMPANY_NAME}_{settings.ADDIN_NAME}_mcpAbout"
CMD_NAME = "Autodesk Fusion MCP"
CMD_Description = "Standalone MCP server for AI control of Autodesk Fusion"

IS_PROMOTED = True
WORKSPACE_ID = "FusionSolidEnvironment"
PANEL_ID = "SolidScriptsAddinsPanel"
COMMAND_BESIDE_ID = "ScriptsManagerCommand"
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

local_handlers = []


def start():
    existing_cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if existing_cmd_def:
        existing_cmd_def.deleteMe()

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
    control.isPromoted = IS_PROMOTED


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    if command_control:
        command_control.deleteMe()
    if command_definition:
        command_definition.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    from ...fusion_bridge import python_exec

    inputs = args.command.commandInputs

    port = settings.MCP_SERVER_PORT
    version_info = python_exec.get_version_info(python_exec.get_addin_dir())
    about_html = f"""<div style="font-family: Arial, sans-serif; padding: 10px;">
<h2 style="color: #0696D7;">Autodesk Fusion MCP</h2>
<p style="color: #666;">{version_info}</p>

<p>Standalone MCP server running inside Autodesk Fusion.<br>
AI agents connect directly &mdash; no external server needed.</p>

<h3>Status</h3>
<p><strong>Server:</strong> http://127.0.0.1:{port}/mcp<br>
<strong>Health:</strong> http://127.0.0.1:{port}/health</p>

<h3>Claude Desktop Config</h3>
<pre style="background: #f5f5f5; color: #333333; padding: 8px; border-radius: 4px;">
"autodesk-fusion-mcp": {{
  "type": "http",
  "url": "http://127.0.0.1:{port}/mcp"
}}
</pre>

<h3>Capabilities</h3>
<ul>
    <li>Full Autodesk Fusion API access (CAD/CAM/CAE)</li>
    <li>Python code execution</li>
    <li>API documentation introspection</li>
    <li>Script save/load/manage</li>
</ul>
</div>"""

    inputs.addTextBoxCommandInput("about_text", "", about_html, 18, True)

    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


def command_execute(args: adsk.core.CommandEventArgs):
    pass


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
