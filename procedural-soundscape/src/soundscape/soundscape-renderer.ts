import type { SoundscapeScene } from "./scenes";
import type { SoundscapeState } from "./soundscape-driver";

const VERTEX = `#version 300 es
out vec2 vUv;
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  vUv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

/*
 * A full-screen field of domain-warped noise; generated signal bands bend its flow.
 */
/*
 * A moving mesh gradient with five soft colour masses drifting on slow orbits.
 * Synthetic band levels and pulses bend the field without loading any media.
 */
const FRAGMENT = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;
uniform vec3 uPal[5];
uniform vec3 uBase;
uniform float uAspect;
uniform float uTime;
uniform float uFlow;
uniform vec4 uBands;
uniform vec4 uPulse;
uniform float uIntensity;
uniform float uGlitch;
uniform vec3 uTone;
uniform vec4 uShape;
uniform vec4 uFx;
uniform float uGlitchAmount;
uniform vec4 uRing;
uniform vec4 uBurst[4];

float hash12(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

float vnoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash12(i), hash12(i + vec2(1.0, 0.0)), u.x), mix(hash12(i + vec2(0.0, 1.0)), hash12(i + vec2(1.0, 1.0)), u.x), u.y);
}

float fbm(vec2 p) {
  float value = 0.0;
  float amplitude = 0.5;
  for (int i = 0; i < 3; i++) {
    value += amplitude * vnoise(p);
    p = p * 2.07 + vec2(1.7, 9.2);
    amplitude *= 0.5;
  }
  return value / 0.875;
}

float caustic(vec2 uv, float t) {
  vec2 p = mod(uv * 6.28318, 6.28318) - 250.0;
  vec2 i = p;
  float c = 1.0;
  for (int n = 0; n < 4; n++) {
    float tt = t * (1.0 - 3.5 / float(n + 1));
    i = p + vec2(cos(tt - i.x) + sin(tt + i.y), sin(tt - i.y) + cos(tt + i.x));
    c += 1.0 / length(vec2(p.x / (sin(i.x + tt) / 0.005), p.y / (cos(i.y + tt) / 0.005)));
  }
  c = 1.17 - pow(c / 4.0, 1.4);
  return pow(abs(c), 8.0);
}

vec3 field(vec2 q, float t, float swell) {
  vec3 acc = vec3(0.0);
  float total = 0.0;
  for (int i = 0; i < 5; i++) {
    float fi = float(i);
    vec2 c = vec2(sin(t * (0.83 + 0.21 * fi) + fi * 1.7) * 0.78 * uAspect, cos(t * (0.67 + 0.17 * fi) + fi * 2.3) * 0.62);
    float radius = uShape.x * (0.95 - 0.08 * fi) * swell;
    vec2 d = q - c;
    float weight = exp(-dot(d, d) / (radius * radius));
    acc += uPal[i] * weight;
    total += weight;
  }
  vec3 blend = acc / max(total, 1e-4);
  return mix(uBase, blend, 1.0 - exp(-total * 1.6));
}

void main() {
  vec2 p = vec2((vUv.x * 2.0 - 1.0) * uAspect, vUv.y * 2.0 - 1.0);
  float bass = uBands.y;
  float mid = uBands.z;
  float beat = uPulse.x;
  float down = uPulse.y;
  float lift = uPulse.z;
  float antic = uPulse.w;
  float r = length(p);

  // Build-up before a chorus draws the field inward; the chorus releases it.
  p *= 1.0 - 0.06 * antic + 0.05 * lift;
  // Bulge scenes pulse from the centre on beats.
  p *= 1.0 - uFx.w * (0.06 * beat + 0.035 * down) * smoothstep(1.6, 0.0, r);

  if (uGlitch > 0.001 && uGlitchAmount > 0.0) {
    float band = floor(vUv.y * 18.0);
    float jitter = hash12(vec2(band, floor(uTime * 20.0)));
    p.x += (jitter - 0.5) * 0.24 * uGlitch * uGlitchAmount * step(0.6, jitter);
  }

  float t = uFlow * 0.05 * uShape.z + uTime * 0.01;
  vec2 q = p;
  vec2 w = vec2(fbm(q * 0.9 + vec2(0.0, t)), fbm(q * 0.9 + vec2(5.2, -t * 0.9))) - 0.5;
  q += w * uShape.y * (1.0 + 0.5 * bass + 0.35 * beat + 0.7 * lift);
  // Bass and choruses let the colour masses breathe outward.
  float swell = 1.0 + 0.16 * bass + 0.08 * beat + 0.28 * lift + 0.08 * uIntensity;

  vec3 col;

  if (uFx.z > 0.0) {
    // Speed smear toward the centre (night drive).
    float k = uFx.z * (0.025 + 0.07 * beat + 0.035 * uIntensity + 0.09 * lift);
    col = vec3(0.0);
    for (int i = 0; i < 4; i++) {
      col += field(q * (1.0 - k * float(i)), t, swell);
    }
    col *= 0.25;
  } else if (uGlitch > 0.001 && uGlitchAmount > 0.0) {
    float split = 0.05 * uGlitch * uGlitchAmount;
    col = vec3(field(q + vec2(split, 0.0), t, swell).r, field(q, t, swell).g, field(q - vec2(split, 0.0), t, swell).b);
  } else {
    col = field(q, t, swell);
  }

  col = pow(max(col, 0.0), vec3(uTone.z));
  float gain = 0.74 + 0.2 * uIntensity + 0.12 * bass + 0.08 * beat + 0.3 * lift + 0.08 * antic;
  col = clamp(col, 0.0, 1.0) * uTone.y * gain + uTone.x;

  if (uFx.x > 0.0) {
    // Light through water, coloured by the field beneath it.
    float c = caustic(p * 0.85 + vec2(uTime * 0.02, uFlow * 0.012), uTime * 0.4 + uFlow * 0.05);
    col += (col * 2.2 + 0.02) * c * uFx.x * (0.1 + 0.25 * mid + 0.15 * beat + 0.3 * lift) * smoothstep(-1.2, 1.0, p.y);
  }

  if (uFx.y > 0.0) {
    // Soft sheen sweeping across the field.
    float band = exp(-pow((p.x + p.y * 0.6) * 0.9 - sin(t * 0.7) * 1.4, 2.0) * 2.5);
    col += col * band * uFx.y * (0.35 + 0.4 * lift + 0.2 * beat);
  }

  // Strong hits bloom locally through the field.
  for (int i = 0; i < 4; i++) {
    vec4 b = uBurst[i];
    if (b.w > 0.0 && b.z < 1.2) {
      vec2 d = p - vec2(b.x * uAspect, b.y);
      float radius = 0.2 + b.z * 0.55;
      col *= 1.0 + exp(-dot(d, d) / (radius * radius)) * b.w * exp(-b.z * 3.0) * 0.5;
    }
  }

  // A soft wave of light rolls out on downbeats and section lifts.
  if (uRing.w > 0.001 && uRing.z < 3.0) {
    float front = length(p - vec2(uRing.x * uAspect, uRing.y)) - uRing.z * 1.3;
    col *= 1.0 + exp(-front * front * 6.0) * exp(-uRing.z * 1.4) * uRing.w * 0.3;
  }

  // Vignette keeps the collage the brightest thing on screen.
  vec2 v = (vUv - 0.5) * vec2(1.0, 1.15);
  col *= 1.0 - 0.42 * smoothstep(0.3, 0.9, length(v));

  col += (hash12(gl_FragCoord.xy + fract(uTime * 7.31) * 913.0) - 0.5) * uShape.w;
  outColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}`;

