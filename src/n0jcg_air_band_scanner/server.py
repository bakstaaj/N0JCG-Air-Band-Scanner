from __future__ import annotations

import argparse
from array import array
import csv
import json
import math
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import PRODUCT_NAME, REQUIRED_RTL_SERIAL, VERSION
from .catalog import AirbandCatalog
from .fft_scan import FftPoint, MIN_VALID_SNR_DB, score_channels, simulated_spectrum
from .registration import registration_status

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "web"
RUNTIME = ROOT / "runtime"
CATALOG = STATIC / "data" / "airband-channels.json"
INPUT_RATE = 240_000
OUTPUT_RATE = 24_000
DEFAULT_LOCATION = {"label": "Cripple Creek receiver", "latitude": 38.7467, "longitude": -105.1783}
DEFAULT_RADIUS_MILES = 25.0
DEFAULT_ACTIVITY_THRESHOLD_RMS = 1300.0
DEFAULT_RF_GAIN_DB = 40.2
DEFAULT_SQUELCH_RMS = 1300.0


class RadioState:
    def __init__(self, simulate: bool = False) -> None:
        self.simulate = simulate
        self.catalog = AirbandCatalog(CATALOG)
        self.settings_path = RUNTIME / "settings.json"
        self.settings = {"location": dict(DEFAULT_LOCATION), "radius_miles": DEFAULT_RADIUS_MILES, "activity_threshold_rms": DEFAULT_ACTIVITY_THRESHOLD_RMS, "rf_gain_db": DEFAULT_RF_GAIN_DB, "search_mode": "fast_spectrum", "spectrum_margin_db": 8.0, "squelch_rms": DEFAULT_SQUELCH_RMS}
        self._load_settings()
        self.lock = threading.RLock()
        self.points: list[FftPoint] = []
        self.candidates = []
        self.tuned: dict | None = None
        self.running = False
        self.audio_process: subprocess.Popen[bytes] | None = None
        self.last_audio_rms = 0.0
        self.squelch_open = False

    def _load_settings(self) -> None:
        try:
            saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
            self.settings["location"].update(saved.get("location", {}))
            for key in ("radius_miles", "activity_threshold_rms", "rf_gain_db", "spectrum_margin_db", "squelch_rms"):
                if key in saved: self.settings[key] = float(saved[key])
            if saved.get("search_mode") in ("traditional", "fast_spectrum"): self.settings["search_mode"] = saved["search_mode"]
        except (OSError, ValueError, TypeError):
            pass

    def _save_settings(self) -> None:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.settings, indent=2) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(self.settings_path)

    def registration(self) -> dict:
        return registration_status(RUNTIME / "registration.json")

    def channels(self, nearby: bool = False) -> list[dict]:
        if not nearby: return self.catalog.channels()
        location = self.settings["location"]
        return self.catalog.nearby(float(location["latitude"]), float(location["longitude"]), float(self.settings["radius_miles"]))

    @staticmethod
    def _unique_scan_channels(channels: list[dict]) -> list[dict]:
        unique: dict[int, dict] = {}
        for channel in channels:
            frequency_hz = int(channel.get("frequency_hz", 0))
            if frequency_hz > 0 and frequency_hz not in unique:
                unique[frequency_hz] = channel
        return list(unique.values())

    def scan(self, nearby: bool = False) -> dict:
        with self.lock:
            self._stop_audio()
            channels = self.channels(nearby)
            if nearby and not channels:
                self.running = False
                self.tuned = None
                return self.snapshot({"error": "No FAA channels are inside the saved radius."})
            scan_channels = self._unique_scan_channels(channels)
            self.points = simulated_spectrum(scan_channels) if self.simulate else self._rtl_power_spectrum()
            self.candidates = score_channels(self.points, scan_channels)
            self.tuned = self.candidates[0].channel if self.candidates and self.candidates[0].snr_db >= MIN_VALID_SNR_DB else None
            self.running = self.tuned is not None
            if self.running and not self.simulate: self._start_audio(self.tuned)
            return self.snapshot({"scan_scope": "nearby_faa" if nearby else "full_airband", "channels_scanned": len(scan_channels), "catalog_records_considered": len(channels)})

    def select(self, channel: dict) -> dict:
        with self.lock:
            self._stop_audio()
            self.tuned = channel
            self.running = True
            if not self.simulate: self._start_audio(channel)
            return self.snapshot()

    def _rtl_power_spectrum(self) -> list[FftPoint]:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        output = RUNTIME / "airband-spectrum.csv"
        output.unlink(missing_ok=True)
        cmd = ["rtl_power", "-d", REQUIRED_RTL_SERIAL, "-f", "118000000:136975000:2500", "-i", "1", "-1", "-g", str(self.settings["rf_gain_db"]), str(output)]
        try: result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.SubprocessError): return []
        if result.returncode != 0 or not output.is_file(): return []
        points = []
        for fields in csv.reader(output.read_text(encoding="utf-8", errors="replace").splitlines()):
            if len(fields) < 7: continue
            try: start, step = float(fields[2]), float(fields[4]); powers = [float(value) for value in fields[6:]]
            except ValueError: continue
            scale = 1 if start > 1_000_000 else 1_000_000
            points.extend(FftPoint(int((start + index * step) * scale), power) for index, power in enumerate(powers))
        return points

    def _start_audio(self, channel: dict) -> None:
        cmd = ["rtl_fm", "-d", REQUIRED_RTL_SERIAL, "-f", str(channel["frequency_hz"]), "-M", "am", "-s", str(INPUT_RATE), "-r", str(OUTPUT_RATE), "-g", str(self.settings["rf_gain_db"]), "-l", "0", "-p", "0", "-E", "offset", "-E", "dc"]
        try: self.audio_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError: self.audio_process = None

    def _stop_audio(self) -> None:
        process = self.audio_process
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: process.kill()
        self.audio_process = None

    def audio_chunk(self, chunk: bytes) -> bytes:
        usable = len(chunk) - (len(chunk) % 2)
        if usable <= 0: return chunk
        samples = array("h"); samples.frombytes(chunk[:usable])
        rms = math.sqrt(sum(sample * sample for sample in samples) / max(1, len(samples)))
        with self.lock:
            self.last_audio_rms = round(rms, 1)
            self.squelch_open = self.settings["squelch_rms"] <= 0 or rms >= self.settings["squelch_rms"]
        if self.squelch_open: return chunk
        return b"\0" * usable + chunk[usable:]

    def update_location(self, payload: dict) -> dict:
        location = {"label": str(payload.get("label", self.settings["location"].get("label", "Receiver"))).strip() or "Receiver", "latitude": float(payload["latitude"]), "longitude": float(payload["longitude"])}
        if not -90 <= location["latitude"] <= 90 or not -180 <= location["longitude"] <= 180: raise ValueError("Latitude or longitude is out of range.")
        radius = float(payload.get("radius_miles", self.settings["radius_miles"]))
        if not 0 < radius <= 500: raise ValueError("Radius must be greater than 0 and no more than 500 miles.")
        self.settings["location"] = location; self.settings["radius_miles"] = round(radius, 1); self._save_settings(); return self.settings_payload()

    def update_tuning(self, payload: dict) -> dict:
        if payload.get("rf_gain_db") not in (None, ""): self.settings["rf_gain_db"] = max(0.0, min(49.6, round(float(payload["rf_gain_db"]), 1)))
        if payload.get("activity_threshold_rms") not in (None, ""): self.settings["activity_threshold_rms"] = max(100.0, min(5000.0, round(float(payload["activity_threshold_rms"]), 1)))
        if payload.get("spectrum_margin_db") not in (None, ""): self.settings["spectrum_margin_db"] = max(2.0, min(30.0, round(float(payload["spectrum_margin_db"]), 1)))
        if payload.get("search_mode") in ("traditional", "fast_spectrum"): self.settings["search_mode"] = payload["search_mode"]
        if payload.get("squelch_rms") not in (None, ""): self.settings["squelch_rms"] = max(0.0, min(5000.0, round(float(payload["squelch_rms"]) / 100) * 100))
        self._save_settings(); return self.settings_payload()

    def adjust_squelch(self, delta: float) -> dict:
        return self.update_tuning({"squelch_rms": self.settings["squelch_rms"] + float(delta)})

    def settings_payload(self) -> dict:
        return {"location": self.settings["location"], "radius_miles": self.settings["radius_miles"], "nearby_channel_count": len(self.channels(True)), "tuning": {"activity_threshold_rms": self.settings["activity_threshold_rms"], "rf_gain_db": self.settings["rf_gain_db"], "search_mode": self.settings["search_mode"], "spectrum_margin_db": self.settings["spectrum_margin_db"], "squelch_rms": self.settings["squelch_rms"], "squelch_open": self.squelch_open, "last_audio_rms": self.last_audio_rms, "audio_profile": {"modulation": "am", "input_sample_rate_hz": INPUT_RATE, "sample_rate_hz": OUTPUT_RATE, "offset_tuning": True, "dc_block": True}}}

    def stop(self) -> dict:
        with self.lock: self.running = False; self._stop_audio(); return self.snapshot()

    def snapshot(self, extra: dict | None = None) -> dict:
        result = {"ok": True, "product": PRODUCT_NAME, "version": VERSION, "simulate": self.simulate, "rtl_serial": REQUIRED_RTL_SERIAL, "running": self.running, "registration": self.registration(), "tuned": self.tuned, "settings": self.settings_payload(), "candidates": [{"channel": item.channel, "peak_frequency_hz": item.peak_frequency_hz, "peak_dbfs": item.peak_dbfs, "noise_floor_dbfs": item.noise_floor_dbfs, "snr_db": item.snr_db} for item in self.candidates]}
        if extra: result.update(extra)
        return result


