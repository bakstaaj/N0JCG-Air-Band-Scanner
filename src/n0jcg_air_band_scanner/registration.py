from __future__ import annotations

import hashlib
import json
import platform
import secrets
from pathlib import Path

from n0jcg_licensing import LicenseClient

from . import LICENSE_PREFIX, PRODUCT_ID, PRODUCT_NAME, VERSION


def _client(path: Path) -> LicenseClient:
    return LicenseClient(product_slug=PRODUCT_ID, app_version=VERSION, state_root=path.parent / "license")


def registration_status(path: Path) -> dict[str, object]:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    installation_id = str(saved.get("installation_id", ""))
    if not installation_id:
        installation_id = hashlib.sha256(f"{PRODUCT_ID}:{platform.node()}:{secrets.token_hex(16)}".encode()).hexdigest()[:24].upper()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"product_id": PRODUCT_ID, "installation_id": installation_id}, indent=2) + "\n", encoding="utf-8")
    license_status = _client(path).status()
    registered = bool(license_status.get("registered") or saved.get("license_token"))
    return {"product_name": PRODUCT_NAME, "product_id": PRODUCT_ID, "license_prefix": LICENSE_PREFIX, "installation_id": installation_id, "serial_number": license_status.get("serial_number"), "registered": registered, "mode": "registered" if registered else "trial", "license_configured": bool(license_status.get("license_configured")), "license_suffix": license_status.get("license_suffix", ""), "validation_error": license_status.get("validation_error")}


def activate(path: Path, license_serial: str, email: str) -> dict[str, object]:
    _client(path).activate(license_serial, email)
    return registration_status(path)
