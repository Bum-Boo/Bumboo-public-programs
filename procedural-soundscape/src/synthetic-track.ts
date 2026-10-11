import { SOUNDSCAPE_CHANNELS, type SoundscapeTrack } from "./soundscape/soundscape-track";

const FPS = 20;
const DURATION_SECONDS = 96;

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value));
}

function hash(index: number, seed: number) {
  const value = Math.sin(index * 12.9898 + seed * 78.233) * 43758.5453;
  return value - Math.floor(value);
}

/** Build deterministic rhythm and frequency-band data without reading or playing audio. */
export function createSyntheticTrack(bpm: number, strength: number, seed = 7): SoundscapeTrack {
  const tempo = Math.max(40, Math.min(200, Math.round(bpm)));
  const level = clamp01(strength);
  const frameCount = FPS * DURATION_SECONDS;
  const channelCount = SOUNDSCAPE_CHANNELS.length;
  const data = new Uint8Array(frameCount * channelCount);
  const beatStep = 60 / tempo;

  for (let frame = 0; frame < frameCount; frame += 1) {
    const time = frame / FPS;
    const beatPhase = (time % beatStep) / beatStep;
    const beat = Math.exp(-beatPhase * 10);
    const slow = 0.5 + 0.5 * Math.sin(time * 0.31 + seed);
    const pulse = beat * (0.45 + 0.55 * level);
    const values = [
      0.08 + 0.68 * pulse,
      0.12 + 0.72 * pulse,
      0.12 + 0.42 * slow,
      0.18 + 0.48 * (0.5 + 0.5 * Math.sin(time * 1.7 + 1.1)),
      0.08 + 0.7 * hash(frame, seed),
      0.06 + 0.6 * hash(frame + 91, seed),
      beat,
      0.16 + 0.76 * level * (0.36 + 0.64 * slow)
    ];
    for (let channel = 0; channel < channelCount; channel += 1) {
      data[frame * channelCount + channel] = Math.round(clamp01(values[channel]) * 255);
    }
  }

  const beatTimes: number[] = [];
  const downbeats: number[] = [];
  const onsetTimes: number[] = [];
  const onsetStrengths: number[] = [];
  const liftTimes: number[] = [];
  const liftStrengths: number[] = [];
  const beatCount = Math.floor(DURATION_SECONDS / beatStep);

  for (let beat = 0; beat < beatCount; beat += 1) {
    const time = beat * beatStep;
    beatTimes.push(time);
    if (beat % 4 === 0) downbeats.push(time);
    onsetTimes.push(time);
    onsetStrengths.push(0.42 + 0.58 * level * (0.5 + 0.5 * hash(beat, seed + 13)));
    if (beat > 0 && beat % 16 === 0) {
      liftTimes.push(time);
      liftStrengths.push(0.4 + 0.6 * level);
    }
  }

  return {
    fps: FPS,
    frameCount,
    channelCount,
    data,
    tempo,
    beats: Float64Array.from(beatTimes),
    downbeats: Float64Array.from(downbeats),
    onsetTimes: Float64Array.from(onsetTimes),
    onsetStrengths: Float32Array.from(onsetStrengths),
    liftTimes: Float64Array.from(liftTimes),
    liftStrengths: Float32Array.from(liftStrengths)
  };
}
