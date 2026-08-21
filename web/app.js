const $ = (id) => document.getElementById(id);
const fmt = (hz) => `${(hz / 1e6).toFixed(3)} MHz`;
const esc = (value) => String(value).replace(/[&<>"']/g, (character) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;"}[character]));
let audioAbort = null;
let audioContext = null;
let audioNode = null;
let audioQueue = [];
let audioQueueOffset = 0;

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {"Content-Type": "application/json"}, ...options});
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await response.json() : {error: await response.text()};
  $("log").textContent = JSON.stringify(data, null, 2);
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function render(state) {
  $("serial").textContent = state.rtl_serial || "-";
  $("tuned").textContent = state.tuned ? `${state.tuned.serviced_facility} ${state.tuned.frequency_use}` : "Not tuned";
  $("frequency").textContent = state.tuned ? fmt(state.tuned.frequency_hz) : "-";
  $("snr").textContent = state.candidates?.[0] ? `${state.candidates[0].snr_db.toFixed(1)} dB SNR` : "-";
  $("scanState").textContent = state.running ? "Audio path selected" : "Stopped";
  const winner = state.candidates?.[0];
  $("candidates").innerHTML = (state.candidates || []).map((candidate) => `<div class="candidate ${winner && candidate.channel.frequency_hz === winner.channel.frequency_hz ? "winner" : ""}"><span><strong>${esc(candidate.channel.serviced_facility)}</strong> ${esc(candidate.channel.frequency_use)}<br><small>${fmt(candidate.channel.frequency_hz)}</small></span><span>${candidate.snr_db.toFixed(1)} dB SNR</span></div>`).join("") || "No spectrum candidates yet.";
}

function showMessage(message) {
  $("audioStatus").hidden = false;
  $("audioStatus").textContent = message;
}

function stopPcmAudio() {
  if (audioAbort) audioAbort.abort();
  audioAbort = null;
  if (audioNode) audioNode.disconnect();
  audioNode = null;
  if (audioContext) audioContext.close();
  audioContext = null;
  audioQueue = [];
  audioQueueOffset = 0;
}

async function startPcmAudio() {
  stopPcmAudio();
  audioAbort = new AbortController();
  audioContext = new (window.AudioContext || window.webkitAudioContext)({sampleRate: 24000});
  await audioContext.resume();
  audioNode = audioContext.createScriptProcessor(4096, 0, 1);
  audioNode.onaudioprocess = (event) => {
    const output = event.outputBuffer.getChannelData(0);
    output.fill(0);
    let written = 0;
    while (written < output.length && audioQueue.length) {
      const source = audioQueue[0];
      const available = source.length - audioQueueOffset;
      const count = Math.min(available, output.length - written);
      output.set(source.subarray(audioQueueOffset, audioQueueOffset + count), written);
      written += count;
      audioQueueOffset += count;
      if (audioQueueOffset >= source.length) { audioQueue.shift(); audioQueueOffset = 0; }
    }
  };
  audioNode.connect(audioContext.destination);
  showMessage("Live AM audio connected - use system/browser volume.");
  const response = await fetch(`/api/audio.pcm?listen=${Date.now()}`, {signal: audioAbort.signal});
  if (!response.ok || !response.body) throw new Error("Live PCM audio stream unavailable");
  const reader = response.body.getReader();
  let carry = new Uint8Array(0);
  try {
    while (true) {
      const part = await reader.read();
      if (part.done) break;
      const bytes = new Uint8Array(carry.length + part.value.length);
      bytes.set(carry); bytes.set(part.value, carry.length);
      const usable = bytes.length - (bytes.length % 2);
      if (!usable) { carry = bytes; continue; }
      const samples = new Float32Array(usable / 2);
      const view = new DataView(bytes.buffer, bytes.byteOffset, usable);
      for (let index = 0; index < samples.length; index += 1) samples[index] = view.getInt16(index * 2, true) / 32768;
      carry = bytes.slice(usable);
      audioQueue.push(samples);
    }
  } catch (error) {
    if (error.name !== "AbortError") throw error;
  }
}

async function listen() {
  let state = await api("/api/status");
  if (!state.running) state = await api("/api/scan", {method: "POST", body: "{}"});
  render(state);
  if (!state.running || !state.tuned) throw new Error("No valid Airband signal was found.");
  await startPcmAudio();
}

async function scan() {
  stopPcmAudio();
  showMessage("Scanning 118.000-136.975 MHz...");
  const state = await api("/api/scan", {method: "POST", body: "{}"});
  render(state);
  if (!state.running || !state.tuned) throw new Error("No Airband candidate passed the SNR threshold.");
  await startPcmAudio();
}

async function stop() {
  stopPcmAudio();
  const state = await api("/api/stop", {method: "POST", body: "{}"});
  render(state);
  showMessage("Audio stopped.");
}

async function findAirport() {
  const data = await api(`/api/airport?code=${encodeURIComponent($("airport").value)}`);
  $("airportResults").innerHTML = data.channels.length ? data.channels.map((channel) => `<div class="result"><span><strong>${esc(channel.frequency_use)}</strong> · ${fmt(channel.frequency_hz)}</span><button type="button" data-freq="${channel.frequency_hz}">Tune</button></div>`).join("") : "No channels found.";
  document.querySelectorAll("[data-freq]").forEach((button) => button.addEventListener("click", () => tune(Number(button.dataset.freq))));
}

async function tune(frequencyHz) {
  stopPcmAudio();
  showMessage(`Tuning ${fmt(frequencyHz)}...`);
  const state = await api("/api/select", {method: "POST", body: JSON.stringify({frequency_hz: frequencyHz})});
  render(state);
  await startPcmAudio();
}

async function run(action) {
  try { await action(); }
  catch (error) { showMessage(error.message); $("log").textContent = error.stack || error.message; }
}

async function refresh() {
  try { render(await api("/api/status")); $("status").textContent = "READY"; $("status").className = "pill ok"; }
  catch (error) { $("status").textContent = "OFFLINE"; $("status").className = "pill warn"; $("log").textContent = error.message; }
}

$("scan").addEventListener("click", () => run(scan));
$("listen").addEventListener("click", () => run(listen));
$("stop").addEventListener("click", () => run(stop));
$("find").addEventListener("click", () => run(findAirport));
refresh();
setInterval(refresh, 5000);
