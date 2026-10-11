/**
 * Procedural visual presets for generated, synthetic signals. Coordinates are normalized: x and y
 * in -1..1 across the viewport. These palettes are authored values; no image or recording is loaded.
 */
export type SoundscapeScene = {
  /** Preset colour palette. */
  fallback: [string, string, string];
  tone: {
    /** Darkness of the gaps between colour masses, and peak brightness of the masses. */
    floor: number;
    ceiling: number;
    /** Applied to the authored preset colours. */
    saturation: number;
    /** >1 deepens the falloff between masses, <1 lifts it (milky). */
    contrast: number;
    /** Pulls colours toward the preset accent. */
    tint: string;
    tintMix: number;
  };
  /** Size of the colour masses. */
  zoom: number;
  /** How much the field sways. */
  warp: number;
  /** Speed of the colour masses' orbits. */
  drift: number;
  grain: number;
  /** Signature treatments, 0 disables. */
  caustics: number;
  /** Soft light sheen sweeping across the field. */
  iridescence: number;
  /** Radial speed smear toward the centre on beats. */
  smear: number;
  /** Heartbeat bulge from the centre on beats. */
  bulge: number;
  /** RGB split and slice tearing on hard hits. */
  glitch: number;
  flowSpeed: number;
  beatSurge: number;
  idleIntensity: number;
  burst: { threshold: number; area: [number, number, number, number] };
  /** Downbeats send a ripple through the field above this intensity (0 disables). */
  downbeatRing: number;
  /** Section lifts also send the ripple. */
  liftRing: boolean;
  ringOrigin: [number, number];
};

const aquarium: SoundscapeScene = {
  fallback: ["#020a0c", "#0c3a3a", "#6fd6c4"],
  tone: { floor: 0.05, ceiling: 0.5, saturation: 1.15, contrast: 1.35, tint: "#20c4ae", tintMix: 0.22 },
  zoom: 1,
  warp: 0.55,
  drift: 0.8,
  grain: 0.035,
  caustics: 0.55,
  iridescence: 0,
  smear: 0,
  bulge: 0,
  glitch: 0,
  flowSpeed: 1,
  beatSurge: 1.1,
  idleIntensity: 0.3,
  burst: { threshold: 0.62, area: [-0.8, 0.8, -0.7, 0.5] },
  downbeatRing: 0,
  liftRing: true,
  ringOrigin: [0, 0.2]
};

const brutal: SoundscapeScene = {
  fallback: ["#050102", "#3a060b", "#ff3b2e"],
  tone: { floor: 0.05, ceiling: 0.6, saturation: 1.25, contrast: 1.35, tint: "#ff1e10", tintMix: 0.4 },
  zoom: 0.92,
  warp: 0.5,
  drift: 1,
  grain: 0.065,
  caustics: 0,
  iridescence: 0,
  smear: 0,
  bulge: 0,
  glitch: 1,
  flowSpeed: 1.2,
  beatSurge: 2.2,
  idleIntensity: 0.28,
  burst: { threshold: 0.55, area: [-0.7, 0.7, -0.6, 0.4] },
  downbeatRing: 0.55,
  liftRing: true,
  ringOrigin: [0, -0.05]
};

const crush: SoundscapeScene = {
  fallback: ["#04100a", "#1d5a2c", "#b8f5b0"],
  tone: { floor: 0.05, ceiling: 0.55, saturation: 1.1, contrast: 1.3, tint: "#6ff09a", tintMix: 0.12 },
  zoom: 1.05,
  warp: 0.5,
  drift: 0.7,
  grain: 0.03,
  caustics: 0,
  iridescence: 0,
  smear: 0,
  bulge: 1,
  glitch: 0,
  flowSpeed: 0.85,
  beatSurge: 0.9,
  idleIntensity: 0.32,
  burst: { threshold: 0.6, area: [-0.6, 0.6, -0.5, 0.5] },
  downbeatRing: 0,
  liftRing: true,
  ringOrigin: [0, 0]
};

const movin: SoundscapeScene = {
  fallback: ["#03040a", "#1c2350", "#9fd8ff"],
  tone: { floor: 0.045, ceiling: 0.48, saturation: 1.35, contrast: 1.4, tint: "#7fb8ff", tintMix: 0.05 },
  zoom: 0.95,
  warp: 0.55,
  drift: 1.3,
  grain: 0.04,
  caustics: 0,
  iridescence: 0.22,
  smear: 1,
  bulge: 0,
  glitch: 0,
  flowSpeed: 1.4,
  beatSurge: 2,
  idleIntensity: 0.3,
  burst: { threshold: 0.6, area: [-0.8, 0.8, -0.6, 0.6] },
  downbeatRing: 0,
  liftRing: true,
  ringOrigin: [0, 0]
};

const plush: SoundscapeScene = {
  fallback: ["#0b0c14", "#3a4166", "#e8ecff"],
  tone: { floor: 0.06, ceiling: 0.46, saturation: 1.35, contrast: 1.2, tint: "#b9b4ff", tintMix: 0.18 },
  zoom: 1.05,
  warp: 0.45,
  drift: 0.55,
  grain: 0.04,
  caustics: 0,
  iridescence: 0.1,
  smear: 0,
  bulge: 0.35,
  glitch: 0,
  flowSpeed: 0.7,
  beatSurge: 0.9,
  idleIntensity: 0.3,
  burst: { threshold: 0.62, area: [-0.8, 0.8, -0.7, 0.6] },
  downbeatRing: 0,
  liftRing: true,
  ringOrigin: [0, 0.1]
};

const scenes: Record<string, SoundscapeScene> = {
  "aquarium-caustic-field": aquarium,
  "impact-tear-glitch": brutal,
  "lush-bloom-prism": crush,
  "kinetic-light-trails": movin,
  "soft-static-fiber-field": plush
};

export function getSoundscapeScene(preset: string): SoundscapeScene {
  return scenes[preset] ?? movin;
}
