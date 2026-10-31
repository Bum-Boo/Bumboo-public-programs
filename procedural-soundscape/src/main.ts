import "./global.css";
import { getSoundscapeScene } from "./soundscape/scenes";
import { SoundscapeDriver } from "./soundscape/soundscape-driver";
import { SoundscapeRenderer } from "./soundscape/soundscape-renderer";
import { PlaybackClock } from "./playback-clock";
import { createSyntheticTrack } from "./synthetic-track";

function required<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing required element: ${selector}`);
  return element;
}

const canvas = required<HTMLCanvasElement>("#field");
const tempo = required<HTMLInputElement>("#tempo");
const tempoValue = required<HTMLOutputElement>("#tempo-value");
const strength = required<HTMLInputElement>("#intensity");
const strengthValue = required<HTMLOutputElement>("#intensity-value");
const preset = required<HTMLSelectElement>("#preset");
const toggle = required<HTMLButtonElement>("#toggle");
const status = required<HTMLElement>("#status");

let track = createSyntheticTrack(Number(tempo.value), Number(strength.value) / 100);
let scene = getSoundscapeScene(preset.value);
let renderer = SoundscapeRenderer.create(canvas, scene, { lowPower: matchMedia("(pointer: coarse)").matches });
let driver = new SoundscapeDriver(scene);
let renderState = driver.update(0, 0, 0, track);
const clock = new PlaybackClock(performance.now());
let lastFrame = performance.now();
let frameId = 0;

if (!renderer) {
  status.textContent = "WebGL2 is unavailable in this browser. Try a browser with WebGL2 enabled.";
  toggle.disabled = true;
} else {
  status.textContent = "WebGL2 ready · generated signal active";
}

function resize() {
  if (renderer) renderer.resize(canvas.clientWidth, canvas.clientHeight, 0.8);
}
const observer = new ResizeObserver(resize);
observer.observe(canvas);
window.addEventListener("beforeunload", () => {
  observer.disconnect();
  if (frameId) cancelAnimationFrame(frameId);
  renderer?.dispose();
}, { once: true });
resize();

function regenerate() {
  track = createSyntheticTrack(Number(tempo.value), Number(strength.value) / 100);
  driver = new SoundscapeDriver(scene);
  renderState = driver.update(0, 0, 0, track);
  clock.restart(performance.now());
  tempoValue.value = `${track.tempo} BPM`;
  strengthValue.value = `${strength.value}%`;
}
tempo.addEventListener("input", regenerate);
strength.addEventListener("input", regenerate);
preset.addEventListener("change", () => {
  scene = getSoundscapeScene(preset.value);
  renderer?.dispose();
  renderer = SoundscapeRenderer.create(canvas, scene, { lowPower: matchMedia("(pointer: coarse)").matches });
  driver = new SoundscapeDriver(scene);
  renderState = driver.update(0, 0, 0, track);
  resize();
});
toggle.addEventListener("click", () => {
  const now = performance.now();
  if (clock.playing) clock.pause(now);
  else clock.resume(now);
  toggle.textContent = clock.playing ? "Pause motion" : "Resume motion";
  toggle.setAttribute("aria-pressed", String(clock.playing));
});

function animate(now: number) {
  frameId = requestAnimationFrame(animate);
  if (!renderer) return;
  const dt = Math.min(0.1, Math.max(0, (now - lastFrame) / 1000));
  lastFrame = now;
  const elapsed = clock.elapsed(now);
  const songTime = clock.playing ? elapsed % (track.frameCount / track.fps) : null;
  if (clock.playing) renderState = driver.update(dt, elapsed, songTime, track);
  renderer.render(renderState);
}
frameId = requestAnimationFrame(animate);
