from __future__ import annotations

import argparse
import csv
import json
import struct
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


class RadioState:
    def __init__(self, simulate: bool = False) -> None:
        self.simulate = simulate
        self.catalog = AirbandCatalog(CATALOG)
        self.lock = threading.RLock()
        self.points: list[FftPoint] = []
        self.candidates = []
        self.tuned: dict | None = None
        self.running = False
        self.audio_process: subprocess.Popen[bytes] | None = None

    def registration(self) -> dict:
        return registration_status(RUNTIME / "registration.json")

    def scan(self) -> dict:
        with self.lock:
            self._stop_audio()
            channels = self.catalog.channels()
            self.points = simulated_spectrum(channels) if self.simulate else self._rtl_power_spectrum()
            self.candidates = score_channels(self.points, channels)
            self.tuned = self.candidates[0].channel if self.candidates and self.candidates[0].snr_db >= MIN_VALID_SNR_DB else None
            self.running = self.tuned is not None
            if self.running and not self.simulate:
                self._start_audio(self.tuned)
            return self.snapshot()

    def select(self, channel: dict) -> dict:
        with self.lock:
            self._stop_audio()
            self.tuned = channel
            self.running = True
            if not self.simulate:
                self._start_audio(channel)
            return self.snapshot()

    def _rtl_power_spectrum(self) -> list[FftPoint]:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        output = RUNTIME / "airband-spectrum.csv"
        output.unlink(missing_ok=True)
        cmd = ["rtl_power", "-d", REQUIRED_RTL_SERIAL, "-f", "118000000:136975000:2500", "-i", "1", "-1", "-g", "40", str(output)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.SubprocessError):
            return []
        if result.returncode != 0 or not output.is_file():
            return []
        points = []
        for fields in csv.reader(output.read_text(encoding="utf-8", errors="replace").splitlines()):
            if len(fields) < 7:
                continue
            try:
                start, step = float(fields[2]), float(fields[4])
                powers = [float(value) for value in fields[6:]]
            except ValueError:
                continue
            scale = 1 if start > 1_000_000 else 1_000_000
            points.extend(FftPoint(int((start + index * step) * scale), power) for index, power in enumerate(powers))
        return points

    def _start_audio(self, channel: dict) -> None:
        cmd = ["rtl_fm", "-d", REQUIRED_RTL_SERIAL, "-f", str(channel["frequency_hz"]), "-M", "am", "-s", str(INPUT_RATE), "-r", str(OUTPUT_RATE), "-g", "49.6", "-l", "0", "-p", "0", "-E", "offset", "-E", "dc"]
        try:
            self.audio_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            self.audio_process = None

    def _stop_audio(self) -> None:
        process = self.audio_process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        self.audio_process = None

    def stop(self) -> dict:
        with self.lock:
            self.running = False
            self._stop_audio()
            return self.snapshot()

    def snapshot(self) -> dict:
        return {"ok": True, "product": PRODUCT_NAME, "version": VERSION, "simulate": self.simulate, "rtl_serial": REQUIRED_RTL_SERIAL, "running": self.running, "registration": self.registration(), "audio_profile": {"modulation": "am", "input_sample_rate_hz": INPUT_RATE, "sample_rate_hz": OUTPUT_RATE, "gain_db": 49.6, "offset_tuning": True, "dc_block": True}, "tuned": self.tuned, "candidates": [{"channel": item.channel, "peak_frequency_hz": item.peak_frequency_hz, "peak_dbfs": item.peak_dbfs, "noise_floor_dbfs": item.noise_floor_dbfs, "snr_db": item.snr_db} for item in self.candidates]}


STATE: RadioState


class Handler(BaseHTTPRequestHandler):
    def _json(self, value: object, status: int = 200) -> None:
        body = json.dumps(value).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status": self._json(STATE.snapshot()); return
        if parsed.path == "/api/registration": self._json(STATE.registration()); return
        if parsed.path == "/api/airports": self._json({"airports": STATE.catalog.airport_codes(parse_qs(parsed.query).get("q", [""])[0])}); return
        if parsed.path == "/api/airport": self._json({"channels": STATE.catalog.for_airport(parse_qs(parsed.query).get("code", [""])[0])}); return
        if parsed.path == "/api/audio.pcm":
            process = STATE.audio_process
            if not process or not process.stdout: self._json({"ok": False, "error": "audio_not_running"}, 409); return
            self.send_response(200); self.send_header("Content-Type", "application/octet-stream"); self.send_header("Transfer-Encoding", "chunked"); self.end_headers()
            while STATE.running and process.poll() is None:
                chunk = process.stdout.read(4096)
                if not chunk: break
                self._chunk(chunk)
            return
        if parsed.path == "/": self._serve("index.html"); return
        self._serve(parsed.path.lstrip("/"))

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path in ("/api/scan", "/api/stop"):
            self._json(STATE.scan() if path.endswith("scan") else STATE.stop()); return
        if path == "/api/select":
            try: payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            except (ValueError, json.JSONDecodeError): self._json({"error": "invalid_json"}, 400); return
            match = next((item for item in STATE.catalog.channels() if int(item["frequency_hz"]) == int(payload.get("frequency_hz", 0))), None)
            if not match: self._json({"error": "channel_not_found"}, 404); return
            self._json(STATE.select(match)); return
        self._json({"error": "not_found"}, 404)

    def _chunk(self, payload: bytes) -> None:
        self.wfile.write(f"{len(payload):X}\r\n".encode() + payload + b"\r\n"); self.wfile.flush()

    def _serve(self, relative: str) -> None:
        target = (STATIC / relative).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file(): self._json({"error": "not_found"}, 404); return
        body = target.read_bytes(); content_type = "text/html" if target.suffix == ".html" else "text/javascript" if target.suffix == ".js" else "text/css" if target.suffix == ".css" else "application/json"
        self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--simulate", action="store_true"); parser.add_argument("--host", default="0.0.0.0"); parser.add_argument("--port", type=int, default=8087)
    args = parser.parse_args()
    global STATE
    STATE = RadioState(args.simulate)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
