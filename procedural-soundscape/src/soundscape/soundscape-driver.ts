import type { SoundscapeScene } from "./scenes";
import { lastIndexAtOrBefore, sampleSoundscape, type SoundscapeTrack } from "./soundscape-track";

/** Everything the renderer needs for one frame. Values are 0..1 unless noted. */
export type SoundscapeState = {
  /** Wall-clock seconds, for idle drift. */
  time: number;
  /** Integrated, music-paced motion phase (unbounded). */
  flow: number;
  sub: number;
  bass: number;
  mid: number;
  high: number;
  intensity: number;
  beat: number;
  downbeat: number;
  lift: number;
  anticipation: number;
  glitch: number;
  /** x, y, age (s), strength. */
  ring: Float32Array;
  /** Four bursts of x, y, age (s), strength. */
  bursts: Float32Array;
};

const BURST_SLOTS = 4;
const MIN_BURST_GAP_SECONDS = 0.16;

function follow(current: number, target: number, dt: number, attack: number, release: number) {
  const rate = target > current ? attack : release;
  return current + (target - current) * (1 - Math.exp(-rate * dt));
}

function smoothstep(edge0: number, edge1: number, value: number) {
  const t = Math.min(1, Math.max(0, (value - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

/** Deterministic 0..1 value per event time, so the same moment always looks the same. */
function hashTime(time: number, salt: number) {
  const x = Math.sin(time * 127.1 + salt * 311.7) * 43758.5453;
  return x - Math.floor(x);
}

function decayPulse(times: Float64Array, time: number, rate: number) {
  const index = lastIndexAtOrBefore(times, time);
  return index < 0 ? 0 : Math.exp(-(time - times[index]) * rate);
}

/**
 * Turns the generated track plus elapsed time into per-frame visual drive:
 * eased band levels, beat/downbeat pulses, onset bursts, and section-lift swells.
 */
export class SoundscapeDriver {
  private readonly scene: SoundscapeScene;
  private readonly frame = new Float32Array(8);
  private readonly state: SoundscapeState = {
    time: 0,
    flow: 0,
    sub: 0,
    bass: 0,
    mid: 0,
    high: 0,
    intensity: 0,
    beat: 0,
    downbeat: 0,
    lift: 0,
    anticipation: 0,
    glitch: 0,
    ring: new Float32Array([0, 0, 9, 0]),
    bursts: new Float32Array(BURST_SLOTS * 4).fill(9)
  };
  private playMix = 0;
  private lastSongTime: number | null = null;
  private onsetCursor = 0;
  private downbeatCursor = 0;
  private liftCursor = 0;
  private lastBurstAt = Number.NEGATIVE_INFINITY;
  private burstSlot = 0;

  constructor(scene: SoundscapeScene) {
    this.scene = scene;
    this.state.intensity = scene.idleIntensity;

    for (let slot = 0; slot < BURST_SLOTS; slot += 1) {
      this.state.bursts[slot * 4 + 3] = 0;
    }
  }

  update(dt: number, wallTime: number, songTime: number | null, track: SoundscapeTrack | null): SoundscapeState {
    const state = this.state;
    const scene = this.scene;
    const active = songTime !== null && track !== null;

    state.time = wallTime;
    this.playMix = follow(this.playMix, active ? 1 : 0, dt, 1.8, 1.2);

    let sub = 0.1;
    let bass = 0.12;
    let mid = 0.16;
    let high = 0.1;
    let intensity = scene.idleIntensity;

    if (active) {
      const frame = sampleSoundscape(track, songTime, this.frame);
      sub = frame[0];
      bass = Math.max(frame[1], frame[0] * 0.85);
      mid = (frame[2] + frame[3]) / 2;
      high = Math.max((frame[4] + frame[5]) / 2, frame[6] * 0.8);
      intensity = frame[7];
    }

    state.sub = follow(state.sub, sub, dt, 24, 5);
    state.bass = follow(state.bass, bass, dt, 28, 7);
    state.mid = follow(state.mid, mid, dt, 16, 5);
    state.high = follow(state.high, high, dt, 30, 9);
    state.intensity = follow(state.intensity, intensity, dt, 1.4, 0.8);

    let beat = 0;
    let downbeat = 0;
    let lift = 0;
    let anticipation = 0;

    if (active) {
      const time = songTime;
      const last = this.lastSongTime;
      const seeked = last === null || time < last - 0.05 || time - last > 0.75;

      if (seeked) {
        this.onsetCursor = lastIndexAtOrBefore(track.onsetTimes, time) + 1;
        this.downbeatCursor = lastIndexAtOrBefore(track.downbeats, time) + 1;
        this.liftCursor = lastIndexAtOrBefore(track.liftTimes, time) + 1;
      } else {
        this.fireCrossedEvents(time, track);
      }

      beat = decayPulse(track.beats, time, 6.5);
      downbeat = decayPulse(track.downbeats, time, 3.2);

      const liftIndex = lastIndexAtOrBefore(track.liftTimes, time);

      if (liftIndex >= 0) {
        lift = track.liftStrengths[liftIndex] * Math.exp(-(time - track.liftTimes[liftIndex]) * 1.1);
      }

      const nextLift = liftIndex + 1;

      if (nextLift < track.liftTimes.length) {
        const at = track.liftTimes[nextLift];
        anticipation = smoothstep(at - 3, at, time) * track.liftStrengths[nextLift] * 0.8;
      }

      this.lastSongTime = time;
    } else {
      this.lastSongTime = null;
    }

    const dynamics = 0.45 + 0.55 * state.intensity;
    state.beat = beat * dynamics * this.playMix;
    state.downbeat = downbeat * dynamics * this.playMix;
    state.lift = lift * this.playMix;
    state.anticipation = anticipation * this.playMix;
    state.glitch = Math.max(0, state.glitch - dt * 8);
    state.flow +=
      dt * scene.flowSpeed * (0.3 + 0.9 * state.intensity * this.playMix + 0.25 * (1 - this.playMix)) +
      dt * state.beat * scene.beatSurge;

    state.ring[2] += dt;

    for (let slot = 0; slot < BURST_SLOTS; slot += 1) {
      state.bursts[slot * 4 + 2] += dt;
    }

    return state;
  }

  private fireCrossedEvents(time: number, track: SoundscapeTrack) {
    const scene = this.scene;

    while (this.onsetCursor < track.onsetTimes.length && track.onsetTimes[this.onsetCursor] <= time) {
      const at = track.onsetTimes[this.onsetCursor];
      const strength = track.onsetStrengths[this.onsetCursor];

      if (strength >= scene.burst.threshold && at - this.lastBurstAt >= MIN_BURST_GAP_SECONDS) {
        this.fireBurst(at, strength);

        if (scene.glitch > 0 && strength > 0.85) {
          this.state.glitch = 1;
        }
      }

      this.onsetCursor += 1;
    }

    while (this.downbeatCursor < track.downbeats.length && track.downbeats[this.downbeatCursor] <= time) {
      if (scene.downbeatRing > 0 && this.state.intensity >= scene.downbeatRing) {
        this.fireRing(0.45 + 0.4 * this.state.intensity);
      }

      this.downbeatCursor += 1;
    }

    while (this.liftCursor < track.liftTimes.length && track.liftTimes[this.liftCursor] <= time) {
      if (scene.liftRing) {
        this.fireRing(0.7 + 0.3 * track.liftStrengths[this.liftCursor]);
      }

      this.liftCursor += 1;
    }
  }

  private fireBurst(at: number, strength: number) {
    const [x0, x1, y0, y1] = this.scene.burst.area;
    const offset = this.burstSlot * 4;
    const bursts = this.state.bursts;

    bursts[offset] = x0 + (x1 - x0) * hashTime(at, 1);
    bursts[offset + 1] = y0 + (y1 - y0) * hashTime(at, 2);
    bursts[offset + 2] = 0;
    bursts[offset + 3] = 0.55 + 0.45 * strength;
    this.burstSlot = (this.burstSlot + 1) % BURST_SLOTS;
    this.lastBurstAt = at;
  }

  private fireRing(strength: number) {
    const ring = this.state.ring;

    // Keep a fresh, stronger ring instead of restarting it on every event.
    if (ring[2] < 0.35 && ring[3] >= strength) {
      return;
    }

    ring[0] = this.scene.ringOrigin[0];
    ring[1] = this.scene.ringOrigin[1];
    ring[2] = 0;
    ring[3] = strength;
  }
}
