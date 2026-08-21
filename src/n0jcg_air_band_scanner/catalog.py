from __future__ import annotations

import json
from pathlib import Path


class AirbandCatalog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def channels(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return list(data.get("channels", []))

    def airport_codes(self, query: str = "") -> list[dict]:
        token = query.strip().upper()
        rows = {}
        for channel in self.channels():
            code = str(channel.get("serviced_facility", "")).upper()
            if len(code) != 4 or (token and token not in code and token not in str(channel.get("serviced_facility_name", "")).upper()):
                continue
            rows.setdefault(code, {"code": code, "name": channel.get("serviced_facility_name", ""), "city": channel.get("city", ""), "state": channel.get("state", ""), "channels": []})
            rows[code]["channels"].append(channel)
        return sorted(rows.values(), key=lambda item: item["code"])

    def for_airport(self, code: str) -> list[dict]:
        wanted = code.strip().upper()
        return [row for row in self.channels() if str(row.get("serviced_facility", "")).upper() == wanted]
