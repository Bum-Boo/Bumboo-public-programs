import { normalizeWhitespace } from "./normalize.js";
import type { CaptionCue, CaptionWord } from "./types.js";

const CUE_TEXT_KEYS = ["text", "caption", "content", "line", "sentence", "displayText", "transcript"];
const WORD_TEXT_KEYS = ["word", "text", "value", "token", "char", "character"];
const START_KEYS = ["startSeconds", "start_seconds", "start", "startTime", "start_time", "from", "begin", "beginTime", "offset"];
const END_KEYS = ["endSeconds", "end_seconds", "end", "endTime", "end_time", "to", "finish", "finishTime"];
const DURATION_KEYS = ["durationSeconds", "duration_seconds", "duration", "length"];

export function parseTypecastJson(input: unknown): CaptionCue[] {
  const root = typeof input === "string" ? JSON.parse(input.replace(/^\uFEFF/, "")) : input;

  if (!root || typeof root !== "object") {
    return [];
  }

  const cueCandidates: CaptionCue[][] = [];
  collectCueArrays(root, cueCandidates);

  const bestCueCandidate = cueCandidates
    .filter((candidate) => candidate.length > 0)
    .sort((a, b) => b.length - a.length)[0];

  if (bestCueCandidate) {
    return finalizeCues(bestCueCandidate);
  }

  const wordCandidates: CaptionWord[][] = [];
  collectWordArrays(root, wordCandidates);

  const bestWordCandidate = wordCandidates
    .filter((candidate) => candidate.length > 0)
    .sort((a, b) => b.length - a.length)[0];

  if (!bestWordCandidate) {
    return [];
  }

  return wordsToCues(bestWordCandidate);
}

function collectCueArrays(value: unknown, out: CaptionCue[][]): void {
  if (Array.isArray(value)) {
    const cues = value
      .map((item) => cueFromObject(item))
      .filter((item): item is CaptionCue => Boolean(item));

    if (cues.length > 0 && cues.length / Math.max(1, value.length) >= 0.6) {
      out.push(cues);
    }

    for (const item of value) {
      collectCueArrays(item, out);
    }
    return;
  }

  if (value && typeof value === "object") {
    for (const child of Object.values(value as Record<string, unknown>)) {
      collectCueArrays(child, out);
    }
  }
}

function collectWordArrays(value: unknown, out: CaptionWord[][]): void {
  if (Array.isArray(value)) {
    const words = value
      .map((item) => wordFromObject(item))
      .filter((item): item is CaptionWord => Boolean(item));

    if (words.length > 0 && words.length / Math.max(1, value.length) >= 0.6) {
      out.push(words);
    }

    for (const item of value) {
      collectWordArrays(item, out);
    }
    return;
  }

  if (value && typeof value === "object") {
    for (const child of Object.values(value as Record<string, unknown>)) {
      collectWordArrays(child, out);
    }
  }
}

function cueFromObject(value: unknown): CaptionCue | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const object = value as Record<string, unknown>;
  const text = readText(object, CUE_TEXT_KEYS);
  const startSeconds = readTimeSeconds(object, START_KEYS);
  const endSeconds = readEndSeconds(object, startSeconds);

  if (text === undefined || startSeconds === undefined || endSeconds === undefined || endSeconds < startSeconds) {
    return null;
  }

  const words = Array.isArray(object.words)
    ? object.words.map((word) => wordFromObject(word)).filter((word): word is CaptionWord => Boolean(word))
    : undefined;

  return {
    id: 0,
    startSeconds,
    endSeconds,
    text: normalizeWhitespace(text),
    ...(words && words.length > 0 ? { words } : {})
  };
}

function wordFromObject(value: unknown): CaptionWord | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const object = value as Record<string, unknown>;
  const text = readText(object, WORD_TEXT_KEYS);
  const startSeconds = readTimeSeconds(object, START_KEYS);
  const endSeconds = readEndSeconds(object, startSeconds);

  if (text === undefined || startSeconds === undefined || endSeconds === undefined || endSeconds < startSeconds) {
    return null;
  }

  return {
    text: normalizeWhitespace(text),
    startSeconds,
    endSeconds
  };
}

function readText(object: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = object[key];
    if (typeof value === "string") {
      return value;
    }
    if (typeof value === "number") {
      return String(value);
    }
  }

  return undefined;
}

function readTimeSeconds(object: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const raw = object[key];
    const numeric = numberFromUnknown(raw);

    if (numeric === undefined) {
      continue;
    }

    if (/_ms$/i.test(key) || Math.abs(numeric) > 10000) {
      return numeric / 1000;
    }

    return numeric;
  }

  return undefined;
}

function readEndSeconds(object: Record<string, unknown>, startSeconds: number | undefined): number | undefined {
  const directEnd = readTimeSeconds(object, END_KEYS);

  if (directEnd !== undefined) {
    return directEnd;
  }

  if (startSeconds === undefined) {
    return undefined;
  }

  for (const key of DURATION_KEYS) {
    const duration = numberFromUnknown(object[key]);
    if (duration !== undefined) {
      return startSeconds + duration;
    }
  }

  return undefined;
}

function numberFromUnknown(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  return undefined;
}

function wordsToCues(words: CaptionWord[], maxChars = 42): CaptionCue[] {
  const sortedWords = words.slice().sort((a, b) => a.startSeconds - b.startSeconds);
  const cues: CaptionCue[] = [];
  let current: CaptionWord[] = [];

  for (const word of sortedWords) {
    const previous = current[current.length - 1];
    const gap = previous ? word.startSeconds - previous.endSeconds : 0;
    const projectedText = joinWords([...current, word]);
    const shouldBreakBefore =
      current.length > 0 &&
      (gap > 0.75 || (projectedText.length > maxChars && !isShortCurrentCue(current)));

    if (shouldBreakBefore) {
      cues.push(cueFromWords(cues.length + 1, current));
      current = [];
    }

    current.push(word);

    if (endsSentence(word.text) || joinWords(current).length >= maxChars) {
      cues.push(cueFromWords(cues.length + 1, current));
      current = [];
    }
  }

  if (current.length > 0) {
    cues.push(cueFromWords(cues.length + 1, current));
  }

  return cues;
}

function cueFromWords(id: number, words: CaptionWord[]): CaptionCue {
  return {
    id,
    startSeconds: words[0].startSeconds,
    endSeconds: words[words.length - 1].endSeconds,
    text: joinWords(words),
    words
  };
}

function joinWords(words: CaptionWord[]): string {
  return normalizeWhitespace(
    words.reduce((text, word) => {
      if (!text) {
        return word.text;
      }

      return /^[,.;:!?%)]/.test(word.text) ? `${text}${word.text}` : `${text} ${word.text}`;
    }, "")
  );
}

function isShortCurrentCue(words: CaptionWord[]): boolean {
  return joinWords(words).length < 18;
}

function endsSentence(text: string): boolean {
  return /[.!?]$/.test(text.trim());
}

function finalizeCues(cues: CaptionCue[]): CaptionCue[] {
  return cues
    .slice()
    .sort((a, b) => a.startSeconds - b.startSeconds)
    .map((cue, index) => ({
      ...cue,
      id: index + 1,
      text: normalizeWhitespace(cue.text)
    }));
}
