"""Installed KDE style choices and targeted restoration, without resetting panel layouts."""

from __future__ import annotations

import re
from pathlib import Path

from .appearance import atomic, dump_ini, ini
from .core import ControllerError
from .desktop_common import Config, choice, fields, integer, run
from .themes import THEMES

STYLE_KEYS = {
    "color_scheme": ("kdeglobals", ("General",), "ColorScheme"),
    "plasma_style": ("plasmarc", ("Theme",), "name"),
    "icons": ("kdeglobals", ("Icons",), "Theme"),
    "cursor": ("kcminputrc", ("Mouse",), "cursorTheme"),
    "cursor_size": ("kcminputrc", ("Mouse",), "cursorSize"),
    "font": ("kdeglobals", ("General",), "font"),
    "fixed_font": ("kdeglobals", ("General",), "fixed"),
    "decoration_library": ("kwinrc", ("org.kde.kdecoration2",), "library"),
    "decoration_theme": ("kwinrc", ("org.kde.kdecoration2",), "theme"),
    "lock_plugin": ("kscreenlockerrc", ("Greeter",), "WallpaperPlugin"),
    "lock_image": ("kscreenlockerrc", ("Greeter", "Wallpaper", "org.kde.image", "General"), "Image"),
    "lock_preview": ("kscreenlockerrc", ("Greeter", "Wallpaper", "org.kde.image", "General"), "PreviewImage"),
}
COLOR_GROUPS = ("Button", "Complementary", "Header", "Selection", "Tooltip", "View", "Window")
COLOR_ENTRIES = (
    "BackgroundAlternate",
    "BackgroundNormal",
    "DecorationFocus",
    "DecorationHover",
    "ForegroundActive",
    "ForegroundInactive",
    "ForegroundLink",
    "ForegroundNegative",
    "ForegroundNeutral",
    "ForegroundNormal",
    "ForegroundPositive",
    "ForegroundVisited",
)


def catalog(folder, pattern, suffix=""):
    choices = {}
    for root in (Path("/usr/share") / folder, Path.home() / ".local/share" / folder):
        for file in root.glob(pattern):
            identifier = file.stem if suffix else file.name
            if identifier.startswith("-") or not re.fullmatch(r"[\w .+-]{1,160}", identifier):
                continue
            choices[identifier] = identifier
    return choices


