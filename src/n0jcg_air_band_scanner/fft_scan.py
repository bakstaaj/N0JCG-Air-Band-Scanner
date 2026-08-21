from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

MIN_VALID_SNR_DB = 6.0


@dataclass(frozen=True)
class FftPoint:
    frequency_hz: int
    power_dbfs: float


@dataclass(frozen=True)
class ScanCandidate:
    channel: dict
    peak_frequency_hz: int
    peak_dbfs: float
    noise_floor_dbfs: float
    snr_db: float


def score_channels(points: Iterable[FftPoint], channels: Iterable[dict], half_width_hz: int = 7_500) -> list[ScanCandidate]:
    points = tuple(points)
    if not points:
        return []
    ordered = sorted(point.power_dbfs for point in points)
    floor = ordered[max(0, len(ordered) // 10)]
    scored = []
    for channel in channels:
        center = int(channel["frequency_hz"])
        window = [p for p in points if abs(p.frequency_hz - center) <= half_width_hz]
        if window:
            peak = max(window, key=lambda p: p.power_dbfs)
            scored.append(ScanCandidate(channel, peak.frequency_hz, peak.power_dbfs, floor, peak.power_dbfs - floor))
    return sorted(scored, key=lambda item: (item.snr_db, item.peak_dbfs), reverse=True)


def simulated_spectrum(channels: Iterable[dict]) -> list[FftPoint]:
    """Deterministic CI spectrum; KDEN tower is the winner."""
    points = []
    for channel in channels:
        peak = -30.0 if channel.get("serviced_facility") == "KDEN" and channel["frequency_use"] == "TWR" else -64.0
        for offset in (-6_000, -2_000, 2_000, 6_000):
            points.append(FftPoint(int(channel["frequency_hz"]) + offset, peak if offset == 2_000 else peak - 8))
    return points
