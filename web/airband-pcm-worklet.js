class AirbandPcmPlayer extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const settings = options.processorOptions || {};
    this.inputRate = Number(settings.inputRate) || 24000;
    this.startSamples = Number(settings.startSamples) || 12000;
    this.maxSamples = Number(settings.maxSamples) || 48000;
    // Keep the physical ring larger than maxSamples so burst delivery cannot
    // overwrite unread samples before the queue limit is reached.
    this.buffer = new Int16Array(131072);
    this.readIndex = 0; this.writeIndex = 0; this.count = 0; this.phase = 0; this.started = false;
    this.port.onmessage = (event) => {
      const message = event.data || {};
      if (message.type === "reset") { this.readIndex = 0; this.writeIndex = 0; this.count = 0; this.phase = 0; this.started = false; return; }
      if (message.type !== "pcm" || !(message.samples instanceof ArrayBuffer)) return;
      const samples = new Int16Array(message.samples);
      for (const sample of samples) { if (this.count >= this.maxSamples) { this.readIndex = (this.readIndex + 1) % this.buffer.length; this.count -= 1; } this.buffer[this.writeIndex] = sample; this.writeIndex = (this.writeIndex + 1) % this.buffer.length; this.count += 1; }
    };
  }
  process(_inputs, outputs) {
    const channel = outputs[0][0]; channel.fill(0);
    if (!this.started) { if (this.count < this.startSamples) return true; this.started = true; }
    const target = this.inputRate;
    const correction = Math.max(-0.01, Math.min(0.01, ((this.count - target) / this.maxSamples) * 0.02));
    const step = (this.inputRate / sampleRate) * (1 + correction);
    for (let i = 0; i < channel.length; i += 1) {
      if (this.count < 2) { this.started = false; break; }
      const first = this.buffer[this.readIndex]; const second = this.buffer[(this.readIndex + 1) % this.buffer.length];
      channel[i] = (first + ((second - first) * this.phase)) / 32768; this.phase += step;
      while (this.phase >= 1 && this.count > 1) { this.phase -= 1; this.readIndex = (this.readIndex + 1) % this.buffer.length; this.count -= 1; }
    }
    return true;
  }
}
registerProcessor("airband-pcm-player", AirbandPcmPlayer);
