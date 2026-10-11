import { discoverTypecastJob } from "./jobDiscovery.js";
import type { JobValidationResult } from "./types.js";

export function validateJobFolder(path: string): JobValidationResult {
  const job = discoverTypecastJob(path);

  return {
    valid: job.errors.length === 0,
    folderPath: job.folderPath,
    files: job.files,
    audioFile: job.audioFile,
    captionFile: job.captionFile,
    captionSource: job.captionSource,
    cueCount: job.cues.length,
    errors: job.errors,
    warnings: job.warnings
  };
}
