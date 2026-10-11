import { normalizeWhitespace } from "./normalize.js";
import { timestampToSeconds } from "./timecode.js";
import type { CaptionCue } from "./types.js";

const VTT_TIMING_LINE =
  /^\s*((?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3})\s*-->\s*((?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3})(?:\s+.*)?$/;

export function parseVtt(input: string): CaptionCue[] {
  const lines = input.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").split("\n");
  const cues: CaptionCue[] = [];
  let index = 0;

  if (lines[index]?.trim().startsWith("WEBVTT")) {
    index += 1;
  }

  while (index < lines.length) {
    while (index < lines.length && lines[index].trim() === "") {
      index += 1;
    }

    if (index >= lines.length) {
      break;
    }

    const trimmed = lines[index].trim();
    if (trimmed.startsWith("NOTE") || trimmed === "STYLE" || trimmed === "REGION") {
      index += 1;
      while (index < lines.length && lines[index].trim() !== "") {
        index += 1;
      }
      continue;
    }

    if (!VTT_TIMING_LINE.test(lines[index]) && index + 1 < lines.length && VTT_TIMING_LINE.test(lines[index + 1])) {
      index += 1;
    }

    const timingMatch = lines[index].match(VTT_TIMING_LINE);
    if (!timingMatch) {
      index += 1;
      continue;
    }

    const startSeconds = timestampToSeconds(timingMatch[1]);
    const endSeconds = timestampToSeconds(timingMatch[2]);
    index += 1;

    const textLines: string[] = [];
    while (index < lines.length && lines[index].trim() !== "") {
      textLines.push(lines[index]);
      index += 1;
    }

    cues.push({
      id: cues.length + 1,
      startSeconds,
      endSeconds,
      text: normalizeWhitespace(textLines.join(" "))
    });
  }

  return cues;
}
