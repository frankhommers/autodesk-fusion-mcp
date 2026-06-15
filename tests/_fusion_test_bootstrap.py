"""Shared test bootstrap: install a mock ``adsk`` package and a synthetic
parent package so ``fusion_bridge`` relative imports resolve outside Fusion.

Importing this module for its side effects is enough:

    import _fusion_test_bootstrap  # noqa: F401

All setup is idempotent (``setdefault`` / ``if name not in sys.modules``), so it
is safe to import alongside any other copy of the same bootstrap.
"""

import importlib
import pathlib
import sys
import types

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
