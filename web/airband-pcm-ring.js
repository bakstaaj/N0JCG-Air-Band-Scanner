(function () {
  if (window.AirbandPcmRing) return;
  class AirbandPcmRing {
    constructor(context, destination) { this.context = context; this.buffer = new Int16Array(65536); this.readIndex = 0; this.writeIndex = 0; this.count = 0; this.phase = 0; this.started = false; this.rateCorrection = 0; this.node = context.createScriptProcessor(2048, 0, 1); this.node.onaudioprocess = (event) => this.render(event.outputBuffer); this.node.connect(destination); }
    enqueue(samples) { for (const sample of samples) { if (this.count >= 48000) { this.readIndex = (this.readIndex + 1) % this.buffer.length; this.count -= 1; } this.buffer[this.writeIndex] = sample; this.writeIndex = (this.writeIndex + 1) % this.buffer.length; this.count += 1; } }
    render(outputBuffer) { const channel = outputBuffer.getChannelData(0); channel.fill(0); if (!this.started) { if (this.count < 12000) return; this.started = true; } const queueError = (this.count - 24000) / 48000; this.rateCorrection = Math.max(-0.01, Math.min(0.01, queueError * 0.02)); const step = (24000 / this.context.sampleRate) * (1 + this.rateCorrection); for (let i = 0; i < channel.length; i += 1) { if (this.count < 2) { this.started = false; break; } const first = this.buffer[this.readIndex]; const second = this.buffer[(this.readIndex + 1) % this.buffer.length]; channel[i] = (first + ((second - first) * this.phase)) / 32768; this.phase += step; while (this.phase >= 1 && this.count > 1) { this.phase -= 1; this.readIndex = (this.readIndex + 1) % this.buffer.length; this.count -= 1; } } }
    reset() { this.readIndex = 0; this.writeIndex = 0; this.count = 0; this.phase = 0; this.started = false; this.rateCorrection = 0; }
  }
  window.AirbandPcmRing = AirbandPcmRing;
})();
