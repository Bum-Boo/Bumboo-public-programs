import type { CaptionCue } from "../../../packages/typecast-sync-core/src/index.js";
import { formatSrt } from "../../../packages/typecast-sync-core/src/index.js";

type UxpFolder = {
  createFile(name: string, options: { overwrite: boolean }): Promise<UxpFile>;
};

type UxpFile = {
  write(contents: string, options?: unknown): Promise<void>;
};

export async function writeFallbackSrt(folder: UxpFolder, cues: CaptionCue[], writeOptions?: unknown): Promise<UxpFile> {
  const srtFile = await folder.createFile("typecast_sync_fallback.srt", { overwrite: true });
  await srtFile.write(formatSrt(cues), writeOptions);
  return srtFile;
}

export function getCaptionCreationLimitation(): string {
  return [
    "Premiere Pro UXP currently documents caption track inspection, but not a stable cue creation API.",
    "The MVP therefore generates a standards-compatible SRT fallback and imports it into the project when possible."
  ].join(" ");
}
