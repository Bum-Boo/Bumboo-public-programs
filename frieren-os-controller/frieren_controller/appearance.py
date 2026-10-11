"""User-owned KDE wallpaper and Konsole appearance, with durable original settings."""

from __future__ import annotations

import configparser
import hashlib
import io
import json
import os
import re
import subprocess
import threading
from pathlib import Path

from .core import ControllerError

FILL_MODES = {"crop": 2, "fit": 1, "stretch": 0, "center": 6, "tile": 3}
DEFAULT_TERMINAL = {
    "background": "#1e1e2e",
    "foreground": "#cdd6f4",
    "opacity": 90,
    "image_opacity": 24,
    "image": "",
}
MANAGED = "FrierenController"


def ini(contents=""):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read_string(contents or "")
    except configparser.Error as exc:
        raise ControllerError("터미널 설정을 읽지 못했어요.") from exc
    return parser


def dump_ini(parser):
    buffer = io.StringIO()
    parser.write(buffer, space_around_delimiters=False)
    return buffer.getvalue()


def put(parser, group, key, value):
    if not parser.has_section(group):
        parser.add_section(group)
    parser.set(group, key, str(value))


def bounded(value, name):
    if type(value) is not int or not 0 <= value <= 100:
        raise ControllerError(f"{name}는 0~100 사이 정수로 입력해 주세요.")
    return value


