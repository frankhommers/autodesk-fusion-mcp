"""Viewport image capture for the Fusion 360 canvas."""

import base64
import json
import os
import tempfile
import traceback

import adsk.core


def capture(arguments):
    """Capture the active Fusion viewport as a base64-encoded PNG."""
    width = arguments.get("width", 800)
    height = arguments.get("height", 600)

    try:
        app = adsk.core.Application.get()
        vp = app.activeViewport
        if not vp:
            return _fail("ERROR: No active viewport")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = tmp.name

        if not vp.saveAsImageFile(path, width, height):
            return _fail("ERROR: Failed to capture viewport image")

        with open(path, "rb") as fh:
            encoded = base64.standard_b64encode(fh.read()).decode("utf-8")

        try:
            os.remove(path)
        except Exception:
            pass

        return {
            "content": [{"type": "image", "data": encoded, "mimeType": "image/png"}],
            "isError": False,
        }
    except Exception as exc:
        detail = {
            "error": f"ERROR capturing viewport: {exc}",
            "traceback": traceback.format_exc(),
        }
        return {
            "content": [{"type": "text", "text": json.dumps(detail, indent=2)}],
            "isError": True,
        }


def _fail(msg):
    return {"content": [{"type": "text", "text": msg}], "isError": True}
