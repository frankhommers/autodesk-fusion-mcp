"""Compatibility shim for Autodesk template utilities.

The vendored Autodesk `fusionAddInUtils` code expects a top-level `config`
module. This project keeps runtime settings in `settings.py`, so this shim
provides the names the upstream template reads without forking those files.
"""

from . import settings

DEBUG = settings.DEBUG
ADDIN_NAME = settings.ADDIN_NAME
COMPANY_NAME = settings.COMPANY_NAME
sample_palette_id = f"{COMPANY_NAME}_{ADDIN_NAME}_palette_id"