STATE: RadioState


class Handler(BaseHTTPRequestHandler):
    def _json(self, value: object, status: int = 200) -> None:
        body = json.dumps(value).encode(); self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _payload(self) -> dict:
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))

    def do_GET(self) -> None:
        parsed = urlparse(self.path); query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/status": self._json(STATE.snapshot()); return
            if parsed.path in ("/api/settings", "/api/settings/airband-scan"): self._json(STATE.settings_payload()); return
            if parsed.path in ("/api/nearby", "/api/airband/channels"): self._json({"ok": True, **STATE.settings_payload(), "channels": STATE.channels(True)}); return
            if parsed.path == "/api/airports": self._json({"airports": STATE.catalog.airport_codes(query.get("q", [""])[0])}); return
            if parsed.path == "/api/airport": self._json({"channels": STATE.catalog.for_airport(query.get("code", [""])[0])}); return
            if parsed.path == "/api/audio.pcm":
                process = STATE.audio_process
                if not process or not process.stdout: self._json({"ok": False, "error": "audio_not_running"}, 409); return
                self.send_response(200); self.send_header("Content-Type", "application/octet-stream"); self.send_header("Transfer-Encoding", "chunked"); self.end_headers()
                while STATE.running and process.poll() is None:
                    chunk = process.stdout.read(4096)
                    if not chunk: break
                    self._chunk(STATE.audio_chunk(chunk))
                return
            if parsed.path == "/": self._serve("index.html"); return
            self._serve(parsed.path.lstrip("/"))
        except (ValueError, KeyError, TypeError) as error: self._json({"ok": False, "error": str(error)}, 400)
        except Exception as error: self._json({"ok": False, "error": str(error)}, 500)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path in ("/api/scan", "/api/scan/nearby"): self._json(STATE.scan(path.endswith("nearby"))); return
            if path == "/api/stop": self._json(STATE.stop()); return
            if path == "/api/select":
                payload = self._payload(); match = next((item for item in STATE.catalog.channels() if int(item["frequency_hz"]) == int(payload.get("frequency_hz", 0))), None)
                if not match: self._json({"ok": False, "error": "channel_not_found"}, 404); return
                self._json(STATE.select(match)); return
            if path in ("/api/settings/location", "/api/settings/receiver"): self._json(STATE.update_location(self._payload())); return
            if path in ("/api/settings/tuning", "/api/settings/airband-scan"): self._json(STATE.update_tuning(self._payload())); return
            if path in ("/api/settings/squelch", "/api/settings/airband-playback-squelch"):
                payload = self._payload(); self._json(STATE.adjust_squelch(payload.get("delta_rms", 0)) if "delta_rms" in payload else STATE.update_tuning({"squelch_rms": payload.get("squelch_rms")})); return
            self._json({"ok": False, "error": "not_found"}, 404)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error: self._json({"ok": False, "error": str(error)}, 400)
        except Exception as error: self._json({"ok": False, "error": str(error)}, 500)

    def _chunk(self, payload: bytes) -> None:
        self.wfile.write(f"{len(payload):X}\r\n".encode() + payload + b"\r\n"); self.wfile.flush()

    def _serve(self, relative: str) -> None:
        target = (STATIC / relative).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file(): self._json({"ok": False, "error": "not_found"}, 404); return
        body = target.read_bytes(); content_type = "text/html" if target.suffix == ".html" else "text/javascript" if target.suffix == ".js" else "text/css" if target.suffix == ".css" else "image/png" if target.suffix == ".png" else "application/json"
        self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--simulate", action="store_true"); parser.add_argument("--host", default="0.0.0.0"); parser.add_argument("--port", type=int, default=8087)
    args = parser.parse_args(); global STATE; STATE = RadioState(args.simulate); ThreadingHTTPServer((args.host, args.port), Handler).serve_forever(); return 0


if __name__ == "__main__": raise SystemExit(main())
