import { RULES } from "@/src/ca/rules";
import type { GridBuffer, RuleId } from "@/src/ca/types";

export type EncodedState = {
  version: 1;
  width: number;
  height: number;
  rule: RuleId;
  generation: number;
  cells: string;
};

export function encodeState(grid: GridBuffer, rule: RuleId, generation: number) {
  const state: EncodedState = {
    version: 1,
    width: grid.width,
    height: grid.height,
    rule,
    generation,
    cells: runLengthEncode(grid.cells)
  };

  return base64UrlEncode(JSON.stringify(state));
}

export function decodeState(hash: string): EncodedState | null {
  const value = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!value.startsWith("state=")) {
    return null;
  }

  try {
    const parsed = JSON.parse(base64UrlDecode(value.slice("state=".length))) as Partial<EncodedState>;
    if (
      parsed.version !== 1 ||
      !isPositiveInteger(parsed.width) ||
      !isPositiveInteger(parsed.height) ||
      typeof parsed.rule !== "string" ||
      !Object.hasOwn(RULES, parsed.rule) ||
      !Number.isSafeInteger(parsed.generation) ||
      (parsed.generation as number) < 0 ||
      typeof parsed.cells !== "string"
    ) {
      return null;
    }

    return parsed as EncodedState;
  } catch {
    return null;
  }
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) > 0;
}

export function restoreCells(encoded: EncodedState, target: GridBuffer) {
  const decoded = runLengthDecode(encoded.cells, target.cells.length);
  target.cells.set(decoded.subarray(0, target.cells.length));
}

export function exportStateJson(grid: GridBuffer, rule: RuleId, generation: number) {
  return JSON.stringify(
    {
      version: 1,
      width: grid.width,
      height: grid.height,
      rule,
      generation,
      cells: Array.from(grid.cells)
    },
    null,
    2
  );
}

function runLengthEncode(cells: Uint8Array) {
  const chunks: string[] = [];
  let index = 0;

  while (index < cells.length) {
    const value = cells[index];
    let length = 1;
    while (index + length < cells.length && cells[index + length] === value && length < 9999) {
      length += 1;
    }

    chunks.push(`${value.toString(36)}.${length.toString(36)}`);
    index += length;
  }

  return chunks.join(",");
}

function runLengthDecode(value: string, expectedLength: number) {
  const cells = new Uint8Array(expectedLength);
  let offset = 0;

  for (const chunk of value.split(",")) {
    const [stateRaw, lengthRaw] = chunk.split(".");
    const state = Number.parseInt(stateRaw ?? "0", 36);
    const length = Number.parseInt(lengthRaw ?? "0", 36);

    if (!Number.isFinite(state) || !Number.isFinite(length) || length <= 0) {
      continue;
    }

    cells.fill(state, offset, Math.min(expectedLength, offset + length));
    offset += length;
    if (offset >= expectedLength) {
      break;
    }
  }

  return cells;
}

function base64UrlEncode(value: string) {
  return btoa(unescape(encodeURIComponent(value))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

function base64UrlDecode(value: string) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return decodeURIComponent(escape(atob(padded)));
}
