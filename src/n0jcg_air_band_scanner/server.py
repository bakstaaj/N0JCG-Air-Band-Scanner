from __future__ import annotations

import argparse
from array import array
import csv
import json
import math
import subprocess
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import PRODUCT_NAME, REQUIRED_RTL_SERIAL, VERSION
from .catalog import AirbandCatalog
from .fft_scan import FftPoint, MIN_VALID_SNR_DB, score_channels, simulated_spectrum
from .registration import activate as activate_license, registration_status

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "web"
RUNTIME = ROOT / "runtime"
CATALOG = STATIC / "data" / "airband-channels.json"
INPUT_RATE = 240_000
OUTPUT_RATE = 24_000
PCM_READ_BYTES = 4096
AUDIO_CHUNK_BYTES = OUTPUT_RATE * 2 // 2
SQUELCH_RELEASE_SAMPLES = OUTPUT_RATE * 3 // 20
SQUELCH_SCAN_RELEASE_SECONDS = 7.0
DEFAULT_LOCATION = {"label": "Cripple Creek receiver", "latitude": 38.7467, "longitude": -105.1783}
DEFAULT_RADIUS_MILES = 25.0
DEFAULT_ACTIVITY_THRESHOLD_RMS = 1300.0
DEFAULT_RF_GAIN_DB = 40.2
DEFAULT_SQUELCH_RMS = 1300.0
TRIAL_SECONDS = 5 * 60


