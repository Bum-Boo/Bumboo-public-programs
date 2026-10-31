# Frieren OS Controller

A local Linux desktop controller for service and timer status, system monitoring, desktop settings, and explicit user actions. The GTK application, CLI, and MCP server use the same local API. It is designed for systemd-based Linux; KDE-specific features require KDE Plasma, and window arrangement currently targets an X11 session.

## Features

- Inspect and control systemd services and timers, with a protected list for critical services.
- View system health, resource use, display and session settings.
- Apply supported KDE desktop changes through fixed system tools.
- Read local status through a user-only Unix socket; MCP uses stdio transport and does not open a network listener.
- Define validated dashboard cards and read or write the current user's systemd and cron job files.
- Optionally connect to an installed Quiet service for its documented status and preset operations.

Available controls depend on the desktop, installed command-line utilities, hardware, and optional integrations. The project has primarily been exercised on an Arch Linux and KDE setup. Other distributions, Wayland, external display controls, and hardware-specific power behavior need separate testing.

## Requirements

- Python 3.11 or later.
- GTK 3, GdkPixbuf and PyGObject provided by the operating system (the GUI loads `Gtk 3.0` and wallpaper checks load `GdkPixbuf 2.0` through GObject introspection). PyGObject is not installed by this project's Python dependency list. Package names: `python3-gi gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0` on Debian/Ubuntu, `python-gobject gtk3` on Arch.
- systemd for service and timer controls.
- KDE Plasma and its command-line tools for KDE appearance, workspace, and desktop integrations.
- `cronie` only if you use cron editing. The application does not install or start it.

Python package dependencies are declared in `pyproject.toml`.

## Install

After installing GTK 3 and PyGObject using your distribution's package manager:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e .
.venv/bin/frieren-controller --help
```

`--system-site-packages` is required: distribution PyGObject lives in the system site-packages, and a plain venv cannot import `gi`. Without it the GUI does not start and the wallpaper tests fail. Create the venv with the interpreter the distribution built PyGObject for, which is not always `python3`; on Ubuntu 24.04 that is `/usr/bin/python3.12`. Check with `.venv/bin/python -c "import gi"`.

The user installer at `packaging/install-user.py` writes a systemd user service, desktop launcher, icon, and Plasma widget, then enables and starts the service. Review it before running: it changes the current user's application and service setup. It does not install system packages. No installer or service command is run by the unit test suite.

## Use

The CLI, GUI, and MCP server are clients of the controller daemon. Start it with `.venv/bin/frieren-controller daemon` (or the user service installed above). It listens on `$XDG_RUNTIME_DIR/frieren-os-controller.sock`. Without a running daemon, the commands below exit with status 1 and print `컨트롤러 서비스에 연결하지 못했어요`.

```sh
.venv/bin/frieren-controller dashboard
.venv/bin/frieren-controller list --scope user --kind timer
.venv/bin/frieren-controller quiet status
```

`frieren-controller --help` lists available read and change operations. MCP clients should launch `frieren-controller mcp` over stdio from the environment where the package was installed.

## Security and permissions

The local API accepts connections from the current user and is not a network server. Service names, protected services, Quiet operations, and dashboard module definitions are validated. Dashboard modules are data and are not evaluated as code.

System service changes use systemd's PolicyKit interaction. The application runs with the current user's privileges. The job editor can save systemd user service definitions and crontab entries; those jobs may execute commands as that user when their schedules run. MCP access has the same permissions as the local user. Connect only trusted clients and review any job definition before saving it.

Audit records omit job command bodies. Local notes, settings, audit records, and job backups are stored in `~/.local/state/frieren-os-controller` (`XDG_STATE_HOME` is not consulted). Edited user units are written to `$XDG_CONFIG_HOME/systemd/user` (default `~/.config/systemd/user`).

## Tests and style checks

The tests use isolated fixtures and mocked system interactions. Ruff is not a project dependency, so install it separately. Run the checks from a clean checkout:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/pip install ruff
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

`tests/test_smoke.py` runs the real CLI, the local socket API, the `mcp` stdio server (as a subprocess), the job editor, and `packaging/install-user.py`. Everything runs against temporary `HOME`/XDG directories with `systemctl` and Quiet replaced by fakes. The wallpaper tests in `tests/test_appearance.py` need PyGObject with GdkPixbuf. The GUI smoke test opens the GTK 3 window only when an X display is available and is skipped otherwise. Run it headless with `xvfb-run -a .venv/bin/python -m unittest discover -s tests -v`. One job test calls the real `systemd-analyze --user verify` and is skipped when no systemd user manager is reachable, for example in containers.

These checks do not verify changes against a live systemd manager, KDE session, Quiet service, or cron daemon. The project code and new neutral icon are licensed under MIT; see [LICENSE](LICENSE). GTK, KDE, Python dependencies, and external integrations remain under their upstream licenses. The current application name and identifiers retain the project's existing Frieren branding; the MIT license does not grant rights to third-party names or marks.
