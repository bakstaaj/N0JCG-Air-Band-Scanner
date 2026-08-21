#!/usr/bin/env bash
set -euo pipefail
APP_ROOT=/opt/n0jcg-air-band-scanner
echo "N0JCG Air Band Scanner installer"
echo "Required RTL-SDR EEPROM serial: 00000118"
if [[ "${1:-}" == "--check-only" ]]; then command -v python3 >/dev/null; command -v rtl_power >/dev/null || echo "WARN: rtl_power missing; live FFT unavailable"; command -v rtl_fm >/dev/null || echo "WARN: rtl_fm missing; live audio unavailable"; echo "PASS: preflight"; exit 0; fi
sudo install -d -o pi -g pi "$APP_ROOT" "$APP_ROOT/runtime"
sudo cp -a "$(dirname "$0")/.."/. "$APP_ROOT"/
sudo chown -R pi:pi "$APP_ROOT"
sudo install -m 0644 "$(dirname "$0")/../systemd/n0jcg-air-band-scanner.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now n0jcg-air-band-scanner.service
echo "Installed at http://$(hostname -I | awk '{print $1}'):8087/"
