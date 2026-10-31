import assert from "node:assert/strict";
import test from "node:test";
import { PlaybackClock } from "../src/playback-clock";

test("elapsed time advances while playing", () => {
  const clock = new PlaybackClock(1000);
  assert.equal(clock.playing, true);
  assert.equal(clock.elapsed(1000), 0);
  assert.equal(clock.elapsed(3500), 2.5);
  assert.equal(clock.elapsed(500), 0, "never negative");
});

test("regression: resume continues from the paused position instead of restarting at 0", () => {
  const clock = new PlaybackClock(0);
  clock.pause(4000);
  assert.equal(clock.playing, false);
  assert.equal(clock.elapsed(4000), 4);
  assert.equal(clock.elapsed(9000), 4, "elapsed is frozen while paused");
  clock.resume(9000);
  assert.equal(clock.playing, true);
  assert.equal(clock.elapsed(9000), 4);
  assert.equal(clock.elapsed(10000), 5);
});

test("pause and resume are idempotent", () => {
  const clock = new PlaybackClock(0);
  clock.pause(2000);
  clock.pause(5000);
  assert.equal(clock.elapsed(5000), 2);
  clock.resume(6000);
  clock.resume(8000);
  assert.equal(clock.elapsed(8000), 4);
});

test("restart returns to zero and keeps the play state", () => {
  const playing = new PlaybackClock(0);
  playing.restart(7000);
  assert.equal(playing.elapsed(7500), 0.5);

  const paused = new PlaybackClock(0);
  paused.pause(3000);
  paused.restart(7000);
  assert.equal(paused.playing, false);
  assert.equal(paused.elapsed(9000), 0);
  paused.resume(9000);
  assert.equal(paused.elapsed(10000), 1);
});