def terminal_settings(settings):
    if not isinstance(settings, dict) or set(settings) != set(DEFAULT_TERMINAL):
        raise ControllerError("터미널 설정 항목을 확인해 주세요.")
    values = dict(settings)
    for key in ("background", "foreground"):
        if not isinstance(values[key], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", values[key]):
            raise ControllerError("색은 #1e1e2e처럼 입력해 주세요.")
        values[key] = values[key].lower()
    for key in ("opacity", "image_opacity"):
        bounded(values[key], "불투명도")
    if not isinstance(values["image"], str):
        raise ControllerError("이미지 경로를 확인해 주세요.")
    return values


def atomic(path, contents):
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
    except OSError as exc:
        raise ControllerError("설정을 저장하지 못했어요. 저장 공간을 확인해 주세요.") from exc


class PlasmaBackend:
    def command(self, args):
        try:
            result = subprocess.run(args, text=True, capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ControllerError("KDE에 연결하지 못했어요. 로그인 상태를 확인해 주세요.") from exc
        if result.returncode:
            raise ControllerError("KDE 설정을 적용하지 못했어요. 다시 확인해 주세요.")
        return result.stdout.strip()

    def script(self, source):
        result = self.command(
            [
                "/usr/bin/qdbus6",
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell.evaluateScript",
                source,
            ]
        )
        try:
            value = json.loads(result)
        except ValueError as exc:
            raise ControllerError("바탕화면 설정을 읽지 못했어요.") from exc
        if isinstance(value, dict) and value.get("error"):
            raise ControllerError(value["error"])
        return value

    def desktops(self):
        return self.script("""
var rows=[], ds=desktops();
for(var i=0;i<ds.length;i++) {
    var d=ds[i]; if(d.screen<0) continue;
    d.currentConfigGroup=["Wallpaper","org.kde.image","General"];
    var keys=d.configKeys, image={};
    for(var j=0;j<keys.length;j++) {
        var k=keys[j];
        if(k==="Image" || k==="FillMode") {
            image[k]=k==="FillMode" ? Number(d.readConfig(k)) : d.readConfig(k);
        }
    }
    rows.push({id:d.id,screen:d.screen,plugin:d.wallpaperPlugin,image:image});
}
print(JSON.stringify({activity:currentActivity(),desktops:rows}));
""")

    def write(self, activity, rows):
        # JSON is embedded as data in a fixed script; clients never supply script code.
        return self.script(
            """
var activity="""
            + json.dumps(activity)
            + """, rows="""
            + json.dumps(rows)
            + """;
var ds=desktops(), targets=[];
if(currentActivity()!==activity) {
    print(JSON.stringify({error:"작업 공간이 바뀌었어요. 다시 선택해 주세요."}));
}
else {
    for(var i=0;i<rows.length;i++) {
        var d=null;
        for(var j=0;j<ds.length;j++) if(ds[j].id===rows[i].id && ds[j].screen===rows[i].screen) d=ds[j];
        if(d===null || d.screen<0) throw new Error("선택한 화면이 바뀌었어요.");
        targets.push(d);
    }
    for(var i=0;i<rows.length;i++) {
        var d=targets[i], row=rows[i];
        d.currentConfigGroup=["Wallpaper","org.kde.image","General"];
        var root=new ConfigFile("plasma-org.kde.plasma.desktop-appletsrc");
        var c=new ConfigFile(root,"Containments"), id=new ConfigFile(c,String(d.id));
        var w=new ConfigFile(id,"Wallpaper"), p=new ConfigFile(w,"org.kde.image");
        var g=new ConfigFile(p,"General");
        var keys=["Image","FillMode"];
        for(var j=0;j<keys.length;j++) {
            var k=keys[j];
            if(Object.prototype.hasOwnProperty.call(row.image,k)) d.writeConfig(k,row.image[k]);
            else g.deleteEntry(k);
        }
        d.wallpaperPlugin=row.plugin;
        d.reloadConfig();
    }
    print(JSON.stringify({ok:true}));
}
"""
        )

    def sessions(self):
        rows = []
        services = self.command(["/usr/bin/qdbus6"]).splitlines()
        for service in services:
            service = service.strip()
            if not re.fullmatch(r"org\.kde\.konsole(?:-\d+)?", service):
                continue
            try:
                paths = self.command(["/usr/bin/qdbus6", service]).splitlines()
            except ControllerError:
                continue
            for path in paths:
                if not re.fullmatch(r"/Sessions/\d+", path):
                    continue
                try:
                    profile = self.command(
                        ["/usr/bin/qdbus6", service, path, "org.kde.konsole.Session.profile"]
                    )
                    identity = self.command(
                        [
                            "/usr/bin/qdbus6",
                            service,
                            path,
                            "org.kde.konsole.Session.shellSessionId",
                        ]
                    )
                except ControllerError:
                    continue
                rows.append({"service": service, "path": path, "identity": identity, "profile": profile})
        return rows


class Appearance:
    def __init__(self, state_dir, backend=None, home=None):
        self.root = Path(state_dir) / "appearance"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.home = Path(home or Path.home())
        self.backend = backend or PlasmaBackend()
        self.lock = threading.RLock()
        self.path = self.root / "state.json"
        try:
            self.state = json.loads(self.path.read_text())
        except FileNotFoundError:
            self.state = {"wallpapers": {}, "terminal": None, "settings": None}
        except (OSError, ValueError) as exc:
            raise ControllerError("배경 복원 기록을 읽지 못했어요. 원본을 확인해 주세요.") from exc
        self.konsolerc = self.home / ".config/konsolerc"
        self.konsole_dir = self.home / ".local/share/konsole"

    def save(self):
        atomic(self.path, json.dumps(self.state, ensure_ascii=False, indent=2) + "\n")

    def import_image(self, value):
        if not isinstance(value, str) or not value or len(value) > 4096 or any(ord(c) < 32 for c in value):
            raise ControllerError("이미지 파일을 선택해 주세요.")
        source = Path(value).expanduser()
        if not source.is_absolute() or not source.is_file():
            raise ControllerError("이미지 파일을 찾지 못했어요. 다시 선택해 주세요.")
        suffix = source.suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
            raise ControllerError("PNG, JPG 또는 WebP 이미지를 선택해 주세요.")
        try:
            with source.open("rb") as stream:
                data = stream.read(32 * 1024 * 1024 + 1)
        except OSError as exc:
            raise ControllerError("이미지를 읽지 못했어요. 다른 파일을 선택해 주세요.") from exc
        if len(data) > 32 * 1024 * 1024:
            raise ControllerError("32MB 이하 이미지를 선택해 주세요.")
        signature = (
            (suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"))
            or (suffix in (".jpg", ".jpeg") and data.startswith(b"\xff\xd8\xff"))
            or (suffix == ".webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP")
        )
        if not signature:
            raise ControllerError("이미지 형식이 맞지 않아요. 다른 파일을 선택해 주세요.")
        images = self.root / "images"
        images.mkdir(mode=0o700, exist_ok=True)
        target = images / (hashlib.sha256(data).hexdigest() + suffix)
        if not target.exists():
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.chmod(0o600)
            try:
                import gi

                gi.require_version("GdkPixbuf", "2.0")
                from gi.repository import GdkPixbuf

                fmt, width, height = GdkPixbuf.Pixbuf.get_file_info(str(temporary))
                if fmt is None or width < 1 or height < 1 or width * height > 64_000_000:
                    raise ValueError("dimensions")
                GdkPixbuf.Pixbuf.new_from_file_at_scale(str(temporary), 1024, 1024, True)
                temporary.replace(target)
            except Exception as exc:
                temporary.unlink(missing_ok=True)
                raise ControllerError("이미지를 열지 못했어요. 다른 파일을 선택해 주세요.") from exc
        return str(target)

    def read_default(self):
        try:
            contents = self.konsolerc.read_text() if self.konsolerc.exists() else ""
        except OSError as exc:
            raise ControllerError("Konsole 설정을 읽지 못했어요.") from exc
        return ini(contents).get("Desktop Entry", "DefaultProfile", fallback=None)

    def write_default(self, profile):
        args = [
            "/usr/bin/kwriteconfig6",
            "--file",
            str(self.konsolerc),
            "--group",
            "Desktop Entry",
            "--key",
            "DefaultProfile",
        ]
        self.backend.command(args + (["--delete"] if profile is None else [profile]))
        if self.read_default() != profile:
            raise ControllerError("터미널 기본 프로필 저장을 확인하지 못했어요.")

    def resource(self, name, extension):
        if not isinstance(name, str) or not name or any(c in name for c in ("/", "\\", "\n", "\r")):
            return None
        filename = name if name.endswith(extension) else name + extension
        for directory in (self.konsole_dir, Path("/usr/share/konsole"), Path("/usr/share/apps/konsole")):
            path = directory / filename
            if path.is_file():
                return path
        return None

    def original_terminal(self):
        default = self.read_default()
        profile_path = self.resource(default, ".profile")
        if default and not profile_path:
            raise ControllerError("기본 Konsole 프로필을 찾지 못했어요. Konsole에서 프로필을 저장해 주세요.")
        contents = profile_path.read_text() if profile_path else "[General]\nParent=FALLBACK/\n"
        parser = ini(contents)
        scheme = parser.get("Appearance", "ColorScheme", fallback="")
        scheme_path = self.resource(scheme, ".colorscheme")
        if scheme and not scheme_path:
            raise ControllerError("기존 색 구성표를 찾지 못했어요. Konsole에서 색 구성표를 저장해 주세요.")
        return {
            "default": default,
            "name": parser.get("General", "Name", fallback=Path(default).stem if default else "Default"),
            "profile": contents,
            "scheme": scheme_path.read_text() if scheme_path else "",
        }

    def status(self):
        with self.lock:
            error = None
            try:
                desktop = self.backend.desktops()
            except ControllerError as exc:
                desktop = {"activity": "", "desktops": []}
                error = str(exc)
            original = self.state["terminal"]
            settings = self.state["settings"]
            if settings is None:
                try:
                    original = original or self.original_terminal()
                    scheme = ini(original["scheme"])
                    settings = dict(DEFAULT_TERMINAL)
                    for key, section in (("background", "Background"), ("foreground", "Foreground")):
                        color = scheme.get(section, "Color", fallback="")
                        if re.fullmatch(r"\d{1,3},\d{1,3},\d{1,3}", color):
                            rgb = [int(c) for c in color.split(",")]
                            if max(rgb) <= 255:
                                settings[key] = "#" + "".join(f"{c:02x}" for c in rgb)
                    settings["image"] = scheme.get("General", "Wallpaper", fallback="")
                    for key, entry in (("opacity", "Opacity"), ("image_opacity", "WallpaperOpacity")):
                        settings[key] = max(
                            0, min(100, round(float(scheme.get("General", entry, fallback="1")) * 100))
                        )
                    terminal_error = None
                except (ControllerError, ValueError) as exc:
                    settings = dict(DEFAULT_TERMINAL)
                    terminal_error = str(exc)
            else:
                terminal_error = None
            return {
                **desktop,
                "desktop_error": error,
                "wallpaper_baselines": list(self.state["wallpapers"]),
                "terminal": {
                    "default_profile": self.read_default(),
                    "settings": settings,
                    "has_baseline": self.state["terminal"] is not None,
                    "error": terminal_error,
                },
            }

    def wallpaper_set(self, image, desktop_id=None, fill="crop"):
        with self.lock:
            if desktop_id is not None and (type(desktop_id) is not int or desktop_id < 0):
                raise ControllerError("화면을 다시 선택해 주세요.")
            if not isinstance(fill, str) or fill not in FILL_MODES:
                raise ControllerError("이미지 배치 방식을 선택해 주세요.")
            current = self.backend.desktops()
            rows = [r for r in current["desktops"] if desktop_id is None or r["id"] == desktop_id]
            if not rows:
                raise ControllerError("연결된 화면을 다시 선택해 주세요.")
            owned = self.import_image(image)
            for row in rows:
                self.state["wallpapers"].setdefault(str(row["id"]), {"activity": current["activity"], **row})
            self.save()  # Original is durable before the first write.
            changed = [
                {
                    **r,
                    "plugin": "org.kde.image",
                    "image": {"Image": Path(owned).as_uri(), "FillMode": FILL_MODES[fill]},
                }
                for r in rows
            ]
            try:
                self.backend.write(current["activity"], changed)
                check = self.backend.desktops()
                observed = {r["id"]: r for r in check["desktops"]}
                if check["activity"] != current["activity"] or any(
                    observed.get(r["id"]) != r for r in changed
                ):
                    raise ControllerError("배경 적용을 확인하지 못했어요.")
            except ControllerError as exc:
                try:
                    self.backend.write(current["activity"], rows)
                except ControllerError:
                    raise ControllerError(
                        "배경 적용과 복원에 실패했어요. 원래 배경으로 버튼을 눌러 주세요."
                    ) from exc
                raise ControllerError("배경 적용을 확인하지 못해 이전 배경으로 되돌렸어요.") from exc
            return self.status()

    def wallpaper_reset(self, desktop_id=None):
        with self.lock:
            if desktop_id is not None and (type(desktop_id) is not int or desktop_id < 0):
                raise ControllerError("화면을 다시 선택해 주세요.")
            current = self.backend.desktops()
            rows = []
            for row in current["desktops"]:
                original = self.state["wallpapers"].get(str(row["id"]))
                if (
                    original
                    and original["activity"] == current["activity"]
                    and (desktop_id is None or row["id"] == desktop_id)
                ):
                    rows.append(
                        {k: v for k, v in original.items() if k != "activity"} | {"screen": row["screen"]}
                    )
            if not rows:
                raise ControllerError("선택한 화면에 저장된 원래 배경이 없어요.")
            before = [r for r in current["desktops"] if r["id"] in {v["id"] for v in rows}]
            try:
                self.backend.write(current["activity"], rows)
                observed = {r["id"]: r for r in self.backend.desktops()["desktops"]}
                if any(observed.get(r["id"]) != r for r in rows):
                    raise ControllerError("원래 배경 복원을 확인하지 못했어요.")
            except ControllerError:
                self.backend.write(current["activity"], before)
                raise
            return self.status()

    def terminal_configure(self, settings):
        with self.lock:
            values = terminal_settings(settings)
            if values["image"]:
                values["image"] = self.import_image(values["image"])
            original = self.state["terminal"] or self.original_terminal()
            scheme = ini(original["scheme"])
            for key, section in (("background", "Background"), ("foreground", "Foreground")):
                rgb = ",".join(str(int(values[key][i : i + 2], 16)) for i in (1, 3, 5))
                for variant in ("", "Faint", "Intense"):
                    put(scheme, section + variant, "Color", rgb)
            for key, value in {
                "Opacity": values["opacity"] / 100,
                "Wallpaper": values["image"],
                "WallpaperOpacity": values["image_opacity"] / 100,
                "FillStyle": "Crop",
                "WallpaperFlipType": "NoFlip",
            }.items():
                put(scheme, "General", key, value)
            name = MANAGED
            put(scheme, "General", "Description", "프리렌 컨트롤러")
            profile = ini(original["profile"])
            put(profile, "General", "Name", "프리렌 컨트롤러")
            put(profile, "Appearance", "ColorScheme", name)
            files = {
                self.konsole_dir / (name + ".colorscheme"): dump_ini(scheme),
                self.konsole_dir / (name + ".profile"): dump_ini(profile),
            }
            previous_files = {path: path.read_text() if path.exists() else None for path in files}
            self.state["terminal"] = original
            before_default = self.read_default()
            before_settings = self.state["settings"]
            self.save()
            try:
                for path, contents in files.items():
                    atomic(path, contents)
                self.write_default(name + ".profile")
                self.state["settings"] = values
                self.save()
            except ControllerError as exc:
                failures = []
                for path, contents in previous_files.items():
                    try:
                        if contents is None:
                            path.unlink(missing_ok=True)
                        else:
                            atomic(path, contents)
                    except (ControllerError, OSError):
                        failures.append("profile")
                try:
                    self.write_default(before_default)
                except ControllerError:
                    failures.append("default")
                self.state["settings"] = before_settings
                self.save()
                if failures:
                    raise ControllerError(
                        "터미널 적용과 복원에 실패했어요. 원래 설정으로 버튼을 눌러 주세요."
                    ) from exc
                raise ControllerError("터미널 적용을 확인하지 못해 이전 설정으로 되돌렸어요.") from exc
            return self.status()

    def terminal_reset(self):
        with self.lock:
            original = self.state["terminal"]
            if original is None:
                raise ControllerError("아직 저장된 원래 터미널 설정이 없어요.")
            before_default = self.read_default()
            before_settings = self.state["settings"]
            try:
                self.write_default(original["default"])
                self.state["settings"] = None
                self.save()
            except ControllerError:
                self.write_default(before_default)
                self.state["settings"] = before_settings
                self.save()
                raise
            return self.status()

    def terminal_open(self):
        """Open a separate Konsole using the current validated profile; no client-supplied command."""
        with self.lock:
            default = self.read_default()
            if default and not self.resource(default, ".profile"):
                raise ControllerError("Konsole 프로필을 찾지 못했어요. 설정을 다시 적용해 주세요.")
            args = ["/usr/bin/konsole", "--separate"]
            if default:
                args.extend(["--profile", str(self.resource(default, ".profile"))])
            try:
                subprocess.Popen(
                    args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
                )
            except OSError as exc:
                raise ControllerError("Konsole을 열지 못했어요. 설치 상태를 확인해 주세요.") from exc
            return self.status()
