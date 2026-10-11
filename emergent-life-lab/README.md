# Emergent Life Lab

A standalone cellular automata playground. Choose a rule and pattern, watch generations evolve, and inspect population and structure metrics. The app runs in your browser and does not send simulation data to a service.

## Requirements

- Node.js 20.19+ (or 22.12+)
- A modern browser

## Run locally

```sh
npm ci
npm run dev
```

Open the loopback URL printed by Vite. Use `npm run build` to create the static site in `dist/`, or `npm run preview` to inspect that build locally.

## Controls and data

The lab supports Conway Life, HighLife, Seeds, Day & Night, Diamoeba, Replicator, Brian's Brain and WireWorld. It can share a pattern in the URL hash or copy it as JSON. Sound is generated with Web Audio only after you turn it on; no audio recording or music file is loaded.

## Development checks

```sh
npm run check
```

The checks typecheck the app, exercise the automata and state-encoding logic with Node's test runner, and build the static site.

## License

The included application source is licensed under MIT; see [LICENSE](LICENSE). Runtime packages keep their own licenses. The interface uses system fonts and includes no third-party images, music, or sample data.
