const $ = (id) => document.getElementById(id);
const fmt = (hz) => `${(hz / 1e6).toFixed(3)} MHz`;
const esc = (value) => String(value).replace(/[&<>"']/g, (c) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;"}[c]));
let audioAbort = null;
let audioContext = null;
let audioNode = null;
let audioSources = [];
let audioNextTime = 0;
let audioPending = [];
let audioPendingSamples = 0;
const AUDIO_BUFFER_SAMPLES = 65536;
let scanScope = "full";
let currentTunedFrequency = null;

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {"Content-Type": "application/json"}, ...options});
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await response.json() : {error: await response.text()};
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function render(state) {
  $("serial").textContent = state.rtl_serial || "-";
  $("tuned").textContent = state.tuned ? `${state.tuned.serviced_facility || "Manual"} ${state.tuned.frequency_use || ""}` : "Not tuned";
  $("frequency").textContent = state.tuned ? fmt(state.tuned.frequency_hz) : "-";
  currentTunedFrequency = state.tuned ? Number(state.tuned.frequency_hz) : null;
  $("tunedControls").hidden = !currentTunedFrequency;
  $("snr").textContent = state.candidates?.[0] ? `${state.candidates[0].snr_db.toFixed(1)} dB SNR` : "-";
  $("scanState").textContent = state.paused ? "Paused" : state.running ? "Scanning / audio live" : "Stopped";
  const winner = state.candidates?.[0];
  $("candidates").innerHTML = (state.candidates || []).map((c) => `<div class="candidate ${winner && c.channel.frequency_hz === winner.channel.frequency_hz ? "winner" : ""}"><span><strong>${esc(c.channel.serviced_facility || "Manual")}</strong> ${esc(c.channel.frequency_use || "")}<small>${fmt(c.channel.frequency_hz)} · ${c.snr_db.toFixed(1)} dB</small></span>${renderChannelControls(c.channel)}</div>`).join("") || "No spectrum candidates yet.";
  renderSettings(state.settings);
  bindChannelControls();
}

function renderChannelControls(channel) {
  const frequency = Number(channel.frequency_hz);
  const control = channel.scan_control || ((window.channelControlMap || {})[String(frequency)] || {mode: "active"});
  if (control.mode === "block") return `<span class="channel-status blocked">BLOCKED <button type="button" data-channel-action="clear" data-channel-frequency="${frequency}">Clear</button></span>`;
  if (control.mode === "pause") return `<span class="channel-status paused">PAUSED ${Math.ceil(Number(control.remaining_seconds || 0) / 60)}m <button type="button" data-channel-action="clear" data-channel-frequency="${frequency}">Clear</button></span>`;
  return `<span class="channel-actions"><button type="button" data-channel-action="pause" data-channel-frequency="${frequency}">Pause 10 min</button><button type="button" data-channel-action="block" data-channel-frequency="${frequency}">Block</button></span>`;
}

function renderSettings(settings) {
  if (!settings) return;
  const location = settings.location || {};
  const tuning = settings.tuning || {};
  window.channelControlMap = settings.channel_controls || {};
  $("locationLabel").value = location.label || "";
  $("latitude").value = location.latitude ?? "";
  $("longitude").value = location.longitude ?? "";
  $("radius").value = settings.radius_miles ?? "";
  $("rfGain").value = String(tuning.rf_gain_db ?? 40.2);
  $("searchMode").value = tuning.search_mode || "fast_spectrum";
  $("spectrumMargin").value = String(tuning.spectrum_margin_db ?? 8);
  $("activityThreshold").value = String(tuning.activity_threshold_rms ?? 1300);
  const squelch = Number(tuning.squelch_rms ?? 0);
  $("squelchValue").textContent = squelch ? `${squelch.toFixed(0)} RMS` : "OPEN";
  $("squelchState").textContent = tuning.squelch_open ? "OPEN" : "CLOSED";
  $("rmsValue").textContent = `Current audio RMS: ${Number(tuning.last_audio_rms || 0).toFixed(1)}`;
}

