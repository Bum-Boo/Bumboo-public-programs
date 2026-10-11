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
- GTK 4 and PyGObject provided by the operating system. PyGObject is not installed by this project's Python dependency list.
- systemd for service and timer controls.
- KDE Plasma and its command-line tools for KDE appearance, workspace, and desktop integrations.
- `cronie` only if you use cron editing. The application does not install or start it.

Python package dependencies are declared in `pyproject.toml`.

## Install

After installing GTK 4 and PyGObject using your distribution's package manager:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/frieren-controller --help
```

The user installer at `packaging/install-user.py` writes a systemd user service, desktop launcher, icon, and Plasma widget, then enables and starts the service. Review it before running: it changes the current user's application and service setup. It does not install system packages. No installer or service command is run by the unit test suite.

## Use

```sh
.venv/bin/frieren-controller dashboard
.venv/bin/frieren-controller list --scope user --kind timer
.venv/bin/frieren-controller quiet status
```

`frieren-controller --help` lists available read and change operations. MCP clients should launch `frieren-controller mcp` over stdio from the environment where the package was installed.

## Security and permissions

The local API accepts connections from the current user and is not a network server. Service names, protected services, Quiet operations, and dashboard module definitions are validated. Dashboard modules are data and are not evaluated as code.

System service changes use systemd's PolicyKit interaction. The application runs with the current user's privileges. The job editor can save systemd user service definitions and crontab entries; those jobs may execute commands as that user when their schedules run. MCP access has the same permissions as the local user. Connect only trusted clients and review any job definition before saving it.

Audit records omit job command bodies. Local notes, settings, and logs are stored under the user's XDG state/config paths.

## Tests and style checks

The existing tests use isolated fixtures and mocked system interactions. Run them from a clean checkout:

```sh
.venv/bin/python -m unittest discover -s tests -v
ruff check .
ruff format --check .
```

These checks do not verify changes against a live systemd manager, KDE session, Quiet service, or cron daemon. The project code and new neutral icon are licensed under MIT; see [LICENSE](LICENSE). GTK, KDE, Python dependencies, and external integrations remain under their upstream licenses. The current application name and identifiers retain the project's existing Frieren branding; the MIT license does not grant rights to third-party names or marks.
