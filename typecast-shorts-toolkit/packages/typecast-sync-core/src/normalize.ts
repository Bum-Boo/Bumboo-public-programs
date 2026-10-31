export function normalizeWhitespace(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export function splitLongCue(
  text: string,
  maxCharsPerLine = 34,
  maxLines = 2
): string {
  const normalized = normalizeWhitespace(text);

  if (!normalized) {
    return "";
  }

  if (maxCharsPerLine <= 0 || maxLines <= 0) {
    return normalized;
  }

  const words = normalized.split(" ");
  const lines: string[] = [];
  let current = "";

  for (const word of words) {
    const next = current ? `${current} ${word}` : word;

    // The last allowed line takes all remaining words, so no text is dropped.
    if (next.length <= maxCharsPerLine || current.length === 0 || lines.length === maxLines - 1) {
      current = next;
      continue;
    }

    lines.push(current);
    current = word;
  }

  if (current) {
    lines.push(current);
  }

  return lines.join("\n");
}