class RadioState:
    def __init__(self, simulate: bool = False) -> None:
        self.simulate = simulate
        self.catalog = AirbandCatalog(CATALOG)
        self.settings_path = RUNTIME / "settings.json"
        self.trial_path = RUNTIME / "trial.json"
        self.settings = {"location": dict(DEFAULT_LOCATION), "radius_miles": DEFAULT_RADIUS_MILES, "activity_threshold_rms": DEFAULT_ACTIVITY_THRESHOLD_RMS, "rf_gain_db": DEFAULT_RF_GAIN_DB, "search_mode": "fast_spectrum", "spectrum_margin_db": 8.0, "squelch_rms": DEFAULT_SQUELCH_RMS, "channel_controls": {}}
        self._load_settings()
        self.lock = threading.RLock()
        self.points: list[FftPoint] = []
        self.candidates = []
        self.tuned: dict | None = None
        self.running = False
        self.paused = False
        self.audio_process: subprocess.Popen[bytes] | None = None
        self.audio_stream_lock = threading.Lock()
        self.last_audio_rms = 0.0
        self.squelch_open = False
        self.audio_gate_gain = 0.0
        self.squelch_hold_samples = 0
        self.squelch_transitions = 0
        self.squelch_quiet_since = None
        self.scan_nearby = False
        self.manual_tuned = False
        self.release_pending = False
        self.trial_started_at = self._load_trial_started_at()
        self.trial_expired = False
        threading.Thread(target=self._trial_watchdog, name="airband-trial-watchdog", daemon=True).start()

    def _load_trial_started_at(self):
        try:
            saved = json.loads(self.trial_path.read_text(encoding="utf-8"))
            started_wall = float(saved.get("started_at", 0))
            if started_wall > 0:
                return time.monotonic() - max(0.0, time.time() - started_wall)
        except (OSError, ValueError, TypeError):
            pass
        return None

    def _save_trial_started_at(self) -> None:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        self.trial_path.write_text(json.dumps({"started_at": time.time()}, indent=2) + "\n", encoding="utf-8")

    def _load_settings(self) -> None:
        try:
            saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
            self.settings["location"].update(saved.get("location", {}))
            for key in ("radius_miles", "activity_threshold_rms", "rf_gain_db", "spectrum_margin_db", "squelch_rms"):
                if key in saved: self.settings[key] = float(saved[key])
            if saved.get("search_mode") in ("traditional", "fast_spectrum"): self.settings["search_mode"] = saved["search_mode"]
            if isinstance(saved.get("channel_controls"), dict): self.settings["channel_controls"] = saved["channel_controls"]
        except (OSError, ValueError, TypeError):
            pass

    def _save_settings(self) -> None:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.settings, indent=2) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(self.settings_path)

    def registration(self) -> dict:
        return registration_status(RUNTIME / "registration.json")

    def activate_license(self, payload: dict) -> dict:
        with self.lock:
            result = activate_license(RUNTIME / "registration.json", str(payload.get("license_serial", "")), str(payload.get("email", "")))
            self.trial_expired = False
            return self.snapshot({"registration": result})

    def trial_status(self) -> dict:
        if self.registration().get("registered"):
            return {"registered": True, "active": False, "expired": False, "remaining_seconds": None, "duration_seconds": TRIAL_SECONDS}
        with self.lock:
            if self.trial_started_at is None:
                return {"registered": False, "active": False, "expired": False, "remaining_seconds": TRIAL_SECONDS, "duration_seconds": TRIAL_SECONDS}
            remaining = max(0, int(TRIAL_SECONDS - (time.monotonic() - self.trial_started_at)))
            expired = self.trial_expired or remaining <= 0
            return {"registered": False, "active": not expired, "expired": expired, "remaining_seconds": remaining, "duration_seconds": TRIAL_SECONDS}

    def _trial_watchdog(self) -> None:
        while True:
            time.sleep(1)
            with self.lock:
                if self.registration().get("registered") or self.trial_started_at is None or self.trial_expired:
                    continue
                if time.monotonic() - self.trial_started_at >= TRIAL_SECONDS:
                    self.trial_expired = True
                    self.running = False
                    self.paused = False
                    self._stop_audio()

    def _start_or_reject_trial_locked(self) -> bool:
        if self.registration().get("registered"):
            return True
        if self.trial_started_at is None:
            self.trial_started_at = time.monotonic()
            self.trial_expired = False
            self._save_trial_started_at()
            return True
        if self.trial_expired or time.monotonic() - self.trial_started_at >= TRIAL_SECONDS:
            self.trial_expired = True
            self.running = False
            self._stop_audio()
            return False
        return True

    def restart_trial(self) -> dict:
        with self.lock:
            if self.registration().get("registered"):
                return self.snapshot()
            self._stop_audio()
            self.running = False
            self.paused = False
            self.trial_started_at = time.monotonic()
            self.trial_expired = False
            self._save_trial_started_at()
            return self.snapshot()

    def channels(self, nearby: bool = False) -> list[dict]:
        if not nearby: return self.catalog.channels()
        location = self.settings["location"]
        return self.catalog.nearby(float(location["latitude"]), float(location["longitude"]), float(self.settings["radius_miles"]))

    def _prune_controls(self) -> None:
        now = time.time()
        controls = self.settings["channel_controls"]
        expired = [key for key, value in controls.items() if value.get("mode") == "pause" and float(value.get("until", 0)) <= now]
        for key in expired: del controls[key]

    def channel_control(self, frequency_hz: int) -> dict:
        self._prune_controls()
        value = self.settings["channel_controls"].get(str(int(frequency_hz)))
        if not value: return {"mode": "active"}
        if value.get("mode") == "pause": return {"mode": "pause", "until": float(value["until"]), "remaining_seconds": max(0, int(float(value["until"]) - time.time()))}
        return {"mode": "block"}

    def _with_control(self, channel: dict) -> dict:
        item = dict(channel)
        item["scan_control"] = self.channel_control(int(item["frequency_hz"]))
        return item

    def available_channels(self, nearby: bool = False) -> list[dict]:
        return [channel for channel in self.channels(nearby) if self.channel_control(int(channel["frequency_hz"]))["mode"] == "active"]

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
            if not self._start_or_reject_trial_locked():
                return self.snapshot({"error": "The five-minute trial has expired. Restart the trial to continue scanning."})
            self._stop_audio()
            self.paused = False
            self.scan_nearby = nearby
            self.manual_tuned = False
            self.release_pending = False
            channels = self.channels(nearby)
            scan_channels = self.available_channels(nearby)
            if nearby and not channels:
                self.running = False
                self.tuned = None
                return self.snapshot({"error": "No FAA channels are inside the saved radius."})
            if not scan_channels:
                self.running = False
                self.tuned = None
                return self.snapshot({"error": "All channels in this scan scope are paused or blocked.", "scan_scope": "nearby_faa" if nearby else "full_airband", "catalog_records_considered": len(channels), "excluded_channels": len(channels)})
            scan_channels = self._unique_scan_channels(scan_channels)
            self.points = simulated_spectrum(scan_channels) if self.simulate else self._rtl_power_spectrum()
            self.candidates = score_channels(self.points, scan_channels)
            self.tuned = self.candidates[0].channel if self.candidates and self.candidates[0].snr_db >= MIN_VALID_SNR_DB else None
            self.running = self.tuned is not None
            if self.running and not self.simulate: self._start_audio(self.tuned)
            return self.snapshot({"scan_scope": "nearby_faa" if nearby else "full_airband", "channels_scanned": len(scan_channels), "catalog_records_considered": len(channels), "excluded_channels": len(channels) - len(scan_channels)})

    def select(self, channel: dict) -> dict:
        with self.lock:
            if not self._start_or_reject_trial_locked():
                return self.snapshot({"error": "The five-minute trial has expired. Restart the trial to continue scanning."})
            self._stop_audio()
            self.scan_nearby = False
            self.manual_tuned = True
            self.release_pending = False
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
        self.audio_gate_gain = 0.0
        self.squelch_hold_samples = 0
        self.squelch_transitions = 0
        self.squelch_open = False
        self.squelch_quiet_since = None
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
        rescan = False
        with self.lock:
            self.last_audio_rms = round(rms, 1)
            threshold = self.settings["squelch_rms"]
            close_threshold = threshold * 0.75
            was_open = self.squelch_open
            if threshold <= 0 or rms >= (close_threshold if was_open else threshold):
                self.squelch_open = True
                self.squelch_hold_samples = SQUELCH_RELEASE_SAMPLES
            elif was_open and self.squelch_hold_samples > 0:
                self.squelch_hold_samples = max(0, self.squelch_hold_samples - len(samples))
                self.squelch_open = self.squelch_hold_samples > 0
            else:
                self.squelch_open = False
            if self.squelch_open != was_open:
                self.squelch_transitions += 1
            if self.squelch_open:
                self.squelch_quiet_since = None
            elif self.squelch_quiet_since is None:
                self.squelch_quiet_since = time.monotonic()
            elif self.running and not self.manual_tuned and not self.release_pending and time.monotonic() - self.squelch_quiet_since >= SQUELCH_SCAN_RELEASE_SECONDS:
                self.release_pending = True
                rescan = True
            target_gain = 1.0 if self.squelch_open else 0.0
            gain = self.audio_gate_gain
            # A 100 ms envelope avoids a DC/AM step when squelch changes at
            # an arbitrary sample boundary.
            ramp_step = 1.0 / max(1, OUTPUT_RATE // 10)
            output = array("h")
            for sample in samples:
                if gain < target_gain: gain = min(target_gain, gain + ramp_step)
                elif gain > target_gain: gain = max(target_gain, gain - ramp_step)
                output.append(max(-32768, min(32767, int(sample * gain))))
            self.audio_gate_gain = gain
        if rescan:
            threading.Thread(target=self._release_quiet_channel, name="airband-quiet-release", daemon=True).start()
        return output.tobytes() + chunk[usable:]

    def _release_quiet_channel(self) -> None:
        with self.lock:
            if not self.running or self.paused or self.manual_tuned:
                self.release_pending = False
                return
            nearby = self.scan_nearby
        self.scan(nearby)

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

    def update_channel_control(self, payload: dict) -> dict:
        action = str(payload.get("action", "")).lower()
        if action == "clear_all":
            with self.lock:
                self.settings["channel_controls"].clear()
                self._save_settings()
            return self.settings_payload()
        frequency_hz = int(payload["frequency_hz"])
        if not any(int(item.get("frequency_hz", 0)) == frequency_hz for item in self.catalog.channels()): raise ValueError("Channel frequency was not found in the FAA catalog.")
        key = str(frequency_hz)
        release_current = False
        with self.lock:
            if action == "pause": self.settings["channel_controls"][key] = {"mode": "pause", "until": time.time() + 600}
            elif action == "block": self.settings["channel_controls"][key] = {"mode": "block"}
            elif action in ("clear", "unblock"): self.settings["channel_controls"].pop(key, None)
            else: raise ValueError("Use pause, block, clear, or unblock.")
            self._save_settings()
            release_current = action in ("pause", "block") and self.running and self.tuned is not None and int(self.tuned.get("frequency_hz", 0)) == frequency_hz
            if release_current: self.release_pending = True
        if release_current:
            threading.Thread(target=self._release_quiet_channel, name="airband-operator-release", daemon=True).start()
        return self.settings_payload()

    def settings_payload(self) -> dict:
        self._prune_controls()
        controls = {key: self.channel_control(int(key)) for key in self.settings["channel_controls"]}
        quiet_seconds = 0.0 if self.squelch_open or self.squelch_quiet_since is None else max(0.0, time.monotonic() - self.squelch_quiet_since)
        return {"location": self.settings["location"], "radius_miles": self.settings["radius_miles"], "nearby_channel_count": len(self.channels(True)), "channel_controls": controls, "tuning": {"activity_threshold_rms": self.settings["activity_threshold_rms"], "rf_gain_db": self.settings["rf_gain_db"], "search_mode": self.settings["search_mode"], "spectrum_margin_db": self.settings["spectrum_margin_db"], "squelch_rms": self.settings["squelch_rms"], "squelch_open": self.squelch_open, "squelch_quiet_seconds": round(quiet_seconds, 1), "squelch_release_timeout_seconds": SQUELCH_SCAN_RELEASE_SECONDS, "last_audio_rms": self.last_audio_rms, "squelch_transitions": self.squelch_transitions, "audio_profile": {"modulation": "am", "input_sample_rate_hz": INPUT_RATE, "sample_rate_hz": OUTPUT_RATE, "offset_tuning": True, "dc_block": True}}}

    def stop(self) -> dict:
        with self.lock: self.running = False; self.paused = False; self.release_pending = False; self._stop_audio(); return self.snapshot()

    def pause_scan(self) -> dict:
        with self.lock:
            self.running = False
            self.paused = True
            self.release_pending = False
            self._stop_audio()
            return self.snapshot()

    def snapshot(self, extra: dict | None = None) -> dict:
        result = {"ok": True, "product": PRODUCT_NAME, "version": VERSION, "simulate": self.simulate, "rtl_serial": REQUIRED_RTL_SERIAL, "running": self.running, "paused": self.paused, "registration": self.registration(), "trial": self.trial_status(), "tuned": self._with_control(self.tuned) if self.tuned else None, "settings": self.settings_payload(), "candidates": [{"channel": self._with_control(item.channel), "peak_frequency_hz": item.peak_frequency_hz, "peak_dbfs": item.peak_dbfs, "noise_floor_dbfs": item.noise_floor_dbfs, "snr_db": item.snr_db} for item in self.candidates]}
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
            if parsed.path in ("/api/nearby", "/api/airband/channels"): self._json({"ok": True, **STATE.settings_payload(), "channels": [STATE._with_control(item) for item in STATE.channels(True)]}); return
            if parsed.path == "/api/airports": self._json({"airports": STATE.catalog.airport_codes(query.get("q", [""])[0])}); return
            if parsed.path == "/api/airport": self._json({"channels": STATE.catalog.for_airport(query.get("code", [""])[0])}); return
            if parsed.path == "/api/audio.pcm":
                process = STATE.audio_process
                if not process or not process.stdout: self._json({"ok": False, "error": "audio_not_running"}, 409); return
                if not STATE.audio_stream_lock.acquire(blocking=False): self._json({"ok": False, "error": "audio_listener_already_connected"}, 409); return
                try:
                    self.send_response(200); self.send_header("Content-Type", "application/octet-stream"); self.send_header("Transfer-Encoding", "chunked"); self.end_headers()
                    while STATE.running and process.poll() is None:
                        chunk = process.stdout.read(PCM_READ_BYTES)
                        if not chunk: break
                        self._chunk(STATE.audio_chunk(chunk))
                finally:
                    STATE.audio_stream_lock.release()
                return
            if parsed.path == "/api/audio.wav":
                process = STATE.audio_process
                if not process or not process.stdout: self._json({"ok": False, "error": "audio_not_running"}, 409); return
                if not STATE.audio_stream_lock.acquire(blocking=False): self._json({"ok": False, "error": "audio_listener_already_connected"}, 409); return
                try:
                    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 0xFFFFFFFF, b"WAVE", b"fmt ", 16, 1, 1, OUTPUT_RATE, OUTPUT_RATE * 2, 2, 16, b"data", 0xFFFFFFFF)
                    self.send_response(200); self.send_header("Content-Type", "audio/wav"); self.send_header("Transfer-Encoding", "chunked"); self.end_headers(); self._chunk(header)
                    while STATE.running and process.poll() is None:
                        chunk = process.stdout.read(PCM_READ_BYTES)
                        if not chunk: break
                        self._chunk(STATE.audio_chunk(chunk))
                finally:
                    STATE.audio_stream_lock.release()
                return
            if parsed.path == "/api/audio.chunk.wav":
                process = STATE.audio_process
                if not process or not process.stdout: self._json({"ok": False, "error": "audio_not_running"}, 409); return
                if not STATE.audio_stream_lock.acquire(blocking=False): self._json({"ok": False, "error": "audio_listener_already_connected"}, 409); return
                try:
                    audio = bytearray()
                    while len(audio) < AUDIO_CHUNK_BYTES and STATE.running and process.poll() is None:
                        part = process.stdout.read(AUDIO_CHUNK_BYTES - len(audio))
                        if not part: break
                        audio.extend(part)
                    if len(audio) < AUDIO_CHUNK_BYTES:
                        self._json({"ok": False, "error": "audio_chunk_unavailable"}, 503); return
                    audio = STATE.audio_chunk(bytes(audio))
                    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(audio), b"WAVE", b"fmt ", 16, 1, 1, OUTPUT_RATE, OUTPUT_RATE * 2, 2, 16, b"data", len(audio))
                    body = header + audio
                    self.send_response(200); self.send_header("Content-Type", "audio/wav"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
                finally:
                    STATE.audio_stream_lock.release()
                return
            if parsed.path == "/VERSION":
                body = f"{VERSION}\n".encode("ascii")
                self.send_response(200); self.send_header("Content-Type", "text/plain; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            if parsed.path == "/": self._serve("index.html"); return
            self._serve(parsed.path.lstrip("/"))
        except (ValueError, KeyError, TypeError) as error: self._json({"ok": False, "error": str(error)}, 400)
        except Exception as error: self._json({"ok": False, "error": str(error)}, 500)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path in ("/api/scan", "/api/scan/nearby"): self._json(STATE.scan(path.endswith("nearby"))); return
            if path == "/api/pause": self._json(STATE.pause_scan()); return
            if path == "/api/stop": self._json(STATE.stop()); return
            if path == "/api/trial/restart": self._json(STATE.restart_trial()); return
            if path in ("/api/license/activate", "/api/registration/activate"):
                try: self._json(STATE.activate_license(self._payload()))
                except Exception as error: self._json({"ok": False, "error": str(error), "registration": STATE.registration()}, 400)
                return
            if path == "/api/select":
                payload = self._payload(); match = next((item for item in STATE.catalog.channels() if int(item["frequency_hz"]) == int(payload.get("frequency_hz", 0))), None)
                if not match: self._json({"ok": False, "error": "channel_not_found"}, 404); return
                self._json(STATE.select(match)); return
            if path in ("/api/settings/location", "/api/settings/receiver"): self._json(STATE.update_location(self._payload())); return
            if path in ("/api/settings/tuning", "/api/settings/airband-scan"): self._json(STATE.update_tuning(self._payload())); return
            if path in ("/api/settings/squelch", "/api/settings/airband-playback-squelch"):
                payload = self._payload(); self._json(STATE.adjust_squelch(payload.get("delta_rms", 0)) if "delta_rms" in payload else STATE.update_tuning({"squelch_rms": payload.get("squelch_rms")})); return
            if path in ("/api/channel-control", "/api/settings/channel-control"):
                self._json(STATE.update_channel_control(self._payload())); return
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
