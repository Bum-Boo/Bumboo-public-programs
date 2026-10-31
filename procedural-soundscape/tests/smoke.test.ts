import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { getSoundscapeScene } from "../src/soundscape/scenes";
import { SoundscapeDriver, type SoundscapeState } from "../src/soundscape/soundscape-driver";
import { SOUNDSCAPE_CHANNELS } from "../src/soundscape/soundscape-track";
import { createSyntheticTrack } from "../src/synthetic-track";

const indexHtml = readFileSync(fileURLToPath(new URL("../index.html", import.meta.url)), "utf8");

function attr(html: string, id: string, name: string) {
  const tag = html.match(new RegExp(`<input[^>]*id="${id}"[^>]*>`))?.[0] ?? "";
  return Number(tag.match(new RegExp(`${name}="([^"]+)"`))?.[1]);
}

const presetValues = [...indexHtml.matchAll(/<option value="([^"]+)"/g)].map((match) => match[1]);
const tempoRange = { min: attr(indexHtml, "tempo", "min"), max: attr(indexHtml, "tempo", "max"), value: attr(indexHtml, "tempo", "value") };
const strengthRange = { min: attr(indexHtml, "intensity", "min"), max: attr(indexHtml, "intensity", "max"), value: attr(indexHtml, "intensity", "value") };

function assertFiniteState(state: SoundscapeState, label: string) {
  for (const [key, value] of Object.entries(state)) {
    if (value instanceof Float32Array) {
      assert.ok(value.every(Number.isFinite), `${label}: ${key} has non-finite values`);
    } else {
      assert.ok(Number.isFinite(value), `${label}: ${key}=${value}`);
    }
  }
}

test("smoke: index.html controls match the documented UI", () => {
  assert.deepEqual(presetValues, [
    "kinetic-light-trails",
    "aquarium-caustic-field",
    "impact-tear-glitch",
    "lush-bloom-prism",
    "soft-static-fiber-field"
  ]);
  assert.deepEqual(tempoRange, { min: 60, max: 160, value: 96 });
  assert.deepEqual(strengthRange, { min: 15, max: 95, value: 65 });
  assert.match(indexHtml, /<button id="toggle"[^>]*>Pause motion<\/button>/);
  assert.match(indexHtml, /<canvas id="field"/);
});

