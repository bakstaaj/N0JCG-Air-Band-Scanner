# N0JCG Air Band Scanner

Standalone, receive-only civil Airband scanner for RTL-SDR serial `00000118`. It uses FFT-directed candidate scoring across the configured 118.000–136.975 MHz Airband range, tunes the strongest valid AM channel, streams browser PCM audio, and supports airport-code channel selection.

This repository is independent of N0JCG Scanner and N0JCG Air Traffic Center. It reuses their proven serial ownership, AM audio, FAA catalog, and operator UI conventions without sharing runtime state or service ownership.

## Development

```bash
python -m pytest -q
PYTHONPATH=src python -m n0jcg_air_band_scanner.server --simulate --port 8087
```

Open `http://127.0.0.1:8087/`. Live deployment requires `rtl_power`, `rtl_fm`, an Airband antenna path, and an RTL-SDR programmed with EEPROM serial `00000118`.

## Release and deployment

Run `tools/package_release.py` to create a self-contained tarball. On Raspberry Pi OS, use `sudo ./deploy/install.sh`; the service listens on port `8087`.

The checked-in airport data is a development seed. Use the FAA NASR FRQ import tool before treating airport-code coverage as current.
