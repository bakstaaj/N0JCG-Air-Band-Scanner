# N0JCG Air Band Scanner User Guide

## Product boundary

N0JCG Air Band Scanner is a standalone, receive-only civil Airband application. It does not transmit, key a radio, decode encrypted traffic, or share runtime ownership with N0JCG NOAA Weather Radio, N0JCG Scanner, or N0JCG Air Traffic Center.

## Hardware

Use the RTL-SDR programmed with EEPROM serial `00000118`. Connect an antenna and filter path appropriate for approximately 118–137 MHz. The scanner identifies the receiver by serial, never by a temporary USB index. It requires `rtl_power` and `rtl_fm` on the host.

## Install

On Raspberry Pi OS, copy the repository to the Pi and run `sudo ./deploy/install.sh`. The UI is served on port `8087`. Run `./deploy/install.sh --check-only` before installation to distinguish missing tools from RF problems.

## Tuning and location controls

The Airband tuning defaults follow the N0JCG Air Traffic Center baseline: AM demodulation, 40.2 dB RF gain, 1300 RMS activity threshold, fast spectrum search, and an 8 dB carrier margin. Use **Apply Airband tuning** to save changes. The RF gain affects both FFT survey and live AM tuning.

Playback squelch is independent of the activity threshold. Use the minus and plus controls to change squelch in 100 RMS steps. A value of 0 is open squelch; a positive value mutes audio below the selected RMS level. If the channel remains quiet below squelch for 7 seconds, the scanner releases it and resumes the selected scan scope.

Enter the receiver name, antenna latitude/longitude, and search radius, then save the location. **Scan nearby FAA** uses the current FAA NASR catalog and only scans known channels within that radius. The **Nearby FAA channels** panel provides direct Tune controls for each returned channel.

## Operation

1. Open the station URL and confirm serial `00000118`.
2. Select **Full Airband** or **Nearby FAA**, then press **Start**. The button changes to **Stop** while the scanner is running. The service surveys 118.000–136.975 MHz, scores every channel in the loaded catalog, and selects the strongest candidate meeting the 6 dB SNR gate.
3. Select **Scan nearby FAA** to survey only channels inside the saved receiver radius.
4. Select an airport code such as `KDEN`, or use the nearby FAA list, then use **Tune** beside a published ATIS, tower, ground, approach, or UNICOM frequency.
5. Browser audio starts automatically after a valid tuned channel is shown. It is delivered as scheduled 0.5-second, valid WAV chunks containing 24 kHz mono audio from the AM demodulator. Use **Stop** to end scanning and audio.
6. When a channel is quiet for 7 seconds, the scanner automatically releases it and scans for another candidate. Use **Skip** to pause the current channel for 10 minutes and continue scanning.

## Channel scan controls

The airport-code, nearby FAA, and FFT candidate panels provide per-frequency scan controls. **Pause 10 min** removes a frequency from FFT scanning for ten minutes and then automatically makes it eligible again. **Block** removes it from scanning until **Clear** is selected. These controls are saved in the standalone scanner settings and survive service restarts. They affect scanning only; **Tune** can still be used for deliberate direct listening.

Long channel lists have their own scroll areas so the receiver controls remain accessible.
7. Stop scanning before changing hardware or sharing the receiver with another application.

## Audio and RF reference

For the complete receive command, sample-rate, demodulator, browser playback, squelch, timeout, diagnostics, and acceptance-test reference, see [AIRBAND_AUDIO_RF_TEMPLATE.md](AIRBAND_AUDIO_RF_TEMPLATE.md).

## Catalog maintenance

`web/data/airband-channels.json` contains a small development seed. Import current FAA NASR FRQ data with `tools/import_faa_catalog.py`; review the generated file before deployment. Airport-code availability is only as current as the imported FAA source.

## Troubleshooting

Service health and USB presence do not prove RF reception. If no candidate appears, check the serial with `rtl_test -d 00000118`, antenna/filter connections, gain, and local channel activity. A clean simulated scan proves application logic only; live FFT and audio commissioning remain hardware-dependent.
