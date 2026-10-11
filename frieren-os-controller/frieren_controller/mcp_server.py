"""MCP v2 stdio facade for the same local API used by the GUI."""

from __future__ import annotations

from functools import partial

from mcp.server import MCPServer

from .client import call as api_call

call = partial(api_call, _source="mcp")

mcp = MCPServer("Frieren OS Controller")


@mcp.tool()
def job_unit_read(unit: str) -> dict:
    """Read an eligible user service/timer editor content, reference and conflict revision."""
    return call("job_unit_read", unit=unit)


@mcp.tool()
def job_unit_save(unit: str, content: str, revision: str) -> dict:
    """Validate/store a user service/timer; reload definitions without starting/restarting jobs."""
    return call("job_unit_save", unit=unit, content=content, revision=revision)


@mcp.tool()
def job_cron_read() -> dict:
    """Read current user's crontab and Cronie availability; no root/system crontab access."""
    return call("job_cron_read")


@mcp.tool()
def job_cron_save(content: str, revision: str) -> dict:
    """Validate/install current user's complete crontab with a conflict revision and private backup."""
    return call("job_cron_save", content=content, revision=revision)


@mcp.tool()
def list_units(scope: str = "system", kind: str = "all", search: str = "") -> list[dict]:
    """List local system or user services and timers, including disabled units."""
    return call("list_units", scope=scope, kind=kind, search=search)


@mcp.tool()
def describe_unit(scope: str, unit: str) -> dict:
    """Read a service or timer's current status, installation state and saved note."""
    return call("describe_unit", scope=scope, unit=unit)


@mcp.tool()
def preview_toggle(scope: str, unit: str, enabled: bool) -> dict:
    """Show the action and current status before changing a service or timer."""
    return call("preview_toggle", scope=scope, unit=unit, enabled=enabled)


@mcp.tool()
def toggle_unit(scope: str, unit: str, enabled: bool) -> dict:
    """Enable/start or disable/stop an eligible unit; system actions may invoke desktop PolicyKit."""
    return call("toggle_unit", scope=scope, unit=unit, enabled=enabled)


@mcp.tool()
def get_note(scope: str, unit: str) -> str:
    """Read the user's note for a system or user unit."""
    return call("get_note", scope=scope, unit=unit)


@mcp.tool()
def set_note(scope: str, unit: str, note: str) -> dict:
    """Save the user's note for a service or timer, up to 4000 characters."""
    return call("set_note", scope=scope, unit=unit, note=note)


@mcp.tool()
def journal_tail(scope: str, unit: str, lines: int = 30) -> dict:
    """Read up to 100 recent local journal lines for a specific service or timer."""
    return call("journal_tail", scope=scope, unit=unit, lines=lines)


@mcp.tool()
def dashboard() -> list[dict]:
    """Read health, disk, log, power controller and custom module cards."""
    return call("dashboard")


@mcp.tool()
def quiet_status() -> dict:
    """Read Freiren Quiet mode, CPU temperature, speed limit and power profile."""
    return call("quiet_status")


@mcp.tool()
def quiet_set_mode(mode: str) -> dict:
    """Select auto, quiet, balanced, performance, saved custom settings, or restore."""
    return call("quiet_set_mode", mode=mode)


@mcp.tool()
def quiet_set_target(temperature: int) -> dict:
    """Set Freiren Quiet automatic target temperature to an integer from 58 to 75 Celsius."""
    return call("quiet_set_target", temperature=temperature)


@mcp.tool()
def quiet_set_effects(enabled: bool) -> dict:
    """Temporarily reduce or restore the current KDE session's blur, contrast and translucency effects."""
    return call("quiet_set_effects", enabled=enabled)


@mcp.tool()
def quiet_configure(
    cap: int,
    turbo: bool,
    preference: str = "balance_performance",
    power_w: float | None = None,
    boost_w: float | None = None,
) -> dict:
    """Apply bounded custom CPU/thermal settings; power limits cannot exceed the captured baseline."""
    return call(
        "quiet_configure",
        settings={
            "cap": cap,
            "turbo": turbo,
            "preference": preference,
            "power_w": power_w,
            "boost_w": boost_w,
        },
    )


