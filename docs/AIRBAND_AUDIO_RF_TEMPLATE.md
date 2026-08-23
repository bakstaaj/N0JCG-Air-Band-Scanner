# N0JCG Air Band Audio and RF Template

Reusable reference for receive-only civil Airband applications built around an RTL-SDR. This document records the settings and behavior validated in the N0JCG Air Band Scanner and compared with the Air Band receiver inside N0JCG Air Traffic Center.

## 1. Verified receiver baseline

| Parameter | Required baseline | Notes |
|---|---:|---|
| Receiver identity | EEPROM serial `00000118` | Select by serial, never by transient USB index. |
| Mode | AM | Civil Airband voice and aviation services use AM. |
| RTL input sample rate | `240000` Hz | The tuner input rate used by `rtl_fm`. |
| Audio output sample rate | `24000` Hz | The browser playback rate used by the working Air Traffic Center Air Band path. |
| Gain | `49.6 dB` at the commissioned Pi | The application default may be lower; preserve the site’s saved value when deploying. |
| PPM correction | `0` | Apply a measured correction only after validating the device. |
| Offset tuning | Enabled | `rtl_fm -E offset`. |
| DC blocking | Enabled | `rtl_fm -E dc`. |
| FM deemphasis | Disabled | Do not apply FM deemphasis to AM Airband audio. |
| RTL audio squelch | `0` | Let the application perform playback squelch. |

The equivalent receive command is:

```text
rtl_fm -d 00000118 -f <frequency_hz> -M am -s 240000 -r 24000 -g 49.6 -l 0 -p 0 -E offset -E dc
```

Do not treat `00000118` as a generic placeholder. It is the stable hardware identity assigned to this receiver and must be changed only when commissioning a different device.

## 2. Spectrum scan baseline

The scanner surveys the civil Airband range with `rtl_power`:

```text
rtl_power -d 00000118 -f 118000000:136975000:2500 -i 1 -1 -g <gain_db> <output_csv>
```

- Frequency coverage: 118.000–136.975 MHz.
- Bin spacing: 2.5 kHz.
- Integration interval: 1 second.
- Single sweep: `-1`.
- Candidate selection: rank catalog channels by measured spectrum energy and tune the strongest valid candidate that meets the application’s SNR threshold.
- Receiver ownership: the same serial-selected receiver must not be claimed by another active RF process at the same time.

Full Airband scanning and Nearby FAA scanning use the same receiver/audio baseline. Nearby mode filters the catalog by the saved location and radius before ranking candidates.

## 3. Working browser audio path

The stable playback path is finite WAV chunk scheduling:

1. `rtl_fm` produces 24 kHz, 16-bit, mono PCM.
2. The server reads exactly 0.5 seconds of audio: 24,000 bytes.
3. The server applies the application squelch gate and wraps the PCM in a valid 44-byte WAV header.
4. The browser fetches one `/api/audio.chunk.wav` response at a time.
5. The browser decodes each WAV with `decodeAudioData()`.
6. Each `AudioBufferSourceNode` is scheduled approximately 40 ms ahead of the current playback clock.
7. The next chunk is scheduled immediately after the previous chunk, preserving continuous playback.

The resulting chunk is 24,044 bytes: 44 bytes of WAV header plus 24,000 bytes of audio. A finite, valid WAV chunk is important. The earlier continuous raw PCM plus browser ring-buffer/resampler path produced repeatable clicking even when RF captures were clean.

The old `/api/audio.pcm` endpoint may remain available for diagnostics or compatibility, but it should not be the default browser playback path for this product.

## 4. Squelch and scanner behavior

Playback squelch is application-controlled:

- RMS threshold is adjustable in 100 RMS steps.
- Threshold `0` means open squelch.
- The server uses hysteresis: an open gate closes at 75% of the opening threshold.
- A short release hold and gain envelope prevent abrupt sample-boundary transitions.
- The browser’s audio loop must tolerate temporary `409` or `503` responses while the receiver is being retuned.

The scanner behaves as a conventional scanner with a quiet-channel timeout:

- When the tuned channel remains below squelch for 7 seconds, the channel is released.
- The scanner repeats the selected Full Airband or Nearby FAA scan.
- The browser keeps retrying audio chunks while the old receiver process is stopped and the next candidate is selected.
- Operator Stop cancels the scan and audio loop; Start begins the selected scan scope again.
- Skip pauses the current channel for 10 minutes and continues scanning.
- Pause and Block act on the current channel; Clear removes all channel controls.

The seven-second timeout is a scanner policy, not an RF or browser-audio setting. Future products may choose a different timeout, but it should be explicit and visible in status/diagnostics.

## 5. Settings that are product-specific

Do not silently copy these values between applications:

| Setting | Air Traffic Center baseline | Air Band Scanner commissioned state |
|---|---:|---:|
| Activity threshold | 1300 RMS default | 250 RMS saved on the Pi |
| Spectrum margin | 8 dB default | 16 dB saved on the Pi |
| Playback squelch | 1300 RMS default | 100 RMS saved on the Pi |
| Quiet-channel release | 7 seconds | 7 seconds |
| Audio queue | Server-side 24 x 0.5-second history | Sequential finite chunks, browser scheduled |

The Air Band Scanner’s current saved settings reflect commissioning at its receiver location. A new deployment must establish its own gain, activity threshold, spectrum margin, squelch, location, and radius using observed RF evidence.

## 6. Diagnostics and acceptance tests

Before declaring a receiver/audio change successful:

1. Confirm the service reports RTL serial `00000118` (or the commissioned serial for a new product).
2. Confirm AM, 240 kHz input, 24 kHz output, offset tuning, and DC blocking in `/api/status`.
3. Run the local test suite: `pytest -q`.
4. Run Python compilation and browser JavaScript syntax checks.
5. Run an FFT scan and confirm a candidate is selected or a clear no-candidate result is reported.
6. Request a finite WAV chunk and verify HTTP 200, `audio/wav`, and 24,044 bytes for a 0.5-second chunk.
7. Listen in the browser for at least 30 seconds, including a quiet-channel transition.
8. Confirm quiet audio releases after approximately 7 seconds and the next candidate reconnects without a browser error.
9. Confirm Stop leaves no `rtl_fm` process running and does not affect sibling receiver services.

RF presence, USB enumeration, or an active systemd service alone is not proof of working receive audio. Always test the actual RTL-to-browser path.

## 7. Reuse checklist

- [ ] Assign and record a stable RTL EEPROM serial.
- [ ] Reserve the receiver for one owning service.
- [ ] Use AM, 240 kHz input, 24 kHz output, PPM 0, offset tuning, DC blocking, and no deemphasis unless commissioning evidence requires otherwise.
- [ ] Use valid finite WAV chunks for browser playback.
- [ ] Schedule decoded chunks with a small playback lead.
- [ ] Make audio retryable across retunes and scanner transitions.
- [ ] Keep RF settings, application squelch, and scanner timeout as separate settings.
- [ ] Record the actual commissioned gain, thresholds, location, and radius.
- [ ] Validate the complete receive path before shipping or publishing.
