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

Open the loopback URL printed by Vite (by default `http://127.0.0.1:5173/`). Use `npm run build` to create the static site in `dist/`, then `npm run preview` to serve that build locally (by default `http://127.0.0.1:4173/`). `npm run preview` serves the existing `dist/` folder, so run `npm run build` first.

## Controls and data

The lab supports Conway Life, HighLife, Seeds, Day & Night, Diamoeba, Replicator, Brian's Brain and WireWorld. It can share a pattern in the URL hash or copy it as JSON. Sound is generated with Web Audio only after you turn it on; no audio recording or music file is loaded.

## Development checks

```sh
npm ci
npm run check
```

The checks typecheck the app (`npm run typecheck`), run the tests in `tests/*.test.ts` with Node's test runner through `tsx` (`npm test`), and build the static site (`npm run build`). The tests cover every rule, every pattern preset, metrics, the share-hash/JSON encoding, and that the dev server can resolve the app's `@/src/...` imports; they do not open a browser, so canvas drawing, pointer painting, clipboard and Web Audio are not covered by them.

## License

The included application source is licensed under MIT; see [LICENSE](LICENSE). Runtime packages keep their own licenses. The interface uses system fonts and includes no third-party images, music, or sample data.
