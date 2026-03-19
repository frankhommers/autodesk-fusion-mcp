# UI commands for the Autodesk Fusion MCP add-in.
# The MCP server itself starts automatically via the bridge runtime.

# MCP About command - shows information about the add-in
from .mcpAbout import mcp_about_command as mcpAbout

# Active commands list
commands = [mcpAbout]


# Assumes you defined a "start" function in each of your modules.
# The start function will be run when the add-in is started.
def start():
    for command in commands:
        command.start()


# Assumes you defined a "stop" function in each of your modules.
# The stop function will be run when the add-in is stopped.
def stop():
    for command in commands:
        command.stop()
