# Procedural Soundscape

An isolated WebGL2 colour-field demo driven by generated synthetic rhythm and frequency-band values. It does not play audio, access a microphone, read a music file, request album art, or fetch track profiles.

## Requirements

- Node.js 20.19+ (or 22.12+)
- A modern browser with WebGL2

## Run locally

```sh
npm ci
npm run dev
```

Open the loopback URL printed by Vite. Adjust tempo and signal strength to regenerate deterministic synthetic data, choose a visual treatment, or pause/resume. `npm run build` creates a static site in `dist/`; `npm run preview` serves that build locally.

## Development checks

```sh
npm run check
```

The checks typecheck the app, exercise generated signal and driver behavior with Node's test runner, and build the static site. Rendering still requires a browser with WebGL2 for a visual check.

## License

The included application source is licensed under MIT; see [LICENSE](LICENSE). Runtime and build packages keep their own licenses. No audio, image, or sample media is included.
