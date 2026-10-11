# Security and data boundaries

Grimoire runs as the current user and has no network listener or telemetry.
Its local activation socket is restricted to that user. It reads explicitly
configured task records and local CLI event files. It does not run commands from
those records. Skin packs contain image data and metadata, never executable plugins.

The application is not an isolation boundary against software already running as
the same user. Only choose directories and character packs you intend to read.
Document/image opening uses either the native text viewer or the desktop's file
association; executable and desktop-launcher file types are excluded.

If a public repository is created, report a vulnerability privately through its
security advisory facility. Until then, contact the project maintainer without
posting private task records, credentials or full logs in a public issue.
