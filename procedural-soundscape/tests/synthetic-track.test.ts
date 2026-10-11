import assert from "node:assert/strict";
import test from "node:test";
import { getSoundscapeScene } from "../src/soundscape/scenes";
import { SoundscapeDriver } from "../src/soundscape/soundscape-driver";
import { lastIndexAtOrBefore, sampleSoundscape } from "../src/soundscape/soundscape-track";
import { createSyntheticTrack } from "../src/synthetic-track";

test("synthetic tracks are deterministic and bounded", () => {
  const first = createSyntheticTrack(96, 0.65, 7);
  const second = createSyntheticTrack(96, 0.65, 7);
  assert.equal(first.tempo, 96);
  assert.deepEqual(first.data, second.data);
  assert.deepEqual(first.beats, second.beats);
  assert.ok([...first.data].every((value) => value >= 0 && value <= 255));
  assert.equal(first.channelCount, 8);
});

test("sample interpolation and event lookup handle endpoints", () => {
  const track = createSyntheticTrack(120, 0.5);
  const out = sampleSoundscape(track, 0, new Float32Array(8));
  assert.equal(out.length, 8);
  assert.ok(out.every((value) => value >= 0 && value <= 1));
  assert.equal(lastIndexAtOrBefore(track.beats, -1), -1);
  assert.equal(lastIndexAtOrBefore(track.beats, 0), 0);
});

test("driver advances finite synthetic state", () => {
  const track = createSyntheticTrack(120, 0.8);
  const driver = new SoundscapeDriver(getSoundscapeScene("kinetic-light-trails"));
  let state = driver.update(1 / 60, 0, 0, track);
  for (let frame = 1; frame < 300; frame += 1) {
    const time = frame / 60;
    state = driver.update(1 / 60, time, time, track);
  }
  assert.ok(Number.isFinite(state.flow));
  assert.ok(Number.isFinite(state.intensity));
  assert.ok(state.flow > 0);
});
