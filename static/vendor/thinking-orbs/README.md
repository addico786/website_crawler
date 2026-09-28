# thinking-orbs 0.3.2 (vendored, React-free engine only)

- Source: npm package `thinking-orbs@0.3.2` (https://www.npmjs.com/package/thinking-orbs,
  repo https://github.com/Jakubantalik/Libraries.dev, `packages/thinking-orbs`).
- Author: Jakub Antalik. Licence: MIT (see `LICENSE`, copied from the package).
- Files copied unchanged from the package's `dist/`:
  - `engine.es.js` (the `thinking-orbs/engine` entry point)
  - `index-B8WsUNf5.js` (the shared chunk it imports; it imports nothing itself,
    in particular not React)
- sha256:
  - engine.es.js       e7dc939abf68eb2890f1a3ed49f129185e04ca690dee905b05820ed27adbf209
  - index-B8WsUNf5.js  4b43963f6409d310b9d80e592d4fb0f1435884a59d0c252f6f1b75926c09b949
- Used by `static/orbs.js`, which mirrors the canvas setup and frame loop of the
  package's React `ThinkingOrb` component. Served locally; nothing loads from the
  internet.
