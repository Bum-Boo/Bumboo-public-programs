/**
 * Elapsed-time bookkeeping for the demo loop; times are `performance.now()` milliseconds.
 * Pausing freezes elapsed time and resuming continues from the same position.
 */
export class PlaybackClock {
  /** Elapsed seconds banked before the current play segment. */
  private banked = 0;
  private segmentStart: number;
  private playingState = true;

  constructor(now: number) {
    this.segmentStart = now;
  }

  get playing() {
    return this.playingState;
  }

  /** Seconds of motion since the last restart, excluding paused time. */
  elapsed(now: number) {
    if (!this.playingState) return this.banked;
    return this.banked + Math.max(0, (now - this.segmentStart) / 1000);
  }

  pause(now: number) {
    if (!this.playingState) return;
    this.banked = this.elapsed(now);
    this.playingState = false;
  }

  resume(now: number) {
    if (this.playingState) return;
    this.segmentStart = now;
    this.playingState = true;
  }

  /** Start again from zero, keeping the current play/pause state. */
  restart(now: number) {
    this.banked = 0;
    this.segmentStart = now;
  }
}
