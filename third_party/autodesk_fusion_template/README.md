This directory contains the canonical Autodesk template snapshot used to freeze
the vendored `lib/fusionAddInUtils/` files in this repository.

Source:
- A freshly generated Autodesk Fusion Python add-in template (`NewAddIn`)

Policy:
- Do not hand-edit these snapshot files.
- Refresh them only by re-copying from a fresh Autodesk-generated template.
- `tests/test_autodesk_vendor_freeze.py` enforces both the snapshot hashes and
  the live vendored copies under `lib/fusionAddInUtils/`.
