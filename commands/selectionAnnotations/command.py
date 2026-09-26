"""Toolbar entry and HTML palette for selection annotations."""

import json
from pathlib import Path

import adsk.core

from ... import settings
from ...fusion_bridge import annotations
from ...lib import fusionAddInUtils as futil

CMD_ID = f"{settings.COMPANY_NAME}_{settings.ADDIN_NAME}_annotations"
PALETTE_ID = CMD_ID + "_palette"
CONTEXT_CMD_ID = CMD_ID + "_context"
WORKSPACE_ID = "FusionSolidEnvironment"
PANEL_ID = "SolidScriptsAddinsPanel"
_palette_handlers = []
_command_handlers = []
_menu_handler = None


def _ui():
    return adsk.core.Application.get().userInterface


def start():
    ui = _ui()
    existing = ui.commandDefinitions.itemById(CMD_ID)
    if existing:
        existing.deleteMe()
    definition = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, "Selection annotations", "Add notes to selections for your AI agent",
        str(Path(__file__).with_name("resources"))
    )
    futil.add_handler(definition.commandCreated, _created)
    panel = ui.workspaces.itemById(WORKSPACE_ID).toolbarPanels.itemById(PANEL_ID)
    panel.controls.addCommand(definition).isPromoted = True

    global _menu_handler
    existing = ui.commandDefinitions.itemById(CONTEXT_CMD_ID)
    if existing:
        existing.deleteMe()
    context = ui.commandDefinitions.addButtonDefinition(
        CONTEXT_CMD_ID, "Annotate selection", "Capture this selection in Selection annotations",
        str(Path(__file__).with_name("resources"))
    )
    futil.add_handler(context.commandCreated, _context_created)
    _menu_handler = futil.add_handler(ui.markingMenuDisplaying, _menu_displaying)


def _menu_displaying(args):
    if args.selectedEntities:
        controls = args.linearMarkingMenu.controls
        controls.addSeparator()
        controls.addCommand(_ui().commandDefinitions.itemById(CONTEXT_CMD_ID))


def _context_created(args):
    # Capture before anything else can change the active selection.
    try:
        annotations.capture_for_palette()
    except ValueError as exc:
        _ui().messageBox(str(exc))
        return
    _created(args)


def _created(args):
    futil.add_handler(args.command.execute, _show, local_handlers=_command_handlers)
    futil.add_handler(args.command.destroy, _destroyed, local_handlers=_command_handlers)


def _destroyed(args):
    _command_handlers.clear()


def _show(args):
    ui = _ui()
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        palette.isVisible = True
        palette.sendInfoToHTML("refresh", "")
        return
    _palette_handlers.clear()
    palette = ui.palettes.add(
        PALETTE_ID, "Selection annotations",
        str(Path(__file__).with_name("palette.html")), True, True, True, 340, 500, True
    )
    futil.add_handler(palette.incomingFromHTML, _message, local_handlers=_palette_handlers)
    palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight


def _message(args):
    try:
        payload = annotations.ui_action(args.action, json.loads(args.data or "{}"))
        if "annotations" in payload:
            preferences = adsk.core.Application.get().preferences.generalPreferences
            theme = getattr(preferences, "activeUserInterfaceTheme", None)
            themes = getattr(adsk.core, "UserInterfaceThemes", None)
            payload["theme"] = "light"
            if themes and theme == themes.DarkBlueUserInterfaceTheme:
                payload["theme"] = "dark-blue"
            elif themes and theme == themes.DarkGrayUserInterfaceTheme:
                payload["theme"] = "dark-gray"
        args.returnData = json.dumps({"ok": True, "data": payload})
    except Exception as exc:
        args.returnData = json.dumps({"ok": False, "error": str(exc)})


def stop():
    ui = _ui()
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        palette.deleteMe()
    panel = ui.workspaces.itemById(WORKSPACE_ID).toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.itemById(CMD_ID)
    if control:
        control.deleteMe()
    global _menu_handler
    if _menu_handler:
        ui.markingMenuDisplaying.remove(_menu_handler)
        _menu_handler = None
    for definition_id in (CMD_ID, CONTEXT_CMD_ID):
        definition = ui.commandDefinitions.itemById(definition_id)
        if definition:
            definition.deleteMe()
    _palette_handlers.clear()
    _command_handlers.clear()
    annotations.clear()
