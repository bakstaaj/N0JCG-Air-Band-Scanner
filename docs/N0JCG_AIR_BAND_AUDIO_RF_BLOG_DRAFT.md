# Building Reliable SDR Streaming Audio for the Browser

*Engineering note · August 2026*

An SDR can be receiving clean signal and still sound broken in a browser. Repeating clicks, gaps, and unstable audio are often caused by the boundary between the demodulator, the network stream, and the browser’s audio clock—not by the RF signal itself.

## Establish a clean receive baseline

Before debugging browser audio, make the receiver and demodulator explicit. Record the device identity, modulation, input sample rate, output sample rate, gain, frequency correction, filtering, and any deemphasis setting.

A generic AM receive command might look like this:

```text
rtl_fm -d <serial> -f <frequency_hz> -M am -s 240000 -r 24000 -g <gain_db> -l 0 -p 0 -E offset -E dc
```

The exact values depend on the band and hardware. The important practice is to keep them visible and repeatable. Confirm the demodulator produces a sustained PCM stream before involving the browser.

## Why continuous raw PCM can click

A common first design streams unbounded raw PCM over HTTP and reconstructs it with a browser ring buffer or resampler. This can work, but it creates several timing boundaries:

- network packet arrival is not audio-clock timing;
- HTTP reads do not necessarily align with audio frames or application chunks;
- browser scheduling can underrun while the network is still healthy;
- a resampler must continuously correct drift between source and browser clocks;
- abrupt gate, gain, or buffer transitions can become audible impulses.

Increasing the buffer may reduce underruns, but it cannot repair a poorly defined transport boundary. Track both queue depth/underruns and the waveform at the server output.

## Use finite, valid audio chunks

A more predictable browser transport is a sequence of finite, valid WAV chunks:

1. The demodulator produces PCM at a known rate and format.
2. The server reads a fixed duration, such as 0.5 seconds.
3. The server applies any gate or mute decision to that complete chunk.
4. The server wraps the PCM in a correct WAV header with accurate sizes.
5. The browser decodes the chunk with `decodeAudioData()`.
6. An `AudioBufferSourceNode` is scheduled against the browser’s audio clock.
7. The next chunk is requested and scheduled before the previous chunk ends.

For 24 kHz, mono, 16-bit audio, a 0.5-second chunk contains 24,000 bytes of PCM. With a standard 44-byte WAV header, the response is 24,044 bytes.

Finite chunks make the contract testable. The server can verify exact duration and format, while the browser can schedule audio by duration rather than guessing how a continuous byte stream maps onto playback time.

## Schedule with a small lead

Starting every decoded buffer immediately risks a gap when the next network request or decode takes longer than expected. Schedule each buffer slightly ahead—often 20–50 ms—and track the end of the previously scheduled buffer:

```text
start_at = max(audio_context.currentTime + safety_lead, next_play_time)
source.start(start_at)
next_play_time = start_at + decoded.duration
```

The safety lead should absorb normal request/decode jitter without creating noticeable monitor delay. Measure the result rather than choosing a large arbitrary buffer.

## Treat squelch as a separate policy

Squelch should not be confused with transport timing. Keep these decisions explicit:

- RMS or signal threshold;
- hysteresis between opening and closing;
- whether muted chunks become zeros or are omitted;
- gain ramp or hard mute behavior;
- hold time after signal disappears;
- scanner release timeout.

If a muted chunk is replaced with zeros, preserve its exact duration. Do not shorten the stream by dropping silent chunks, because doing so changes playback timing and can create gaps or buffer corrections.

For scanner applications, a quiet-channel timeout can release a tuned channel after a defined period—seven seconds, for example—and return control to the channel-selection loop. During that transition, the browser should tolerate temporary `409` or `503` responses and reconnect rather than treating the retune gap as a fatal audio error.

## Diagnostics that isolate the fault

Capture evidence at each boundary:

- direct demodulator PCM;
- server post-gate PCM;
- WAV header and chunk length;
- browser request status and response timing;
- decoded buffer duration;
- scheduled lead time;
- queue depth and underrun count;
- squelch state transitions and RMS values.

If direct PCM and server PCM are clean but the browser clicks, focus on transport and scheduling. If the server waveform contains impulses, isolate the gate, gain envelope, demodulator, and chunk boundaries before changing browser code.

## Reusable implementation pattern

- Identify hardware by a stable serial or unique device identifier.
- Make modulation, rates, gain, correction, filtering, and deemphasis explicit.
- Validate sustained demodulator output before adding the browser.
- Use fixed-duration, valid WAV chunks for browser playback.
- Schedule decoded buffers with a measured safety lead.
- Preserve silence duration; do not drop muted chunks.
- Make reconnects normal during retunes, scanner transitions, and service restarts.
- Keep RF settings, squelch policy, scanner policy, and browser transport independently configurable.
- Test the complete receiver-to-browser path, not only service status or USB enumeration.

Reliable SDR streaming audio is mostly about respecting the clock. The receiver owns the samples, the server owns the transport contract, and the browser owns playback time. Clear boundaries make each part measurable and reusable across applications.
