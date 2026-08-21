# N0JCG Air Band Scanner User Guide

## Product boundary

N0JCG Air Band Scanner is a standalone, receive-only civil Airband application. It does not transmit, key a radio, decode encrypted traffic, or share runtime ownership with N0JCG NOAA Weather Radio, N0JCG Scanner, or N0JCG Air Traffic Center.

## Hardware

Use the RTL-SDR programmed with EEPROM serial `00000118`. Connect an antenna and filter path appropriate for approximately 118–137 MHz. The scanner identifies the receiver by serial, never by a temporary USB index. It requires `rtl_power` and `rtl_fm` on the host.

## Install

On Raspberry Pi OS, copy the repository to the Pi and run `sudo ./deploy/install.sh`. The UI is served on port `8087`. Run `./deploy/install.sh --check-only` before installation to distinguish missing tools from RF problems.

## Tuning and location controls

The Airband tuning defaults follow the N0JCG Air Traffic Center baseline: AM demodulation, 40.2 dB RF gain, 1300 RMS activity threshold, fast spectrum search, and an 8 dB carrier margin. Use **Apply Airband tuning** to save changes. The RF gain affects both FFT survey and live AM tuning.

Playback squelch is independent of the activity threshold. Use the minus and plus controls to change squelch in 100 RMS steps. A value of 0 is open squelch; a positive value mutes audio below the selected RMS level while retaining the tuned channel.

Enter the receiver name, antenna latitude/longitude, and search radius, then save the location. **Scan nearby FAA** uses the current FAA NASR catalog and only scans known channels within that radius. The **Nearby FAA channels** panel provides direct Tune controls for each returned channel.

## Operation

1. Open the station URL and confirm serial `00000118`.
2. Select **Scan full Airband**. The service surveys 118.000–136.975 MHz, scores every channel in the loaded catalog, and selects the strongest candidate meeting the 6 dB SNR gate.
3. Select **Scan nearby FAA** to survey only channels inside the saved receiver radius.
4. Select an airport code such as `KDEN`, or use the nearby FAA list, then use **Tune** beside a published ATIS, tower, ground, approach, or UNICOM frequency.
5. Use **Listen** only after a valid tuned channel is shown. Browser audio is 24 kHz mono PCM from the AM demodulator and is subject to playback squelch.
6. Stop audio before changing hardware or sharing the receiver with another application.

## Catalog maintenance

`web/data/airband-channels.json` contains a small development seed. Import current FAA NASR FRQ data with `tools/import_faa_catalog.py`; review the generated file before deployment. Airport-code availability is only as current as the imported FAA source.

## Troubleshooting

Service health and USB presence do not prove RF reception. If no candidate appears, check the serial with `rtl_test -d 00000118`, antenna/filter connections, gain, and local channel activity. A clean simulated scan proves application logic only; live FFT and audio commissioning remain hardware-dependent.