@mcp.tool()
def quiet_reset() -> dict:
    """Restore the captured original CPU and power limits, and stop automatic management."""
    return call("quiet_reset")


@mcp.tool()
def audit_log(limit: int = 50) -> list[dict]:
    """Read the controller's recent note, module and service changes."""
    return call("audit_log", limit=limit)


@mcp.tool()
def list_modules() -> list[dict]:
    """List built-in cards and agent-created declarative cards."""
    return call("list_modules")


@mcp.tool()
def read_module(name: str) -> dict:
    """Read one card's validated declarative definition."""
    return call("read_module", name=name)


@mcp.tool()
def write_module(name: str, definition: dict) -> dict:
    """Create or update a unit or disk card without executing supplied code."""
    return call("write_module", name=name, definition=definition)


@mcp.tool()
def run_check(name: str) -> dict:
    """Run the read-only status check for one card."""
    return call("run_check", name=name)


@mcp.tool()
def monitor_status() -> dict:
    """Read brightness, night color, connected modes and pending display recovery."""
    return call("monitor_status")


@mcp.tool()
def monitor_configure(settings: dict) -> dict:
    """Apply and save custom brightness/night settings. Read monitor_status for the fixed settings schema."""
    return call("monitor_configure", settings=settings)


@mcp.tool()
def monitor_preset(name: str) -> dict:
    """Apply work, night, presentation, battery, or saved custom display settings."""
    return call("monitor_preset", name=name)


@mcp.tool()
def monitor_reset() -> dict:
    """Restore captured original display settings; returned pending layout needs confirmation within 15s."""
    return call("monitor_reset")


@mcp.tool()
def monitor_keep_awake(minutes: int) -> dict:
    """Keep screens on for 1–240 minutes, or release with 0. Does not disable locking or system suspend."""
    return call("monitor_keep_awake", minutes=minutes)


@mcp.tool()
def monitor_original_color(minutes: int) -> dict:
    """Temporarily show original colors for 1–120 minutes; restore night colors with 0."""
    return call("monitor_original_color", minutes=minutes)


@mcp.tool()
def monitor_preview_layout(layout: list[dict]) -> dict:
    """Preview connected modes/rotation/positions/primary. Service reverts in 15s unless confirmed."""
    return call("monitor_preview_layout", layout=layout)


@mcp.tool()
def monitor_confirm_layout(token: str, keep: bool) -> dict:
    """Confirm or revert the exact pending layout token before its deadline."""
    return call("monitor_confirm_layout", token=token, keep=keep)


@mcp.tool()
def monitor_external_status() -> dict:
    """Detect DDC/CI monitors and read supported brightness, contrast and input choices."""
    return call("monitor_external_status")


@mcp.tool()
def monitor_external_set(identifier: str, feature: str, value: int) -> dict:
    """Set a detected monitor's brightness/contrast percent or supported input value; verify readback."""
    return call("monitor_external_set", identifier=identifier, feature=feature, value=value)


@mcp.tool()
def monitor_external_reset(identifier: str) -> dict:
    """Restore this monitor's captured original DDC values; detects device identity before writing."""
    return call("monitor_external_reset", identifier=identifier)


@mcp.tool()
def appearance_status() -> dict:
    """Read active KDE desktops, saved originals and Konsole appearance settings."""
    return call("appearance_status")


@mcp.tool()
def wallpaper_set(image: str, desktop_id: int | None = None, fill: str = "crop") -> dict:
    """Apply a local PNG/JPEG/WebP to one or all connected desktops.

    Fill: crop/fit/stretch/center/tile. Originals are preserved for reset.
    """
    return call("wallpaper_set", image=image, desktop_id=desktop_id, fill=fill)