function message(id, text, kind = "") { const target = $(id); target.textContent = text; target.className = `hint ${kind}`; }
function stopPcmAudio() { if (audioAbort) audioAbort.abort(); audioAbort = null; const player = $("audioPlayer"); if (player) { player.pause(); player.removeAttribute("src"); player.load(); } audioSources.forEach((source) => { try { source.stop(); } catch (_) {} }); audioSources = []; audioPending = []; audioPendingSamples = 0; if (audioNode) audioNode.disconnect(); audioNode = null; if (audioContext) audioContext.close(); audioContext = null; audioNextTime = 0; }

function scheduleAudioBuffer(samples) { if (!samples.length) return; const buffer = audioContext.createBuffer(1, samples.length, 24000); buffer.copyToChannel(samples, 0); const source = audioContext.createBufferSource(); const gain = audioContext.createGain(); source.buffer = buffer; source.connect(gain); gain.connect(audioContext.destination); const fade = Math.min(0.02, buffer.duration / 4); const startAt = Math.max(audioNextTime - fade, audioContext.currentTime + 0.1); const endAt = startAt + buffer.duration; gain.gain.setValueAtTime(0, startAt); gain.gain.linearRampToValueAtTime(1, startAt + fade); gain.gain.setValueAtTime(1, Math.max(startAt + fade, endAt - fade)); gain.gain.linearRampToValueAtTime(0, endAt); source.start(startAt); audioNextTime = endAt; audioSources.push(source); source.onended = () => { audioSources = audioSources.filter((item) => item !== source); }; }

function queueAudioBuffer(samples) { audioPending.push(samples); audioPendingSamples += samples.length; if (audioPendingSamples < AUDIO_BUFFER_SAMPLES) return; const merged = new Float32Array(audioPendingSamples); let offset = 0; audioPending.forEach((part) => { merged.set(part, offset); offset += part.length; }); audioPending = []; audioPendingSamples = 0; scheduleAudioBuffer(merged); }

async function startPcmAudio() {
  const player = $("audioPlayer"); if (!player) throw new Error("Browser audio element is unavailable."); stopPcmAudio(); player.src = `/api/audio.wav?listen=${Date.now()}`; player.load(); await player.play(); $("audioStatus").hidden = false; $("audioStatus").textContent = "Live AM audio connected - use system/browser volume.";
}

