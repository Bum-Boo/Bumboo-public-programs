from __future__ import annotations

import re

_PRIORITY_KEYWORDS = (
    "결론",
    "완료",
    "주의",
    "다음",
    "원칙",
    "성공",
    "실패",
    "오류",
    "승인",
)

_STATUS_RULES = (
    ("error", ("오류", "실패", "에러", "error", "failed", "traceback")),
    ("needs_approval", ("승인", "확인 필요", "허가", "permission", "approval")),
    ("completed", ("완료", "끝났", "성공", "통과", "done", "completed", "passed")),
    ("working", ("진행", "확인 중", "작업 중", "보고 있어", "running", "working")),
)


def _strip_markdown_noise(text: str) -> list[str]:
    """Return readable non-empty lines with fenced code and headings removed."""
    lines: list[str] = []
    in_fence = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line:
            continue
        if line.startswith("#"):
            continue
        if re.fullmatch(r"[-*_]{3,}", line):
            continue
        # Remove common markdown list prefix but keep the sentence.
        line = re.sub(r"^[-*+]\s+", "", line)
        lines.append(line)
    return lines


def _clip(text: str, max_chars: int) -> str:
    if max_chars <= 1:
        return "…" if text else ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def extract_snippet(text: str, max_chars: int = 120) -> str:
    """Extract a deterministic display snippet from an existing answer.

    This deliberately does not summarize. It only selects and clips an existing
    line so the pet never needs a model call.
    """
    lines = _strip_markdown_noise(text)
    if not lines:
        return "결과가 도착했어."

    for keyword in _PRIORITY_KEYWORDS:
        for line in lines:
            if keyword in line:
                return _clip(line, max_chars)

    compact = " ".join(lines)
    compact = re.sub(r"\s+", " ", compact).strip()
    return _clip(compact, max_chars)


def classify_status(text: str) -> str:
    """Map existing text to a local display status without model calls."""
    haystack = (text or "").lower()
    for status, keywords in _STATUS_RULES:
        if any(keyword.lower() in haystack for keyword in keywords):
            return status
    return "idle" if not haystack.strip() else "working"