@mcp.tool()
def wallpaper_reset(desktop_id: int | None = None) -> dict:
    """Restore captured wallpaper and image placement for connected desktops in the current activity."""
    return call("wallpaper_reset", desktop_id=desktop_id)


@mcp.tool()
def terminal_configure(
    background: str,
    foreground: str,
    opacity: int = 90,
    image_opacity: int = 24,
    image: str = "",
) -> dict:
    """Set Konsole colors (#RRGGBB), opacity 0–100 and optional local image.

    Save a separate profile for new windows and preserve the original profile.
    """
    return call(
        "terminal_configure",
        settings={
            "background": background,
            "foreground": foreground,
            "opacity": opacity,
            "image_opacity": image_opacity,
            "image": image,
        },
    )


@mcp.tool()
def terminal_reset() -> dict:
    """Restore Konsole's original default profile; open a new window to use it."""
    return call("terminal_reset")


@mcp.tool()
def terminal_open() -> dict:
    """Open a separate Konsole window using the saved default appearance."""
    return call("terminal_open")


@mcp.tool()
def workspace_status(area: str) -> dict:
    """Read panels/style/windows/audio/input/network/session/power/display capabilities and live values."""
    return call("workspace_status", area=area)


@mcp.tool()
def workspace_configure(area: str, settings: dict) -> dict:
    """Apply fixed settings with snapshots, readback and rollback. No shell/script input.

    For area="session", session_restore is a boolean: true restores apps from the
    last logout on next login, false starts an empty session. Autostart is separate.
    """
    return call("workspace_configure", area=area, settings=settings)


@mcp.tool()
def work_mode_status() -> dict:
    """Read built-in/custom integrated work modes, their settings and the currently active mode."""
    return call("work_mode_status")


@mcp.tool()
def work_mode_save(name: str, settings: dict) -> dict:
    """Save a named mode combining power, display, session, audio, style, windows, input or panels."""
    return call("work_mode_save", name=name, settings=settings)


@mcp.tool()
def work_mode_apply(name: str) -> dict:
    """Apply research/presentation/away or a saved mode transactionally, retaining the previous settings."""
    return call("work_mode_apply", name=name)


@mcp.tool()
def work_mode_end() -> dict:
    """End the active mode and restore its previous settings, checking external edits for conflicts."""
    return call("work_mode_end")


@mcp.tool()
def workspace_presets(area: str) -> dict:
    """Read saved presets for a desktop settings area."""
    return call("workspace_presets", area=area)


@mcp.tool()
def workspace_save_preset(area: str, name: str, settings: dict) -> dict:
    """Save a validated style/window/audio/input/panel preset without applying it."""
    return call("workspace_save_preset", area=area, name=name, settings=settings)


@mcp.tool()
def workspace_apply_preset(area: str, name: str) -> dict:
    """Apply a saved settings preset using the same transaction and history as the GUI."""
    return call("workspace_apply_preset", area=area, name=name)


@mcp.tool()
def settings_history(limit: int = 50) -> list[dict]:
    """Read private change snapshots and GUI/CLI/MCP/widget provenance, with reversible status."""
    return call("settings_history", limit=limit)


@mcp.tool()
def settings_revert(identifier: str) -> dict:
    """Restore the exact change if device/window identities and current settings still match."""
    return call("settings_revert", identifier=identifier)


@mcp.tool()
def settings_recover() -> dict:
    """Retry restoring a desktop transaction interrupted by a failure or service restart."""
    return call("settings_recover")


@mcp.tool()
def himmel_open() -> dict:
    """Open the existing Himmel shortcut; never change the remote physical display resolution."""
    return call("himmel_open")


@mcp.tool()
def widget_status() -> dict:
    """Read the small temperature/brightness/power/work-mode summary used by the Plasma widget."""
    return call("widget_status")


@mcp.tool()
def widget_brightness(value: int) -> dict:
    """Set brightness to an integer 5–100 through the same recorded display operation as the widget."""
    return call("widget_brightness", value=value)


def main() -> int:
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