type Uniforms = Record<string, WebGLUniformLocation | null>;
type Rgb = [number, number, number];

const PALETTE_SIZE = 5;

export type SoundscapeRendererOptions = {
  /** Phones and coarse-pointer devices. */
  lowPower: boolean;
};

function hexToRgb(value: string): Rgb {
  const parsed = Number.parseInt(value.replace("#", ""), 16);
  return [((parsed >> 16) & 255) / 255, ((parsed >> 8) & 255) / 255, (parsed & 255) / 255];
}

function compileProgram(gl: WebGL2RenderingContext, vertexSource: string, fragmentSource: string) {
  const program = gl.createProgram();
  const shaders = [
    [gl.VERTEX_SHADER, vertexSource],
    [gl.FRAGMENT_SHADER, fragmentSource]
  ] as const;

  for (const [type, source] of shaders) {
    const shader = gl.createShader(type);

    if (!shader) {
      throw new Error("Shader allocation failed");
    }

    gl.shaderSource(shader, source);
    gl.compileShader(shader);

    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(shader) ?? "Shader compile failed");
    }

    gl.attachShader(program, shader);
    gl.deleteShader(shader);
  }

  gl.linkProgram(program);

  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(program) ?? "Program link failed");
  }

  return program;
}

const UNIFORM_NAMES = [
  "uPal", "uBase", "uAspect", "uTime", "uFlow", "uBands", "uPulse", "uIntensity", "uGlitch", "uTone", "uShape", "uFx",
  "uGlitchAmount", "uRing", "uBurst"
];

