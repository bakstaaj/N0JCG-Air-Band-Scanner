from __future__ import annotations

import hashlib
import json
import platform
import secrets
from pathlib import Path

from . import PRODUCT_ID


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
    registered = bool(saved.get("license_token"))
    return {"product_id": PRODUCT_ID, "installation_id": installation_id, "registered": registered, "mode": "registered" if registered else "trial"}
