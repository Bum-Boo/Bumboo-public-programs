import { secondsToSrtTimestamp } from "./timecode.js";
import type { CaptionCue } from "./types.js";

export function formatSrt(cues: CaptionCue[]): string {
  return cues
    .map((cue, index) => {
      const text = cue.text.trim();
      return [
        String(index + 1),
        `${secondsToSrtTimestamp(cue.startSeconds)} --> ${secondsToSrtTimestamp(cue.endSeconds)}`,
        text
      ].join("\n");
    })
    .join("\n\n")
    .concat(cues.length > 0 ? "\n" : "");
}
