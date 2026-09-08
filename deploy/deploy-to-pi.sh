#!/usr/bin/env bash
set -euo pipefail

PI_HOST="${PI_HOST:-192.168.68.137}"
PI_USER="${PI_USER:-pi}"
APP_ROOT="${APP_ROOT:-/opt/n0jcg-air-band-scanner}"
SERVICE="${SERVICE:-n0jcg-air-band-scanner.service}"
PORT="${PORT:-8087}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REMOTE="${PI_USER}@${PI_HOST}"
SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)

required_files=(
  "${REPO_ROOT}/web/index.html"
  "${REPO_ROOT}/web/app.css"
  "${REPO_ROOT}/web/app.js"
  "${REPO_ROOT}/VERSION"
  "${REPO_ROOT}/src/n0jcg_air_band_scanner/server.py"
)

for file in "${required_files[@]}"; do
  [[ -f "${file}" ]] || { echo "Missing deployment file: ${file}" >&2; exit 1; }
done

SSH=(ssh "${SSH_OPTS[@]}")
SCP=(scp "${SSH_OPTS[@]}")
if command -v sshpass >/dev/null 2>&1 && [[ -z "${PI_PASSWORD:-}" ]]; then
  read -r -s -p "Pi password: " PI_PASSWORD
  echo
fi
if command -v sshpass >/dev/null 2>&1 && [[ -n "${PI_PASSWORD:-}" ]]; then
  export SSHPASS="${PI_PASSWORD}"
  SSH=(sshpass -e ssh "${SSH_OPTS[@]}")
  SCP=(sshpass -e scp "${SSH_OPTS[@]}")
fi

echo "Deploying Air Band Scanner to ${REMOTE}:${APP_ROOT}"
"${SCP[@]}" \
  "${REPO_ROOT}/web/index.html" \
  "${REPO_ROOT}/web/app.js" \
  "${REPO_ROOT}/web/app.css" \
  "${REPO_ROOT}/VERSION" \
  "${REPO_ROOT}/src/n0jcg_air_band_scanner/server.py" \
  "${REMOTE}:/tmp/"

remote_install="sudo -n true >/dev/null 2>&1"
if ! "${SSH[@]}" "${REMOTE}" "${remote_install}"; then
  if [[ -z "${PI_PASSWORD:-}" ]]; then
    read -r -s -p "Pi password for sudo: " PI_PASSWORD
    echo
  fi
  printf '%s\n' "${PI_PASSWORD}" | "${SSH[@]}" "${REMOTE}" "sudo -S -p '' sh -c 'install -m 0644 /tmp/index.html ${APP_ROOT}/web/index.html && install -m 0644 /tmp/app.js ${APP_ROOT}/web/app.js && install -m 0644 /tmp/app.css ${APP_ROOT}/web/app.css && install -m 0644 /tmp/VERSION ${APP_ROOT}/VERSION && install -m 0644 /tmp/server.py ${APP_ROOT}/src/n0jcg_air_band_scanner/server.py && systemctl restart ${SERVICE}'"
else
  "${SSH[@]}" "${REMOTE}" "sudo install -m 0644 /tmp/index.html ${APP_ROOT}/web/index.html && sudo install -m 0644 /tmp/app.js ${APP_ROOT}/web/app.js && sudo install -m 0644 /tmp/app.css ${APP_ROOT}/web/app.css && sudo install -m 0644 /tmp/VERSION ${APP_ROOT}/VERSION && sudo install -m 0644 /tmp/server.py ${APP_ROOT}/src/n0jcg_air_band_scanner/server.py && sudo systemctl restart ${SERVICE}"
fi

"${SSH[@]}" "${REMOTE}" "systemctl is-active --quiet ${SERVICE}"
version="$(curl --fail --silent "http://${PI_HOST}:${PORT}/VERSION" | tr -d '\\r\\n')"
html="$(curl --fail --silent "http://${PI_HOST}:${PORT}/")"
[[ "${html}" == *data-release-version* ]] || { echo "Footer hook missing from live page" >&2; exit 1; }
[[ "${html}" == *footer-links* ]] || { echo "Footer links missing from live page" >&2; exit 1; }

echo "Deployment verified: ${SERVICE} active, release v${version}, footer present."
