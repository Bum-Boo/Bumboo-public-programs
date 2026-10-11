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

  for (let index = 0; index < words.length; index += 1) {
    const word = words[index];
    const next = current ? `${current} ${word}` : word;

    if (next.length <= maxCharsPerLine || current.length === 0) {
      current = next;
      continue;
    }

    lines.push(current);
    current = word;

    if (lines.length === maxLines - 1) {
      const remaining = [current, ...words.slice(index + 1)].join(" ");
      lines.push(remaining);
      return lines.join("\n");
    }
  }

  if (current) {
    lines.push(current);
  }

  return lines.slice(0, maxLines).join("\n");
}
