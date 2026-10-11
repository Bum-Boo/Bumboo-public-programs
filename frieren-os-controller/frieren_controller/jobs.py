"""Owner-account job files; commands are stored, never executed by the editor."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

from .core import ControllerError, protected, validate_unit

LIMIT = 24000
JOB_PROTECTED = {"dbus.service", "dbus-broker.service", "wireplumber.service"}
JOB_PROTECTED_PREFIXES = (
    "pipewire",
    "xdg-desktop-portal",
    "plasma-kwin",
    "plasma-plasmashell",
    "plasma-ksmserver",
)


def job_protected(unit):
    return protected("user", unit) or unit in JOB_PROTECTED or unit.startswith(JOB_PROTECTED_PREFIXES)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def text(value: str) -> str:
    if not isinstance(value, str) or len(value.encode()) > LIMIT or "\x00" in value or "\r" in value:
        raise ControllerError("내용은 24KB 이내여야 하고 제어 문자는 넣을 수 없어요.")
    return value.rstrip("\n") + "\n" if value else ""


class JobEditor:
    def __init__(self, controller, unit_dir=None, crontab=None):
        self.c = controller
        config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.unit_dir = Path(unit_dir or config / "systemd/user")
        self.crontab = Path(crontab or "/usr/bin/crontab")

    def _path(self, unit, mode):
        validate_unit(unit)
        if not unit[0].isalnum():
            raise ControllerError("이름은 영문이나 숫자로 시작해 주세요.")
        if job_protected(unit):
            raise ControllerError("이 서비스는 보호돼 있어요. 내용을 바꿀 수 없어요.")
        path = self.unit_dir / unit
        if mode == "override":
            path = self.unit_dir / (unit + ".d") / "90-frieren-controller.conf"
        # Never follow a unit mask, alias, or a symlinked configuration directory.
        for part in (path, *path.parents):
            if part.is_symlink():
                raise ControllerError(
                    "설정 폴더나 파일이 심볼릭 링크예요. 연결된 설정과 차단된 서비스는 편집하지 않아요."
                )
        if path.exists() and not path.is_file():
            raise ControllerError("설정 위치에 일반 파일이 아닌 항목이 있어요.")
        return path

    def _cron(self, *args, allow_failure=False):
        return self.c._run(
            [str(self.crontab), *args],
            allow_failure=allow_failure,
            env={**os.environ, "LC_ALL": "C", "NO_COLOR": "1"},
        )

    def unit_read(self, unit):
        main = self._path(unit, "file")
        state = self.c._systemctl(
            "user", "show", "--property=LoadState,FragmentPath,DropInPaths,ActiveState", "--", unit
        ).stdout
        properties = dict(line.split("=", 1) for line in state.splitlines() if "=" in line)
        if properties.get("LoadState") == "masked":
            raise ControllerError("차단된 서비스는 편집할 수 없어요.")
        exists = properties.get("LoadState") != "not-found"
        if exists and not properties.get("FragmentPath"):
            raise ControllerError("임시 서비스는 파일로 편집할 수 없어요.")
        mode = "file" if main.exists() or not exists else "override"
        path = self._path(unit, mode)
        content = path.read_text() if path.exists() else ""
        if len(content.encode()) > LIMIT:
            raise ControllerError("이 설정은 편집 가능한 크기를 넘어요.")
        # Ask the manager for exact source files. '# /...' is an ordinary comment,
        # not a reliable boundary when reading systemctl cat output.
        files = []
        paths = [properties["FragmentPath"]] if exists else []
        paths.extend(properties.get("DropInPaths", "").split())
        for filename in paths:
            filename = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m[1], 16)), filename)
            source = Path(filename)
            if not source.is_file() or source.stat().st_size > LIMIT:
                raise ControllerError("원본 설정 파일을 읽지 못했어요. 파일 위치와 크기를 확인해 주세요.")
            files.append({"path": filename, "content": source.read_text()})
        reference = "\n".join("# " + f["path"] + "\n" + f["content"] for f in files)
        base = "\n".join(f["content"] for f in files if f["path"] != str(path))
        revision = digest(str(path) + "\n" + str(path.exists()) + content + "\n" + reference)
        return {
            "unit": unit,
            "mode": mode,
            "exists": exists,
            "content": content,
            "reference": reference,
            "base": base,
            "revision": revision,
            "active": properties.get("ActiveState", "inactive"),
            "files": files,
        }

    def _write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _verify_unit(self, unit, before, content):
        # Explicit file verification still loads installed drop-ins. Mirror those
        # in the candidate directory so an old ExecStart cannot hide a bad edit.
        with tempfile.TemporaryDirectory() as directory:
            check = Path(directory) / unit
            check.write_text(content if before["mode"] == "file" else before["files"][0]["content"])
            dropins = Path(directory) / (unit + ".d")
            for file in before["files"][1:]:
                source = Path(file["path"])
                if source.suffix == ".conf":
                    dropins.mkdir(exist_ok=True)
                    (dropins / source.name).write_text(file["content"])
            if before["mode"] == "override":
                dropins.mkdir(exist_ok=True)
                (dropins / "90-frieren-controller.conf").write_text(content)
            self.c._run(["/usr/bin/systemd-analyze", "--user", "verify", "--man=no", str(check)])

    def unit_save(self, unit, content, revision):
        content = text(content)
        if not content.strip():
            raise ControllerError("서비스나 타이머 내용을 입력해 주세요.")
        with self.c.lock:
            before = self.unit_read(unit)
            if before["revision"] != revision:
                raise ControllerError("다른 곳에서 설정을 바꿨어요. 초안을 복사한 뒤 다시 열어 주세요.")
            path = self._path(unit, before["mode"])
            candidate = before["base"] + "\n" + content if before["mode"] == "override" else content
            required = "[Service]" if unit.endswith(".service") else "[Timer]"
            if required not in candidate:
                raise ControllerError(f"{required} 항목이 필요해요.")
            if unit.endswith(".timer") and not before["exists"]:
                target = unit.removesuffix(".timer") + ".service"
                section = ""
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith(("#", ";")):
                        continue
                    if line.startswith("["):
                        section = line
                    elif section == "[Timer]" and "=" in line:
                        key, value = line.split("=", 1)
                        if key.strip() == "Unit" and value.strip():
                            target = value.strip().strip('"')
                validate_unit(target)
                if not target.endswith(".service"):
                    raise ControllerError("새 타이머가 실행할 .service를 지정해 주세요.")
                loaded = self.c._systemctl("user", "show", "--property=LoadState", "--", target).stdout
                if "LoadState=loaded" not in loaded.splitlines():
                    raise ControllerError("타이머가 실행할 서비스를 먼저 만들어 주세요: " + target)
            self._verify_unit(unit, before, content)
            if self.unit_read(unit)["revision"] != revision:
                raise ControllerError("검사 중 설정이 바뀌었어요. 초안을 복사한 뒤 다시 열어 주세요.")
            old = path.read_text() if path.exists() else None
            backup = self.c.state_dir / ("job-" + unit + ".json")
            self.c._atomic_json(
                backup, {"unit": unit, "mode": before["mode"], "before": old, "after": digest(content)}
            )
            try:
                self._write(path, content)
                self.c._systemctl("user", "daemon-reload")
                if path.read_text() != content:
                    raise ControllerError("저장한 내용을 다시 확인하지 못했어요.")
            except Exception as exc:
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    self._write(path, old)
                self.c._systemctl("user", "daemon-reload", allow_failure=True)
                raise ControllerError("저장에 실패해 이전 파일로 돌아갔어요. " + str(exc)) from exc
            self.c._unit_cache.clear()
            self.c._audit("job_unit_save", unit=unit, mode=before["mode"])
            result = self.unit_read(unit)
            result["saved"] = True
            return result

    def cron_read(self):
        if not self.crontab.is_file():
            return {
                "available": False,
                "content": "",
                "revision": None,
                "message": "cronie를 설치하면 내 계정의 cron 작업을 편집해요. 지금은 타이머를 추가해 주세요.",
            }
        result = self._cron("-l", allow_failure=True)
        absent = result.returncode == 1 and "no crontab for" in result.stderr.lower()
        if result.returncode and not absent:
            raise ControllerError("cron 목록을 읽지 못했어요. " + result.stderr[:400])
        content = "" if absent else result.stdout
        if len(content.encode()) > LIMIT:
            raise ControllerError("crontab이 편집 가능한 크기를 넘어요.")
        active = self.c._systemctl("system", "is-active", "cronie.service", allow_failure=True)
        return {
            "available": True,
            "content": content,
            "revision": digest(str(absent) + content),
            "absent": absent,
            "running": active.returncode == 0,
            "message": ""
            if active.returncode == 0
            else "cron 서비스가 꺼져 있어요. 서비스 화면에서 cronie를 켜 주세요.",
        }

    def cron_save(self, content, revision):
        content = text(content)
        with self.c.lock:
            before = self.cron_read()
            if not before["available"]:
                raise ControllerError(before["message"])
            if before["revision"] != revision:
                raise ControllerError("다른 곳에서 crontab을 바꿨어요. 초안을 복사한 뒤 다시 열어 주세요.")
            with tempfile.TemporaryDirectory() as directory:
                candidate = Path(directory) / "crontab"
                candidate.write_text(content)
                candidate.chmod(0o600)
                self._cron("-T", str(candidate))
                if self.cron_read()["revision"] != revision:
                    raise ControllerError("검사 중 crontab이 바뀌었어요. 초안을 복사한 뒤 다시 열어 주세요.")
                self.c._atomic_json(
                    self.c.state_dir / "job-crontab.json",
                    {"before": before["content"], "absent": before["absent"], "after": digest(content)},
                )
                try:
                    self._cron(str(candidate))
                    after = self.cron_read()
                    if after["content"] != content:
                        raise ControllerError("저장한 crontab을 다시 확인하지 못했어요.")
                except Exception as exc:
                    try:
                        if before["absent"]:
                            removed = self._cron("-r", allow_failure=True)
                            if removed.returncode and "no crontab for" not in removed.stderr.lower():
                                raise ControllerError(removed.stderr[:400])
                        else:
                            candidate.write_text(before["content"])
                            self._cron(str(candidate))
                    except Exception as rollback:
                        raise ControllerError(
                            "cron 저장과 복구에 실패했어요. job-crontab.json 백업을 확인해 주세요. "
                            + str(rollback)
                        ) from exc
                    raise ControllerError("저장에 실패해 이전 crontab으로 돌아갔어요. " + str(exc)) from exc
            self.c._audit("job_cron_save")
            return after