class StyleControls:
    def __init__(self, appearance, config=None):
        self.appearance = appearance
        self.config = config or Config()
        self._install_colors()

    def _install_colors(self):
        base = Path("/usr/share/color-schemes/BreezeDark.colors")
        if not base.is_file():
            return
        root = Path.home() / ".local/share/color-schemes"
        for name, theme in THEMES.items():
            parser = ini(base.read_text())
            colors = theme["colors"]
            parser.set("General", "Name", theme["name"])
            for group in COLOR_GROUPS:
                section = "Colors:" + group
                if not parser.has_section(section):
                    parser.add_section(section)
                for key in COLOR_ENTRIES:
                    color = colors["text"] if key.startswith("Foreground") else colors["surface"]
                    if key.startswith("Decoration") or key in ("ForegroundLink", "ForegroundActive"):
                        color = colors["accent"]
                    if key == "BackgroundNormal" and group in ("Window", "View"):
                        color = colors["background"]
                    if group == "Selection" and key.startswith("Background"):
                        color = colors["selected"]
                    parser.set(section, key, ",".join(str(int(color[i : i + 2], 16)) for i in (1, 3, 5)))
            target = root / ("Frieren" + name.capitalize() + ".colors")
            if not target.is_file():
                atomic(target, dump_ini(parser))

    def status(self):
        current = self.config.capture(STYLE_KEYS, STYLE_KEYS)
        fonts = sorted(set(run(["/usr/bin/fc-list", "--format", "%{family[0]}\n"]).splitlines()))
        icons = {}
        cursors = {}
        for root in (Path("/usr/share/icons"), Path.home() / ".local/share/icons", Path.home() / ".icons"):
            for theme in root.glob("*/index.theme"):
                name = theme.parent.name
                if name.startswith("-") or "/" in name:
                    continue
                if (theme.parent / "cursors").is_dir():
                    cursors[name] = name
                elif (theme.parent / "scalable").is_dir() or "[Icon Theme]" in theme.read_text(
                    errors="replace"
                ):
                    icons[name] = name
        decorations = {"org.kde.breeze": {"name": "Breeze", "library": "org.kde.breeze", "theme": None}}
        for name in catalog("aurorae/themes", "*"):
            decorations["aurorae:" + name] = {
                "name": name,
                "library": "org.kde.kwin.aurorae.v2",
                "theme": name,
            }
        current["decoration"] = next(
            (
                k
                for k, v in decorations.items()
                if v["library"] == current["decoration_library"] and v["theme"] == current["decoration_theme"]
            ),
            None,
        )
        return {
            "current": current,
            "choices": {
                "color_scheme": catalog("color-schemes", "*.colors", ".colors"),
                "plasma_style": catalog("plasma/desktoptheme", "*"),
                "icons": icons,
                "cursor": cursors,
                "decoration": decorations,
                "fonts": [f for f in fonts if "," not in f and "\n" not in f],
            },
        }

    def validate(self, settings):
        values = fields(
            settings,
            {
                "color_scheme",
                "plasma_style",
                "icons",
                "cursor",
                "cursor_size",
                "font_family",
                "font_size",
                "fixed_family",
                "fixed_size",
                "decoration",
                "lock_image",
            },
        )
        choices = self.status()["choices"]
        for key in ("color_scheme", "plasma_style", "icons", "cursor", "decoration"):
            if key in values:
                choice(values[key], choices[key])
        if "cursor_size" in values:
            integer(values["cursor_size"], 16, 64, "커서 크기")
        for prefix in ("font", "fixed"):
            if prefix + "_family" in values or prefix + "_size" in values:
                if prefix + "_family" not in values or prefix + "_size" not in values:
                    raise ControllerError("글꼴과 크기를 함께 선택해 주세요.")
                choice(values[prefix + "_family"], choices["fonts"], "설치된 글꼴")
                integer(values[prefix + "_size"], 6, 32, "글꼴 크기")
        if "lock_image" in values:
            if not isinstance(values["lock_image"], str) or not values["lock_image"]:
                raise ControllerError("잠금 화면 이미지를 선택해 주세요.")
            # Decoding/import happens before any desktop setting is changed.
            values["lock_image"] = str(self.appearance.import_image(values["lock_image"]))
        return values

    def _keys(self, settings):
        keys = {k for k in settings if k in STYLE_KEYS}
        if "font_family" in settings:
            keys.add("font")
        if "fixed_family" in settings:
            keys.add("fixed_font")
        if "decoration" in settings:
            keys.update(("decoration_library", "decoration_theme"))
        if "lock_image" in settings:
            keys.update(("lock_image", "lock_preview", "lock_plugin"))
        return keys

    def capture(self, settings):
        result = {"values": self.config.capture(STYLE_KEYS, self._keys(settings))}
        if "color_scheme" in settings:
            parser = ini((Path.home() / ".config/kdeglobals").read_text())
            result["palette"] = {
                group: {key: parser.get("Colors:" + group, key, fallback=None) for key in COLOR_ENTRIES}
                for group in COLOR_GROUPS
            }
        return result

    def apply(self, settings):
        values = self.validate(settings)
        current = self.status()["current"]
        for key, executable in (
            ("color_scheme", "plasma-apply-colorscheme"),
            ("plasma_style", "plasma-apply-desktoptheme"),
        ):
            if key in values and values[key] != current[key]:
                run(["/usr/bin/" + executable, values[key]])
        if "cursor" in values or "cursor_size" in values:
            cursor = values.get("cursor", current["cursor"])
            size = int(values.get("cursor_size", current["cursor_size"] or 24))
            if cursor != current["cursor"] or str(size) != current["cursor_size"]:
                run(["/usr/bin/plasma-apply-cursortheme", "--size", str(size), cursor])
        writes = {}
        if "cursor_size" in values:
            writes["cursor_size"] = str(values["cursor_size"])
        if "icons" in values:
            writes["icons"] = values["icons"]
        for prefix, target in (("font", "font"), ("fixed", "fixed_font")):
            if prefix + "_family" in values:
                writes[target] = f"{values[prefix + '_family']},{values[prefix + '_size']},-1,5,50,0,0,0,0,0"
        if "decoration" in values:
            item = self.status()["choices"]["decoration"][values["decoration"]]
            writes.update(decoration_library=item["library"], decoration_theme=item["theme"])
        if "lock_image" in values:
            url = Path(values["lock_image"]).as_uri()
            writes.update(lock_image=url, lock_preview=url, lock_plugin="org.kde.image")
        if writes:
            self.config.restore(STYLE_KEYS, writes)
            self._reload(writes)
        actual = self.config.capture(STYLE_KEYS, {*writes, *(k for k in values if k in STYLE_KEYS)})
        expected = {**{k: str(v) for k, v in values.items() if k in STYLE_KEYS}, **writes}
        if actual != expected:
            raise ControllerError("변경한 스타일을 확인하지 못했어요.")

    def _reload(self, writes):
        for change in ([4] if "icons" in writes else []) + (
            [1] if {"font", "fixed_font"} & set(writes) else []
        ):
            self.config.bus.bus.emit_signal(
                None,
                "/KGlobalSettings",
                "org.kde.KGlobalSettings",
                "notifyChange",
                self.config.bus.GLib.Variant("(ii)", (change, 0)),
            )
        if {"font", "fixed_font"} & set(writes):
            run(["/usr/bin/kcminit", "kcm_fonts"])
        if {"cursor", "cursor_size"} & set(writes):
            run(["/usr/bin/kcminit", "kcm_cursortheme"])
            self.config.bus.bus.emit_signal(
                None,
                "/KGlobalSettings",
                "org.kde.KGlobalSettings",
                "notifyChange",
                self.config.bus.GLib.Variant("(ii)", (5, 0)),
            )
        if {"decoration_library", "decoration_theme"} & set(writes):
            self.config.bus.call("org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure")
        self.config.bus.bus.flush_sync(None)

    def restore(self, snapshot):
        values = snapshot["values"]
        current = self.status()["current"]
        for key, executable in (
            ("color_scheme", "plasma-apply-colorscheme"),
            ("plasma_style", "plasma-apply-desktoptheme"),
        ):
            if key in values and values[key] and values[key] != current[key]:
                run(["/usr/bin/" + executable, values[key]])
        if "cursor" in values or "cursor_size" in values:
            cursor = values.get("cursor") or current["cursor"]
            size = values.get("cursor_size") or current["cursor_size"] or "24"
            if cursor != current["cursor"] or size != current["cursor_size"]:
                run(["/usr/bin/plasma-apply-cursortheme", "--size", size, cursor])
        self.config.restore(STYLE_KEYS, values)
        if "palette" in snapshot:
            palette_map = {
                group + "/" + key: ("kdeglobals", ("Colors:" + group,), key)
                for group in COLOR_GROUPS
                for key in COLOR_ENTRIES
            }
            palette = {
                group + "/" + key: value
                for group, rows in snapshot["palette"].items()
                for key, value in rows.items()
            }
            self.config.restore(palette_map, palette)
            self.config.bus.bus.emit_signal(
                None,
                "/KGlobalSettings",
                "org.kde.KGlobalSettings",
                "notifyChange",
                self.config.bus.GLib.Variant("(ii)", (0, 0)),
            )
        self._reload(values)
