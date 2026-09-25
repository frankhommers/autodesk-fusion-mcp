"""Toolbar entry and HTML palette for selection annotations."""

import json
from pathlib import Path

import adsk.core

from ... import settings
from ...fusion_bridge import annotations
from ...lib import fusionAddInUtils as futil

CMD_ID = f"{settings.COMPANY_NAME}_{settings.ADDIN_NAME}_annotations"
PALETTE_ID = CMD_ID + "_palette"
WORKSPACE_ID = "FusionSolidEnvironment"
PANEL_ID = "SolidScriptsAddinsPanel"
_palette_handlers = []
_command_handlers = []


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


def _created(args):
    futil.add_handler(args.command.execute, _show, local_handlers=_command_handlers)
    futil.add_handler(args.command.destroy, _destroyed, local_handlers=_command_handlers)


def _destroyed(args):
    _command_handlers.clear()


def _show(args):
    ui = _ui()
    palette = ui.palettes.itemById(PALETTE_ID)
    if not palette:
        _palette_handlers.clear()
        palette = ui.palettes.add(
            PALETTE_ID, "Selection annotations",
            str(Path(__file__).with_name("palette.html")), True, True, True, 340, 500, True
        )
        futil.add_handler(palette.incomingFromHTML, _message, local_handlers=_palette_handlers)
        palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
    palette.isVisible = True


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
    definition = ui.commandDefinitions.itemById(CMD_ID)
    if definition:
        definition.deleteMe()
    _palette_handlers.clear()
    _command_handlers.clear()
    annotations.clear()