/** WebGL2 renderer for a synthetic procedural colour field. */
export class SoundscapeRenderer {
  private readonly gl: WebGL2RenderingContext;
  private readonly canvas: HTMLCanvasElement;
  private readonly scene: SoundscapeScene;
  private readonly program: WebGLProgram;
  private readonly uniforms: Uniforms;
  private readonly vao: WebGLVertexArrayObject;
  private readonly palette = new Float32Array(PALETTE_SIZE * 3);
  private readonly base = new Float32Array(3);

  static create(canvas: HTMLCanvasElement, scene: SoundscapeScene, options: SoundscapeRendererOptions) {
    const gl = canvas.getContext("webgl2", {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      premultipliedAlpha: false,
      powerPreference: options.lowPower ? "low-power" : "default"
    });

    if (!gl) {
      return null;
    }

    try {
      return new SoundscapeRenderer(canvas, gl, scene);
    } catch {
      return null;
    }
  }

  private constructor(canvas: HTMLCanvasElement, gl: WebGL2RenderingContext, scene: SoundscapeScene) {
    this.canvas = canvas;
    this.gl = gl;
    this.scene = scene;
    this.writePalette();
    this.program = compileProgram(gl, VERTEX, FRAGMENT);
    this.uniforms = Object.fromEntries(UNIFORM_NAMES.map((name) => [name, gl.getUniformLocation(this.program, name)]));
    this.vao = gl.createVertexArray();
  }

  /** Fill the palette and base tone from this preset's authored colours. */
  private writePalette() {
    const colours = this.scene.fallback.map(hexToRgb);

    for (let index = 0; index < PALETTE_SIZE; index += 1) {
      const colour = colours[index % colours.length];
      for (let channel = 0; channel < 3; channel += 1) {
        this.palette[index * 3 + channel] = colour[channel];
      }
    }

    for (let channel = 0; channel < 3; channel += 1) {
      this.base[channel] = (this.palette[channel] * 0.5 + this.palette[3 + channel] * 0.3 + this.palette[6 + channel] * 0.2) * this.scene.tone.floor * 5;
    }
  }

  /** Match the drawing buffer to the element size at `scale` device pixels per CSS pixel. */
  resize(cssWidth: number, cssHeight: number, scale: number) {
    const width = Math.max(1, Math.round(cssWidth * scale));
    const height = Math.max(1, Math.round(cssHeight * scale));

    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
  }

  render(state: SoundscapeState) {
    const { gl, scene, uniforms: u } = this;
    const width = this.canvas.width;
    const height = this.canvas.height;
    gl.viewport(0, 0, width, height);
    gl.useProgram(this.program);
    gl.bindVertexArray(this.vao);
    gl.uniform3fv(u.uPal, this.palette);
    gl.uniform3fv(u.uBase, this.base);
    gl.uniform1f(u.uAspect, width / height);
    gl.uniform1f(u.uTime, state.time);
    gl.uniform1f(u.uFlow, state.flow);
    gl.uniform4f(u.uBands, state.sub, state.bass, state.mid, state.high);
    gl.uniform4f(u.uPulse, state.beat, state.downbeat, state.lift, state.anticipation);
    gl.uniform1f(u.uIntensity, state.intensity);
    gl.uniform1f(u.uGlitch, state.glitch);
    gl.uniform3f(u.uTone, scene.tone.floor * 0.25, scene.tone.ceiling, scene.tone.contrast);
    gl.uniform4f(u.uShape, scene.zoom, scene.warp, scene.drift, scene.grain);
    gl.uniform4f(u.uFx, scene.caustics, scene.iridescence, scene.smear, scene.bulge);
    gl.uniform1f(u.uGlitchAmount, scene.glitch);
    gl.uniform4fv(u.uRing, state.ring);
    gl.uniform4fv(u.uBurst, state.bursts);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindVertexArray(null);
  }

  dispose() {
    const { gl } = this;
    gl.deleteVertexArray(this.vao);
    gl.deleteProgram(this.program);
  }
}
