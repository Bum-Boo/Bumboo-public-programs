"""Small read-only adapters. Neither prompts nor session transcripts are collected."""

import json
import re
import time
from pathlib import Path

from .config import atomic_json
from .models import Task, clean_text, now_iso, timestamp

MAX_BYTES = 262144
MAX_RECORDS = 512


def read_object(path: Path) -> dict:
    with path.open("rb") as stream:
        payload = stream.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("record_too_large")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("record_not_object")
    return value


def from_agent_task(path: Path, now: float) -> Task:
    raw = read_object(path)
    if raw.get("schema") != 1:
        raise ValueError("unsupported_schema")
    updated = timestamp(raw.get("updated_at"))
    status = raw.get("status")
    owner = raw.get("owner") or {}
    checkpoint = raw.get("checkpoint") or {}
    if not isinstance(owner, dict) or not isinstance(checkpoint, dict):
        raise ValueError("malformed_owner_or_checkpoint")
    if status == "active":
        state = "working" if timestamp(owner.get("expires_at")) > now else "attention"
        detail = (
            "유효한 담당 기록이 있어요. 실제 프로세스 실행 여부는 별도예요."
            if state == "working"
            else "담당 기록의 유효 시간이 지났어요. 진행 여부를 확인해 주세요."
        )
    elif status in ("complete", "completed"):
        state, detail = "done", "완료로 기록된 작업이에요."
    elif status in ("released", "blocked"):
        state, detail = "attention", "다음 담당자 또는 확인을 기다리는 기록이에요."
    else:
        raise ValueError("unknown_task_status")
    outputs = checkpoint.get("outputs", [])
    if not isinstance(outputs, list):
        outputs = []
    title = clean_text(raw.get("title")) or clean_text(raw.get("task")) or "이름 없는 작업"
    if title == raw.get("task"):
        title = (
            clean_text(checkpoint.get("summary"), 120) or clean_text(raw.get("scope"), 120) or title
        )
    project = clean_text(raw.get("project"), 64)
    return Task(
        f"task:{project}/{clean_text(raw.get('task'), 64)}",
        title,
        clean_text(owner.get("agent"), 32) or "agent",
        state,
        updated,
        "agent-task",
        clean_text(checkpoint.get("summary"), 400) or detail,
        str(path.parent / "Handoff.md"),
        tuple(x for x in outputs[:8] if isinstance(x, str) and len(x) < 4096),
        str(raw.get("revision", "")),
    )


def from_event(path: Path, now: float) -> Task:
    raw = read_object(path)
    if raw.get("schema") != 1:
        raise ValueError("unsupported_schema")
    state = raw.get("state")
    if state not in ("idle", "working", "done", "attention", "error"):
        raise ValueError("unknown_event_state")
    updated = timestamp(raw.get("updated_at"))
    ttl = raw.get("ttl", 300)
    if not isinstance(ttl, int) or not 10 <= ttl <= 86400:
        raise ValueError("invalid_ttl")
    if state == "working" and now - updated > ttl:
        state = "attention"
    artifact = raw.get("artifact")
    return Task(
        "event:" + path.stem,
        clean_text(raw.get("title")) or path.stem,
        clean_text(raw.get("agent"), 32) or "agent",
        state,
        updated,
        "event",
        clean_text(raw.get("detail"), 400),
        clean_text(raw.get("handoff"), 4096),
        (artifact,) if isinstance(artifact, str) and len(artifact) < 4096 else (),
        str(raw.get("updated_at")),
    )


def collect(task_root: str, event_root: Path, now: float | None = None):
    now = time.time() if now is None else now
    tasks, errors = [], []
    sources = [(event_root, "*.json", from_event)]
    if task_root:
        sources.append((Path(task_root).expanduser(), "*/*/state.json", from_agent_task))
    for root, pattern, parser in sources:
        if not root.is_dir():
            if parser == from_agent_task:
                errors.append("task_source_unavailable")
            continue
        try:
            paths = list(root.glob(pattern))
            paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            if len(paths) > MAX_RECORDS:
                errors.append("record_limit_reached")
            for path in paths[:MAX_RECORDS]:
                try:
                    task = parser(path, now)
                    if now - task.updated < 14 * 86400 or task.state == "working":
                        tasks.append(task)
                except (ValueError, OSError, TypeError, KeyError):
                    errors.append("unreadable_record")
        except OSError:
            errors.append("source_unavailable")
    tasks.sort(key=lambda t: t.updated, reverse=True)
    return tasks, errors


def write_event(
    root: Path,
    *,
    event_id: str,
    state: str,
    title: str,
    agent="agent",
    detail="",
    artifact="",
    handoff="",
    ttl=300,
) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}", event_id):
        raise ValueError("id must contain 1–96 letters, digits, dots, underscores or hyphens")
    if state not in ("idle", "working", "done", "attention", "error"):
        raise ValueError("Invalid state")
    if not 10 <= ttl <= 86400:
        raise ValueError("ttl must be 10–86400 seconds")
    value = {
        "schema": 1,
        "state": state,
        "title": clean_text(title),
        "agent": clean_text(agent, 32),
        "detail": clean_text(detail, 400),
        "artifact": str(Path(artifact).expanduser().absolute()) if artifact else "",
        "handoff": str(Path(handoff).expanduser().absolute()) if handoff else "",
        "ttl": ttl,
        "updated_at": now_iso(),
    }
    target = root / (event_id + ".json")
    atomic_json(target, value)
    return target
