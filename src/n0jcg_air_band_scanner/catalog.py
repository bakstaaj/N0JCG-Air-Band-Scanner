from __future__ import annotations

import json
import math
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

    @staticmethod
    def _distance_miles(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
        radius = 3958.7613
        phi_a, phi_b = math.radians(latitude_a), math.radians(latitude_b)
        dphi = math.radians(latitude_b - latitude_a)
        dlambda = math.radians(longitude_b - longitude_a)
        value = math.sin(dphi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(dlambda / 2) ** 2
        return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))

    def nearby(self, latitude: float, longitude: float, radius_miles: float, limit: int = 200) -> list[dict]:
        rows = []
        for channel in self.channels():
            if channel.get("latitude") is None or channel.get("longitude") is None:
                continue
            distance = self._distance_miles(latitude, longitude, float(channel["latitude"]), float(channel["longitude"]))
            if distance <= radius_miles:
                item = dict(channel)
                item["distance_miles"] = round(distance, 1)
                rows.append(item)
        rows.sort(key=lambda item: (item["distance_miles"], item.get("frequency_mhz", 0), item.get("frequency_use", "")))
        return rows[:max(1, min(int(limit), 500))]