async function run(action) { try { await action(); } catch (error) { $("audioStatus").hidden = false; $("audioStatus").textContent = error.message; } }
async function scan(nearby = scanScope === "nearby") { stopPcmAudio(); $("audioStatus").hidden = false; $("audioStatus").textContent = nearby ? "Scanning known FAA channels within the saved radius..." : "Scanning 118.000-136.975 MHz..."; const state = await api(nearby ? "/api/scan/nearby" : "/api/scan", {method: "POST", body: "{}"}); render(state); if (!state.running || !state.tuned) throw new Error(state.error || "No Airband candidate passed the SNR threshold."); await startPcmAudio(); }
async function skipCurrent() { if (!currentTunedFrequency) throw new Error("There is no currently locked channel to skip."); await updateChannelControl("pause", currentTunedFrequency); await scan(); }
async function stop() { stopPcmAudio(); render(await api("/api/stop", {method: "POST", body: "{}"})); $("audioStatus").hidden = false; $("audioStatus").textContent = "Audio stopped."; }
async function tune(frequencyHz) { stopPcmAudio(); const state = await api("/api/select", {method: "POST", body: JSON.stringify({frequency_hz: frequencyHz})}); render(state); await startPcmAudio(); }
async function findAirport() { const data = await api(`/api/airport?code=${encodeURIComponent($("airport").value)}`); $("airportResults").innerHTML = data.channels.length ? data.channels.map((c) => `<div class="result"><span><strong>${esc(c.frequency_use)}</strong><small>${fmt(c.frequency_hz)}</small></span><span class="channel-row-actions"><button type="button" data-freq="${c.frequency_hz}">Tune</button>${renderChannelControls(c)}</span></div>`).join("") : "No channels found."; document.querySelectorAll("[data-freq]").forEach((button) => button.addEventListener("click", () => run(() => tune(Number(button.dataset.freq))))); bindChannelControls(); }
async function loadNearby() { const data = await api("/api/nearby"); window.channelControlMap = data.channel_controls || {}; $("nearbySummary").textContent = `${data.channels.length} channels within ${Number(data.radius_miles).toFixed(1)} miles of ${data.location.label}.`; $("nearbyChannels").innerHTML = data.channels.length ? data.channels.map((c) => `<div class="nearby-row"><span><strong>${esc(c.serviced_facility)}</strong> ${esc(c.frequency_use)}<small>${fmt(c.frequency_hz)} · ${esc(c.serviced_facility_name || "")} · ${c.distance_miles} mi</small></span><span class="channel-row-actions"><button type="button" data-nearby-freq="${c.frequency_hz}">Tune</button>${renderChannelControls(c)}</span></div>`).join("") : "No FAA channels found in this radius."; document.querySelectorAll("[data-nearby-freq]").forEach((button) => button.addEventListener("click", () => run(() => tune(Number(button.dataset.nearbyFreq))))); bindChannelControls(); }
async function saveLocation() { const result = await api("/api/settings/location", {method: "POST", body: JSON.stringify({label: $("locationLabel").value, latitude: $("latitude").value, longitude: $("longitude").value, radius_miles: $("radius").value})}); renderSettings(result); message("locationMessage", `Saved ${result.location.label}; ${result.nearby_channel_count} FAA channels found.`, "good"); await loadNearby(); }
async function saveTuning() { const result = await api("/api/settings/tuning", {method: "POST", body: JSON.stringify({rf_gain_db: $("rfGain").value, search_mode: $("searchMode").value, spectrum_margin_db: $("spectrumMargin").value, activity_threshold_rms: $("activityThreshold").value})}); renderSettings(result); message("tuningMessage", "Airband tuning settings saved.", "good"); }
async function adjustSquelch(delta) { const result = await api("/api/settings/squelch", {method: "POST", body: JSON.stringify({delta_rms: delta})}); renderSettings(result); }
async function updateChannelControl(action, frequencyHz) { const result = await api("/api/channel-control", {method: "POST", body: JSON.stringify({action, frequency_hz: frequencyHz})}); renderSettings(result); message("channelMessage", action === "pause" ? "Channel paused for 10 minutes." : action === "block" ? "Channel blocked until cleared." : "Channel scan control cleared.", "good"); await loadNearby(); }
async function updateTunedChannel(action) { if (!currentTunedFrequency) return; await updateChannelControl(action, currentTunedFrequency); }
async function clearAllChannelControls() { const result = await api("/api/channel-control", {method: "POST", body: JSON.stringify({action: "clear_all"})}); renderSettings(result); message("channelMessage", "All paused and blocked channels were cleared.", "good"); await loadNearby(); }
function bindChannelControls() { document.querySelectorAll("[data-channel-action]").forEach((button) => button.addEventListener("click", () => run(() => updateChannelControl(button.dataset.channelAction, Number(button.dataset.channelFrequency))))); }
async function refresh() { try { const state = await api("/api/status"); render(state); $("status").textContent = "READY"; $("status").className = "pill ok"; } catch (error) { $("status").textContent = "OFFLINE"; $("status").className = "pill warn"; } }

$("scanFull").addEventListener("change", () => { scanScope = "full"; }); $("scanNearbyScope").addEventListener("change", () => { scanScope = "nearby"; }); $("start").addEventListener("click", () => run(() => scan())); $("skip").addEventListener("click", () => run(skipCurrent)); $("stop").addEventListener("click", () => run(stop)); $("tunedPause").addEventListener("click", () => run(() => updateTunedChannel("pause"))); $("tunedBlock").addEventListener("click", () => run(() => updateTunedChannel("block"))); $("clearAll").addEventListener("click", () => run(clearAllChannelControls)); $("find").addEventListener("click", () => run(findAirport)); $("saveLocation").addEventListener("click", () => run(saveLocation)); $("saveTuning").addEventListener("click", () => run(saveTuning)); $("squelchDown").addEventListener("click", () => run(() => adjustSquelch(-100))); $("squelchUp").addEventListener("click", () => run(() => adjustSquelch(100))); refresh(); loadNearby().catch(() => {}); setInterval(refresh, 5000);
