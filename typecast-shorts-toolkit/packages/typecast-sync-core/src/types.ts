export interface CaptionWord {
  text: string;
  startSeconds: number;
  endSeconds: number;
}

export interface CaptionCue {
  id: number;
  startSeconds: number;
  endSeconds: number;
  text: string;
  words?: CaptionWord[];
}

export type CaptionSource = "typecast-json" | "srt" | "vtt" | "script" | "none";

export interface TypecastJobFiles {
  audioFile?: string;
  srtFile?: string;
  vttFile?: string;
  scriptFile?: string;
  typecastJsonFile?: string;
}

export interface TypecastJob {
  folderPath: string;
  files: TypecastJobFiles;
  audioFile?: string;
  captionFile?: string;
  captionSource: CaptionSource;
  cues: CaptionCue[];
  errors: string[];
  warnings: string[];
}

export interface JobValidationResult {
  valid: boolean;
  folderPath: string;
  files: TypecastJobFiles;
  audioFile?: string;
  captionFile?: string;
  captionSource: CaptionSource;
  cueCount: number;
  errors: string[];
  warnings: string[];
}
