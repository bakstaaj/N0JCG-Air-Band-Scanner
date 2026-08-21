class N0jcgPcmPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.queuedSamples = 0;
    this.current = 0;
    this.phase = 0;
    this.started = false;
    this.gain = 0;
    this.sourceRate = 24000;
    this.port.onmessage = (event) => {
      const samples = new Float32Array(event.data);
      if (samples.length) {
        this.queue.push({ samples, offset: 0 });
        this.queuedSamples += samples.length;
      }
    };
  }

  nextSample() {
    if (!this.queue.length) return null;
    const part = this.queue[0];
    const sample = part.samples[part.offset];
    part.offset += 1;
    if (part.offset >= part.samples.length) this.queue.shift();
    this.queuedSamples -= 1;
    return sample;
  }

  process(_inputs, outputs) {
    const output = outputs[0][0];
    const outputRate = sampleRate;
    if (!this.started && this.queuedSamples >= this.sourceRate * 1.5) this.started = true;
    for (let index = 0; index < output.length; index += 1) {
      this.phase += this.sourceRate;
      if (this.phase >= outputRate) {
        this.phase -= outputRate;
        const sample = this.nextSample();
        if (sample !== null) this.current = sample;
      }
      const target = this.started && this.queuedSamples > 0 ? 1 : 0;
      const step = 1 / Math.max(1, Math.round(outputRate * 0.01));
      this.gain += Math.max(-step, Math.min(step, target - this.gain));
      output[index] = this.current * this.gain;
    }
    return true;
  }
}

registerProcessor("n0jcg-pcm-player", N0jcgPcmPlayer);
