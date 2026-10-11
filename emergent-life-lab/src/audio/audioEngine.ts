import type { MetricsSnapshot } from "@/src/ca/types";

export class EmergentAudioEngine {
  private context: AudioContext | null = null;
  private master: GainNode | null = null;
  private drone: OscillatorNode | null = null;
  private droneGain: GainNode | null = null;
  private filter: BiquadFilterNode | null = null;
  private panner: StereoPannerNode | null = null;
  private enabled = false;
  private lastBirths = 0;
  private lastDeaths = 0;

  async setEnabled(enabled: boolean) {
    this.enabled = enabled;

    if (enabled) {
      await this.ensureStarted();
      this.master?.gain.setTargetAtTime(0.16, this.context?.currentTime ?? 0, 0.08);
    } else if (this.context && this.master) {
      this.master.gain.setTargetAtTime(0, this.context.currentTime, 0.08);
    }
  }

  update(metrics: MetricsSnapshot, width: number, height: number) {
    if (!this.enabled || !this.context || !this.master || !this.droneGain || !this.filter || !this.panner) {
      return;
    }

    const now = this.context.currentTime;
    const density = Math.min(1, metrics.population / Math.max(1, width * height));
    const entropyNorm = Math.min(1, metrics.entropy / 2);
    const pan = Math.max(-1, Math.min(1, (metrics.centerX / Math.max(1, width - 1)) * 2 - 1));

    this.droneGain.gain.setTargetAtTime(0.018 + density * 0.16, now, 0.12);
    this.filter.frequency.setTargetAtTime(240 + entropyNorm * 2100, now, 0.12);
    this.panner.pan.setTargetAtTime(pan, now, 0.1);

    if (metrics.births > 0 && metrics.births !== this.lastBirths) {
      this.triggerPluck(Math.min(1, metrics.births / 180), 220 + Math.min(9, metrics.clusterCount) * 34);
    }

    if (metrics.deaths > 0 && metrics.deaths !== this.lastDeaths) {
      this.triggerClick(Math.min(1, metrics.deaths / 220));
    }

    this.lastBirths = metrics.births;
    this.lastDeaths = metrics.deaths;
  }

  dispose() {
    this.drone?.stop();
    this.context?.close().catch(() => undefined);
    this.context = null;
    this.master = null;
    this.drone = null;
    this.droneGain = null;
    this.filter = null;
    this.panner = null;
  }

  private async ensureStarted() {
    if (!this.context) {
      const context = new AudioContext();
      const master = context.createGain();
      const drone = context.createOscillator();
      const droneGain = context.createGain();
      const filter = context.createBiquadFilter();
      const panner = context.createStereoPanner();

      drone.type = "sine";
      drone.frequency.value = 82;
      droneGain.gain.value = 0;
      filter.type = "lowpass";
      filter.frequency.value = 420;
      master.gain.value = 0;

      drone.connect(droneGain);
      droneGain.connect(filter);
      filter.connect(panner);
      panner.connect(master);
      master.connect(context.destination);
      drone.start();

      this.context = context;
      this.master = master;
      this.drone = drone;
      this.droneGain = droneGain;
      this.filter = filter;
      this.panner = panner;
    }

    if (this.context.state !== "running") {
      await this.context.resume();
    }
  }

  private triggerPluck(amount: number, frequency: number) {
    if (!this.context || !this.master) {
      return;
    }

    const now = this.context.currentTime;
    const oscillator = this.context.createOscillator();
    const gain = this.context.createGain();

    oscillator.type = "triangle";
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.012 + amount * 0.045, now + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.18);

    oscillator.connect(gain);
    gain.connect(this.master);
    oscillator.start(now);
    oscillator.stop(now + 0.22);
  }

  private triggerClick(amount: number) {
    if (!this.context || !this.master) {
      return;
    }

    const now = this.context.currentTime;
    const buffer = this.context.createBuffer(1, Math.floor(this.context.sampleRate * 0.045), this.context.sampleRate);
    const data = buffer.getChannelData(0);

    for (let index = 0; index < data.length; index += 1) {
      data[index] = (Math.random() * 2 - 1) * (1 - index / data.length);
    }

    const source = this.context.createBufferSource();
    const gain = this.context.createGain();
    const filter = this.context.createBiquadFilter();

    filter.type = "lowpass";
    filter.frequency.value = 280;
    gain.gain.value = 0.012 + amount * 0.035;
    source.buffer = buffer;
    source.connect(filter);
    filter.connect(gain);
    gain.connect(this.master);
    source.start(now);
  }
}
