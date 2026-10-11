"""Existing Plasma panels and an allowlist of desktop/panel widgets."""

from __future__ import annotations

import json

from .appearance import PlasmaBackend
from .core import ControllerError
from .desktop_common import choice, fields, integer

WIDGETS = {
    "clock": ("시계", "org.kde.plasma.digitalclock"),
    "cpu": ("CPU 사용률", "org.kde.plasma.systemmonitor.cpu"),
    "memory": ("메모리", "org.kde.plasma.systemmonitor.memory"),
    "controller": ("프리렌 컨트롤러", "io.github.BumBoo.FrierenController"),
}


class PanelControls:
    def __init__(self, backend=None):
        self.backend = backend or PlasmaBackend()

    def status(self):
        value = self.backend.script("""
var rows=panels().map(function(p){return {id:p.id,screen:p.screen,location:p.location,
height:p.height,hiding:p.hiding,length_mode:p.lengthMode,alignment:p.alignment,
widgets:p.widgets().map(function(w){return {id:w.id,type:w.type};})};});
var ds=desktops().filter(function(d){return d.screen>=0;}).map(function(d){return {
id:d.id,screen:d.screen,widgets:d.widgets().map(function(w){return {id:w.id,type:w.type};})};});
print(JSON.stringify({panels:rows,desktops:ds,activity:currentActivity(),available:knownWidgetTypes}));
""")
        value["kinds"] = [
            {
                "id": key,
                "name": name,
                "plugin": plugin,
                "available": plugin in value["available"],
            }
            for key, (name, plugin) in WIDGETS.items()
        ]
        return value

    def validate(self, settings):
        values = fields(settings, {"panel", "widget"})
        if len(values) != 1:
            raise ControllerError("패널 설정과 위젯 추가는 하나씩 적용해 주세요.")
        state = self.status()
        if "panel" in values:
            panel = fields(
                values["panel"], {"id", "location", "height", "hiding", "length_mode", "alignment"}, ("id",)
            )
            integer(panel["id"], 1, 2**31 - 1, "패널 식별자")
            if panel["id"] not in {p["id"] for p in state["panels"]}:
                raise ControllerError("패널 구성이 바뀌었어요. 다시 선택해 주세요.")
            if len(panel) == 1:
                raise ControllerError("바꿀 패널 설정을 선택해 주세요.")
            for key, options in (
                ("location", ("top", "bottom", "left", "right")),
                ("hiding", ("none", "autohide", "dodgewindows", "windowsgobelow")),
                ("length_mode", ("fit", "fill", "custom")),
                ("alignment", ("left", "center", "right")),
            ):
                if key in panel:
                    choice(panel[key], options)
            if "height" in panel:
                integer(panel["height"], 24, 128, "패널 크기")
        else:
            widget = fields(values["widget"], {"target", "id", "kind"}, ("target", "id", "kind"))
            choice(widget["target"], ("panel", "desktop"))
            integer(widget["id"], 1, 2**31 - 1, "배치할 곳")
            choice(widget["kind"], {r["id"] for r in state["kinds"] if r["available"]}, "위젯")
            rows = state["panels" if widget["target"] == "panel" else "desktops"]
            if widget["id"] not in {r["id"] for r in rows}:
                raise ControllerError("위젯을 배치할 곳이 바뀌었어요.")
        return values

    def capture(self, settings):
        state = self.status()
        kind = next(iter(settings))
        target = settings[kind]
        rows = state["panels" if kind == "panel" or target["target"] == "panel" else "desktops"]
        row = next((r for r in rows if r["id"] == target["id"]), None)
        if not row:
            raise ControllerError("선택한 패널이나 화면을 확인하지 못했어요.")
        if kind == "panel":
            return {"panel": {k: row[k] for k in target}, "screen": row["screen"]}
        return {
            "target": target["target"],
            "id": row["id"],
            "kind": target["kind"],
            "activity": state["activity"],
            "widgets": row["widgets"],
        }

    def apply(self, settings):
        values = self.validate(settings)
        if "panel" in values:
            row = values["panel"]
            self.backend.script(
                "var v="
                + json.dumps(row)
                + """;
var p=panelById(v.id); if(!p) throw new Error("패널이 바뀌었어요.");
Object.keys(v).forEach(function(k){if(k!=="id")p[k==="length_mode"?"lengthMode":k]=v[k];});
print(JSON.stringify({id:p.id}));
"""
            )
            actual = self.capture(values)["panel"]
            if actual != row:
                raise ControllerError("변경한 패널 설정을 확인하지 못했어요.")
        else:
            row = values["widget"]
            self.backend.script(
                "var v="
                + json.dumps(row)
                + ";var plugin="
                + json.dumps(WIDGETS[row["kind"]][1])
                + """;
var c=v.target==="panel"?panelById(v.id):desktopById(v.id);
if(!c || c.screen<0) throw new Error("배치할 곳이 바뀌었어요.");
var w=c.addWidget(plugin); print(JSON.stringify({id:w.id}));
"""
            )

    def restore(self, snapshot):
        if "panel" in snapshot:
            current = self.capture({"panel": snapshot["panel"]})
            if current["screen"] != snapshot["screen"]:
                raise ControllerError("패널의 화면 연결이 바뀌었어요.")
            self.apply({"panel": snapshot["panel"]})
        else:
            state = self.status()
            if state["activity"] != snapshot["activity"]:
                raise ControllerError("작업 공간이 바뀌었어요. 원래 공간에서 복원해 주세요.")
            self.backend.script(
                "var v="
                + json.dumps(snapshot)
                + ";var plugin="
                + json.dumps(WIDGETS[snapshot["kind"]][1])
                + """;
var c=v.target==="panel"?panelById(v.id):desktopById(v.id);
if(!c) throw new Error("배치한 곳이 바뀌었어요.");
var old=v.widgets.map(function(w){return w.id;});
c.widgets().forEach(function(w){if(old.indexOf(w.id)<0 && w.type===plugin)w.remove();});
print(JSON.stringify({ok:true}));
"""
            )
