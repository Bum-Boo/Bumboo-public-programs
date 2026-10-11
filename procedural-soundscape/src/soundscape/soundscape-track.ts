/** Synthetic-only track data used to drive the procedural visualizer. No audio is loaded or played. */
export type SoundscapeTrack = {
  fps: number;
  frameCount: number;
  channelCount: number;
  data: Uint8Array;
  tempo: number;
  beats: Float64Array;
  downbeats: Float64Array;
  onsetTimes: Float64Array;
  onsetStrengths: Float32Array;
  liftTimes: Float64Array;
  liftStrengths: Float32Array;
};

export const SOUNDSCAPE_CHANNELS = ["sub", "bass", "lowmid", "mid", "high", "air", "onset", "intensity"] as const;

/** Linearly interpolated channel values (0..1) at `time`, written into `out`. */
export function sampleSoundscape(track: SoundscapeTrack, time: number, out: Float32Array) {
  const position = Math.min(track.frameCount - 1, Math.max(0, time * track.fps));
  const index = Math.floor(position);
  const next = Math.min(track.frameCount - 1, index + 1);
  const mix = position - index;
  const stride = track.channelCount;

  for (let channel = 0; channel < out.length; channel += 1) {
    const a = track.data[index * stride + channel] ?? 0;
    const b = track.data[next * stride + channel] ?? 0;
    out[channel] = (a + (b - a) * mix) / 255;
  }

  return out;
}

/** Index of the last entry <= time, or -1. */
export function lastIndexAtOrBefore(sorted: ArrayLike<number>, time: number) {
  let low = 0;
  let high = sorted.length - 1;
  let found = -1;

  while (low <= high) {
    const middle = (low + high) >>> 1;
    if (sorted[middle] <= time) {
      found = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }

  return found;
}
