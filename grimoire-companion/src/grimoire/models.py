"""Source-independent, factual states; leases are never process-liveness claims."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

STATES = {"idle", "working", "done", "attention", "error", "sleep"}
LABELS = {
    "idle": "다음 여정을 기다려요",
    "working": "작업 기록을 살펴보고 있어요",
    "done": "새로운 결과가 도착했어요",
    "attention": "확인이 필요한 기록이 있어요",
    "error": "작업에서 문제가 보고됐어요",
    "sleep": "잠시 쉬고 있어요",
}
SHORT = {
    "idle": "대기",
    "working": "진행 기록",
    "done": "완료 기록",
    "attention": "확인 필요",
    "error": "오류",
    "sleep": "휴식",
}


def timestamp(value) -> float:
    if not isinstance(value, str):
        raise ValueError("Expected timestamp")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp needs timezone")
    return dt.timestamp()


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def clean_text(value, limit=200) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\x00", "").split())[:limit]


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    agent: str
    state: str
    updated: float
    source: str
    detail: str = ""
    handoff: str = ""
    artifacts: tuple[str, ...] = ()
    revision: str = ""


def aggregate(tasks: list[Task]) -> str:
    for state in ("error", "working", "attention"):
        if any(t.state == state for t in tasks):
            return state
    return "idle"


SAFE_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".jsonl",
    ".csv",
    ".log",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
    ".odt",
    ".docx",
    ".pptx",
    ".xlsx",
}


def openable_path(value: str) -> Path | None:
    try:
        p = Path(value).expanduser().resolve(strict=True)
        if p.is_dir() or (p.is_file() and p.suffix.lower() in SAFE_EXTENSIONS):
            return p
    except (OSError, ValueError, RuntimeError):
        pass
    return None