test("smoke: every preset option maps to its own valid scene", () => {
  const fallback = getSoundscapeScene("no-such-preset");
  assert.equal(fallback, getSoundscapeScene("kinetic-light-trails"), "unknown presets fall back to kinetic-light-trails");
  const seen = new Set();
  for (const preset of presetValues) {
    const scene = getSoundscapeScene(preset);
    assert.ok(!seen.has(scene), `${preset} reuses another preset's scene`);
    seen.add(scene);
    for (const colour of [...scene.fallback, scene.tone.tint]) {
      assert.match(colour, /^#[0-9a-f]{6}$/i, `${preset}: colour ${colour}`);
    }
    const [x0, x1, y0, y1] = scene.burst.area;
    assert.ok(-1 <= x0 && x0 < x1 && x1 <= 1 && -1 <= y0 && y0 < y1 && y1 <= 1, `${preset}: burst area`);
    assert.ok(scene.ringOrigin.every((value) => value >= -1 && value <= 1), `${preset}: ring origin`);
    assert.ok(scene.tone.floor >= 0 && scene.tone.floor < scene.tone.ceiling && scene.tone.ceiling <= 1, `${preset}: tone`);
    assert.ok(scene.flowSpeed > 0 && scene.idleIntensity > 0 && scene.idleIntensity < 1, `${preset}: motion`);
  }
});

test("smoke: synthetic tracks follow tempo across the slider range", () => {
  const duration = 96;
  for (let bpm = tempoRange.min; bpm <= tempoRange.max; bpm += 10) {
    for (const percent of [strengthRange.min, strengthRange.value, strengthRange.max]) {
      const track = createSyntheticTrack(bpm, percent / 100);
      const beatStep = 60 / bpm;
      assert.equal(track.tempo, bpm);
      assert.equal(track.channelCount, SOUNDSCAPE_CHANNELS.length);
      assert.equal(track.frameCount, track.fps * duration);
      assert.equal(track.data.length, track.frameCount * track.channelCount);
      assert.equal(track.beats.length, Math.floor(duration / beatStep));
      assert.ok(track.beats.every((time, index) => Math.abs(time - index * beatStep) < 1e-9));
      assert.equal(track.downbeats.length, Math.ceil(track.beats.length / 4));
      assert.equal(track.onsetTimes.length, track.onsetStrengths.length);
      assert.equal(track.liftTimes.length, track.liftStrengths.length);
      assert.equal(track.liftTimes.length, Math.floor((track.beats.length - 1) / 16));
      assert.ok(track.onsetStrengths.every((value) => value >= 0.42 && value <= 1));
      assert.ok(track.liftStrengths.every((value) => value >= 0.4 && value <= 1));
    }
  }
});

test("smoke: tempo and strength are clamped and seed changes only the noise", () => {
  assert.equal(createSyntheticTrack(10, 0.5).tempo, 40);
  assert.equal(createSyntheticTrack(999, 0.5).tempo, 200);
  assert.equal(createSyntheticTrack(95.6, 0.5).tempo, 96);
  assert.deepEqual(createSyntheticTrack(120, -3).data, createSyntheticTrack(120, 0).data);
  assert.deepEqual(createSyntheticTrack(120, 7).data, createSyntheticTrack(120, 1).data);

  const seven = createSyntheticTrack(120, 0.5, 7);
  const eight = createSyntheticTrack(120, 0.5, 8);
  assert.notDeepEqual(seven.data, eight.data);
  assert.deepEqual(seven.beats, eight.beats);

  const weak = createSyntheticTrack(120, 0.15);
  const strong = createSyntheticTrack(120, 0.95);
  const meanIntensity = (track: typeof weak) => {
    let sum = 0;
    for (let frame = 0; frame < track.frameCount; frame += 1) sum += track.data[frame * track.channelCount + 7];
    return sum / track.frameCount;
  };
  assert.ok(meanIntensity(strong) > meanIntensity(weak) * 2, "strength raises the intensity channel");
});

test("smoke: every scene renders a full loop with events, wrap-around and pause", () => {
  const track = createSyntheticTrack(tempoRange.max, strengthRange.max / 100);
  const loopSeconds = track.frameCount / track.fps;
  const dt = 1 / 30;

  for (const preset of presetValues) {
    const scene = getSoundscapeScene(preset);
    const driver = new SoundscapeDriver(scene);
    let state = driver.update(0, 0, 0, track);
    let burstsFired = 0;
    let ringsFired = 0;
    let glitched = false;
    let peakBeat = 0;
    let previousBurstAges = Array.from({ length: 4 }, (_, slot) => state.bursts[slot * 4 + 2]);
    let previousRingAge = state.ring[2];

    // Run slightly past one loop so the song time wraps back to 0 like the app's animation loop.
    for (let step = 1; step * dt <= loopSeconds + 4; step += 1) {
      const elapsed = step * dt;
      state = driver.update(dt, elapsed, elapsed % loopSeconds, track);
      for (let slot = 0; slot < 4; slot += 1) {
        const age = state.bursts[slot * 4 + 2];
        if (age < previousBurstAges[slot]) burstsFired += 1;
        previousBurstAges[slot] = age;
      }
      if (state.ring[2] < previousRingAge) ringsFired += 1;
      previousRingAge = state.ring[2];
      glitched ||= state.glitch > 0;
      peakBeat = Math.max(peakBeat, state.beat);
      for (const key of ["sub", "bass", "mid", "high", "intensity", "beat", "downbeat", "lift", "anticipation", "glitch"] as const) {
        assert.ok(state[key] >= 0 && state[key] <= 1.0001, `${preset}: ${key}=${state[key]} at ${elapsed}s`);
      }
    }

    assertFiniteState(state, preset);
    assert.ok(burstsFired > 10, `${preset}: onset bursts fired (${burstsFired})`);
    assert.ok(peakBeat > 0.3, `${preset}: beat pulse visible (${peakBeat})`);
    if (scene.liftRing) assert.ok(ringsFired >= track.liftTimes.length, `${preset}: lift rings fired (${ringsFired})`);
    assert.equal(glitched, scene.glitch > 0, `${preset}: glitch only for glitch scenes`);

    // Paused frames (songTime null) fade the pulses out instead of freezing them on.
    for (let step = 0; step < 120; step += 1) state = driver.update(dt, loopSeconds + 4 + step * dt, null, track);
    assertFiniteState(state, `${preset} paused`);
    assert.ok(state.beat < 0.01 && state.lift < 0.01, `${preset}: pulses fade when inactive`);
  }
});

test("smoke: seeking does not replay skipped events", () => {
  const track = createSyntheticTrack(120, 0.95);
  const driver = new SoundscapeDriver(getSoundscapeScene("impact-tear-glitch"));
  driver.update(1 / 60, 0, 10, track);
  const state = driver.update(1 / 60, 1 / 60, 60, track);
  assert.ok(state.bursts.filter((_, index) => index % 4 === 2).every((age) => age > 0), "no burst fired by the jump");
  assert.equal(state.glitch, 0);
});
