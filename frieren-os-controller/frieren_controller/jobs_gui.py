"""Small job editors opened from the existing service/timer pages."""

from __future__ import annotations

from functools import partial

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .client import call as api_call  # noqa: E402
from .core import ControllerError  # noqa: E402

call = partial(api_call, _source="gui")


def cron_entry_command(command):
    """The row entry is a shell command; quote cron's separate percent syntax."""
    result = []
    backslashes = 0
    for char in command:
        if char == "%" and backslashes % 2 == 0:
            result.append("\\")
        result.append(char)
        backslashes = backslashes + 1 if char == "\\" else 0
    return "".join(result)


def template(unit):
    if unit.endswith(".timer"):
        service = unit.removesuffix(".timer") + ".service"
        return (
            "[Unit]\nDescription=예약 작업\n\n[Timer]\nOnCalendar=*-*-* 09:00:00\n"
            f"Unit={service}\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"
        )
    return (
        "[Unit]\nDescription=내 서비스\n\n[Service]\nType=simple\n"
        "ExecStart=\nRestart=on-failure\n\n[Install]\nWantedBy=default.target\n"
    )


class JobPages:
    def _job_dialog(self, title):
        dialog = Gtk.Dialog(title=title, transient_for=self, flags=Gtk.DialogFlags.MODAL)
        dialog.set_default_size(820, 650)
        dialog.add_button("닫기", Gtk.ResponseType.CLOSE)
        save = dialog.add_button("저장하기", Gtk.ResponseType.APPLY)
        save.get_style_context().add_class("suggested-action")
        body = dialog.get_content_area()
        body.set_spacing(12)
        body.set_border_width(18)
        hint = Gtk.Label(xalign=0, wrap=True)
        body.pack_start(hint, False, False, 0)
        view = Gtk.TextView()
        view.set_monospace(True)
        view.set_wrap_mode(Gtk.WrapMode.NONE)
        view.set_left_margin(8)
        view.set_right_margin(8)
        scroll = Gtk.ScrolledWindow()
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        scroll.add(view)
        body.pack_start(scroll, True, True, 0)
        status = Gtk.Label(xalign=0, wrap=True, selectable=True)
        body.pack_start(status, False, False, 0)
        self.job_dialog = dialog
        return dialog, body, save, hint, view, status

    def _edit_job_unit(self, kind, new=False):
        selected = dict(self.selected) if self.selected else None
        if not new and (not selected or selected["kind"] != kind or selected["scope"] != "user"):
            return
        dialog, body, save, hint, view, status = self._job_dialog(
            ("서비스 추가" if kind == "service" else "타이머 추가")
            if new
            else "내용 편집 · " + selected["unit"]
        )
        name = Gtk.Entry(placeholder_text="이름." + kind)
        name.set_text("" if new else selected["unit"])
        name.set_editable(new)
        body.pack_start(name, False, False, 0)
        body.reorder_child(name, 0)
        reference = Gtk.Expander(label="현재 설정 보기")
        reference_view = Gtk.TextView(editable=False, monospace=True)
        reference_scroll = Gtk.ScrolledWindow()
        reference_scroll.set_min_content_height(150)
        reference_scroll.add(reference_view)
        reference.add(reference_scroll)
        body.pack_start(reference, False, False, 0)
        body.reorder_child(reference, 2)
        state = {"busy": False, "data": None, "alive": True}
        hint.set_text(
            "내 계정에 저장해요. ExecStart에 실행 명령을 넣어 주세요. 저장 후 목록에서 켜요."
            if kind == "service"
            else "내 계정에 저장해요. 실행할 .service를 먼저 만들고 OnCalendar에 주기를 넣어 주세요."
        )
        buffer = view.get_buffer()
        buffer.set_text(template("new-job." + kind) if new else "")

        def failure(message):
            if state["alive"]:
                state["busy"] = False
                view.set_editable(new or state["data"] is not None)
                name.set_editable(new and state["data"] is None)
                save.set_sensitive(new or state["data"] is not None)
                status.set_text(message)
            return False

        def loaded(data):
            if not state["alive"]:
                return False
            state["data"] = data
            buffer.set_text(
                data["content"]
                or (
                    "[Service]\n# 명령 변경: ExecStart=로 먼저 비우고 새 ExecStart를 적어요.\n"
                    if kind == "service"
                    else "[Timer]\n# 기존 주기를 비우려면 OnCalendar=를 먼저 적어요.\n"
                )
            )
            reference_view.get_buffer().set_text(data["reference"])
            view.set_editable(True)
            status.set_text("")
            if data["mode"] == "override":
                hint.set_text("원본은 두고 바꿀 항목만 덧붙여요. 실행 중인 서비스는 다음 시작 때 반영돼요.")
            save.set_sensitive(True)
            return False

        def saved(data):
            if state["alive"]:
                state["busy"] = False
                state["data"] = data
                buffer.set_text(data["content"])
                view.set_editable(True)
                name.set_editable(False)
                reference_view.get_buffer().set_text(data["reference"])
                save.set_sensitive(True)
                status.set_text("저장했어요. 실행 중인 서비스는 다시 시작하면 새 설정을 써요.")
                page = self.pages[kind]
                page["scope"].set_active_id("user")
                self._load_list(kind)
            return False

        def response(_dialog, response_id):
            if state["busy"]:
                return
            if response_id != Gtk.ResponseType.APPLY:
                dialog.destroy()
                return
            unit = name.get_text().strip()
            if not unit.endswith("." + kind):
                status.set_text("이름은 ." + kind + "로 끝나야 해요.")
                return
            content = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
            if new and state["data"] is None and kind == "timer":
                content = content.replace(
                    "Unit=new-job.service\n", "Unit=" + unit.removesuffix(".timer") + ".service\n"
                )
            state["busy"] = True
            view.set_editable(False)
            name.set_editable(False)
            save.set_sensitive(False)
            status.set_text("내용을 검사하고 저장하는 중…")

            def operation():
                data = state["data"]
                if data is None:
                    data = call("job_unit_read", unit=unit)
                    if data["exists"]:
                        raise ControllerError("같은 이름이 있어요. 목록에서 선택해 편집해 주세요.")
                return call("job_unit_save", unit=unit, content=content, revision=data["revision"])

            self._work("", operation, saved, failure)

        dialog.connect("response", response)
        dialog.connect("destroy", lambda *_: state.update(alive=False))
        dialog.show_all()
        if not new:
            save.set_sensitive(False)
            view.set_editable(False)
            status.set_text("현재 내용을 읽는 중…")
            self._work("", lambda: call("job_unit_read", unit=selected["unit"]), loaded, failure)
        return dialog

    def _edit_cron(self):
        dialog, body, save, hint, view, status = self._job_dialog("cron 작업 편집")
        hint.set_text("내 계정의 crontab을 편집해요. 주기와 명령을 한 줄에 적고, #을 붙이면 쉬어요.")
        line = Gtk.Box(spacing=8)
        schedule = Gtk.Entry(placeholder_text="분 시 일 월 요일", text="0 9 * * *")
        schedule.set_width_chars(16)
        command = Gtk.Entry(placeholder_text="실행 명령")
        command.set_hexpand(True)
        add = Gtk.Button(label="줄 추가하기")
        line.pack_start(schedule, False, False, 0)
        line.pack_start(command, True, True, 0)
        line.pack_start(add, False, False, 0)
        body.pack_start(line, False, False, 0)
        body.reorder_child(line, 1)
        buffer = view.get_buffer()
        state = {"busy": False, "data": None, "alive": True}
        save.set_sensitive(False)
        line.set_sensitive(False)
        view.set_editable(False)

        def append(*_):
            values = (schedule.get_text().strip(), command.get_text().strip())
            if not all(values) or any("\n" in value or "\r" in value for value in values):
                status.set_text("주기와 명령을 한 줄로 입력해 주세요.")
                return
            old = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
            buffer.set_text(
                old.rstrip("\n")
                + ("\n" if old else "")
                + values[0]
                + " "
                + cron_entry_command(values[1])
                + "\n"
            )
            command.set_text("")

        add.connect("clicked", append)

        def loaded(data):
            if state["alive"]:
                state["busy"] = False
                state["data"] = data
                buffer.set_text(data["content"])
                save.set_sensitive(data["available"])
                line.set_sensitive(data["available"])
                view.set_editable(data["available"])
                status.set_text(data.get("message", ""))
            return False

        def failure(message):
            if state["alive"]:
                state["busy"] = False
                save.set_sensitive(bool(state["data"] and state["data"]["available"]))
                line.set_sensitive(bool(state["data"] and state["data"]["available"]))
                view.set_editable(bool(state["data"] and state["data"]["available"]))
                status.set_text(message)
            return False

        def saved(data):
            loaded(data)
            if state["alive"]:
                status.set_text("저장했어요. " + data.get("message", ""))
            return False

        def response(_dialog, response_id):
            if state["busy"]:
                return
            if response_id != Gtk.ResponseType.APPLY:
                dialog.destroy()
                return
            if not state["data"] or not state["data"]["available"]:
                return
            content = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
            revision = state["data"]["revision"]
            state["busy"] = True
            line.set_sensitive(False)
            view.set_editable(False)
            save.set_sensitive(False)
            status.set_text("주기를 검사하고 저장하는 중…")
            self._work("", lambda: call("job_cron_save", content=content, revision=revision), saved, failure)

        dialog.connect("response", response)
        dialog.connect("destroy", lambda *_: state.update(alive=False))
        dialog.show_all()
        self._work("", lambda: call("job_cron_read"), loaded, failure)
        return dialog
