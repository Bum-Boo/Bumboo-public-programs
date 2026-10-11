# Bumboo Public Programs

Ten independent source projects extracted from personal development work. Each folder has its own README, license, dependencies and checks. Install one project at a time; there is no root-level application or shared runtime. Private operational data, account credentials, customer records, music, borrowed character sprites and model weights are excluded.

| Project | Purpose | Start here |
| --- | --- | --- |
| Grimoire Companion | Native Linux companion for agent status and audio visualization | [README](grimoire-companion/README.md) |
| Frieren OS Controller | Linux GTK, CLI and MCP controls for desktop services and jobs | [README](frieren-os-controller/README.md) |
| Emergent Life Lab | Standalone cellular automata laboratory | [README](emergent-life-lab/README.md) |
| Procedural Soundscape | WebGL2 visuals driven by generated synthetic signals | [README](procedural-soundscape/README.md) |
| Agent Workflow | Markdown project context, task leases and verification receipts | [README](agent-workflow/README.md) |
| Hermes Pet | Read-only browser and terminal status companion with generic emoji | [README](hermes-pet/README.md) |
| AID VFX Toolkit | Experimental local VFX commands and Adobe scripts | [README](aid-vfx-toolkit/README.md) |
| Typecast Shorts Toolkit | Caption timing core and experimental Adobe panels | [README](typecast-shorts-toolkit/README.md) |
| Quiet Desktop | Quiet-mode desktop utility for supported MSI hardware | [README](quiet-desktop/README.md) |
| Quiet Controller Plugin | Headless power and thermal backend for supported MSI hardware | [README](quiet-controller-plugin/README.md) |

## Use and checks

Change into the chosen folder and follow its README. The two web demos use `npm ci` and `npm run check`; the Typecast package uses `npm ci` and `npm test`. Python projects document their own environment and test command. System integration tools may change desktop services, saved jobs or power settings when explicitly installed/run; their tests use temporary state and mocks.

Desktop distributions, hardware, Adobe hosts and model downloads have different support limits. A passing syntax/core test does not establish Adobe host behavior or hardware compatibility. VFX model inference and Adobe panel runtime remain unverified by this source packaging pass. Model weights and user footage must be acquired separately under their own terms. CI files under `ci/` are reference templates and are not active GitHub workflows.

MIT covers user-authored source and original synthetic samples, with project-specific license and third-party notices retained in each folder. External dependencies and user-provided assets retain their own terms. No hosting, production deployment or automatic system installation is performed by this repository.
