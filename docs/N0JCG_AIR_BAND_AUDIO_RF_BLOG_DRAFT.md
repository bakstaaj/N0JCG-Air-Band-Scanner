# Building a Reliable RTL-SDR Air Band Audio Path

*Engineering note · N0JCG Air Band Scanner · August 2026*

Browser audio can make an otherwise healthy SDR receiver sound broken. That was the lesson behind the latest N0JCG Air Band Scanner work: the RTL-SDR was producing usable AM audio, the RF settings were valid, and yet the browser produced persistent clicking.

## Start with stable RF settings

The Air Band Scanner uses RTL-SDR serial `00000118`, AM demodulation, a 240 kHz tuner input, and 24 kHz mono audio output. Offset tuning and DC blocking are enabled; FM deemphasis is disabled. The receive command is:

```text
rtl_fm -d 00000118 -f <frequency_hz> -M am -s 240000 -r 24000 -g 49.6 -l 0 -p 0 -E offset -E dc
```

The scanner uses `rtl_power` to survey 118.000–136.975 MHz, ranks known FAA channels, and tunes the strongest valid candidate. The receiver is selected by EEPROM serial so a USB enumeration change cannot silently move the application to another radio.

## The clicking was not an RF problem

The first browser implementation streamed continuous raw PCM and reconstructed the audio with a browser ring buffer and resampler. Increasing the buffer depth reduced underruns, but the clicking remained. That evidence was important: a larger queue could not repair a flawed transport boundary.

The working Air Band path in N0JCG Air Traffic Center used a different model. It produced finite, valid 0.5-second WAV chunks, decoded them in the browser, and scheduled each chunk against the browser’s audio clock. We adopted that transport for the standalone product while preserving its independent scanner, registration, repository, and deployment identity.

Each chunk contains 24,000 bytes of 16-bit mono audio at 24 kHz, plus a standard 44-byte WAV header. The browser schedules the decoded chunk roughly 40 ms ahead and then requests the next chunk. Once this path was deployed, the clicking disappeared.

## Make a scanner release quiet channels

A scanner should not remain locked forever on a channel that has gone quiet. The Air Band Scanner now releases a channel after seven seconds below the playback squelch threshold and repeats the selected Full Airband or Nearby FAA scan. During the retune gap, the browser tolerates temporary unavailable-audio responses and reconnects to the next finite WAV chunk.

The operator control is intentionally simple: one button changes from Start to Stop based on the scanner state. Skip pauses the current channel for ten minutes, while Pause and Block provide explicit operator control over the current channel.

## A reusable template

The resulting template is straightforward:

- Select the RTL-SDR by stable EEPROM serial.
- Use AM with 240 kHz input and 24 kHz output.
- Keep PPM, offset tuning, DC blocking, and deemphasis explicit.
- Scan with FFT/spectrum data, then tune a known catalog channel.
- Deliver browser audio as valid finite WAV chunks.
- Schedule decoded chunks instead of resampling an unbounded raw PCM stream in the browser.
- Keep squelch, quiet timeout, RF gain, and scan thresholds independently configurable.
- Test the actual RTL-to-browser path, not just service status or USB presence.

The detailed settings and acceptance checklist are now recorded in the [N0JCG Air Band Audio and RF Template](https://github.com/bakstaaj/N0JCG-Air-Band-Scanner/blob/main/docs/AIRBAND_AUDIO_RF_TEMPLATE.md).

This work is a reminder that reliable SDR products are built at the boundaries: stable device identity at the RF boundary, explicit demodulator settings at the signal boundary, and clocked finite audio at the browser boundary.
