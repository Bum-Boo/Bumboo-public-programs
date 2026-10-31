const TIMESTAMP_PATTERN =
  /^(?:(\d+):)?(\d{1,2}):(\d{2})([,.](\d{1,3}))?$/;

export function timestampToSeconds(value: string): number {
  const match = value.trim().match(TIMESTAMP_PATTERN);

  if (!match) {
    throw new Error(`Invalid timestamp: ${value}`);
  }

  const hours = Number(match[1] ?? 0);
  const minutes = Number(match[2]);
  const seconds = Number(match[3]);
  const milliseconds = Number((match[5] ?? "0").padEnd(3, "0"));

  return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000;
}

export function secondsToTimecode(seconds: number, fps = 30): string {
  const safeSeconds = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  const safeFps = Math.max(1, Math.round(fps));
  const totalFrames = Math.round(safeSeconds * safeFps);

  const frames = totalFrames % safeFps;
  const totalWholeSeconds = Math.floor(totalFrames / safeFps);
  const wholeSeconds = totalWholeSeconds % 60;
  const minutes = Math.floor(totalWholeSeconds / 60) % 60;
  const hours = Math.floor(totalWholeSeconds / 3600);

  return [
    pad(hours, 2),
    pad(minutes, 2),
    pad(wholeSeconds, 2),
    pad(frames, 2)
  ].join(":");
}

export function secondsToSrtTimestamp(seconds: number): string {
  const safeSeconds = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  const totalMilliseconds = Math.round(safeSeconds * 1000);
  const milliseconds = totalMilliseconds % 1000;
  const totalWholeSeconds = Math.floor(totalMilliseconds / 1000);
  const wholeSeconds = totalWholeSeconds % 60;
  const minutes = Math.floor(totalWholeSeconds / 60) % 60;
  const hours = Math.floor(totalWholeSeconds / 3600);

  return `${pad(hours, 2)}:${pad(minutes, 2)}:${pad(wholeSeconds, 2)},${pad(milliseconds, 3)}`;
}

function pad(value: number, size: number): string {
  return String(value).padStart(size, "0");
}
