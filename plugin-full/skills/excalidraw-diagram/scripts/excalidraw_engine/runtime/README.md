# Vendored Excalidraw runtime

The offline viewer inlines these files, so a generated `.html` renders with no network
at all — the promise `SYS-DIAGRAM-001` makes ("a viewer that opens with no install and
no network"). They are third-party build outputs, copied as published, with exactly one edit — recorded
below — and never touched otherwise.

| File | Source | Version | Licence |
|---|---|---|---|
| `excalidraw.production.min.js` | `unpkg.com/@excalidraw/excalidraw@0.17.6/dist/` | 0.17.6 | MIT |
| `react.production.min.js` | `unpkg.com/react@18.2.0/umd/` | 18.2.0 | MIT |
| `react-dom.production.min.js` | `unpkg.com/react-dom@18.2.0/umd/` | 18.2.0 | MIT |
| `Virgil.woff2`, `Cascadia.woff2`, `Assistant-*.woff2` | `…/@excalidraw/excalidraw@0.17.6/dist/excalidraw-assets/` | 0.17.6 | see below |

`excalidraw.production.min.js.LICENSE.txt` is the bundle's own notice file, copied with it.
Virgil ships with Excalidraw; Cascadia Code is SIL OFL 1.1; Assistant is SIL OFL 1.1.

**The one edit.** `VITE_APP_FIREBASE_CONFIG` is replaced by `'{}'` in
`excalidraw.production.min.js` (three occurrences). The published bundle carries
Excalidraw's own Firebase web config for the `excalidraw-room-persistence` project, which
drives *their* live-collaboration backend. This viewer never starts a collaboration
session, so the config is dead weight here — and its `apiKey` field is a Google API key by
format, which every secret scanner in existence flags the moment it lands in a public
repository. Removing it keeps the scanners honest and costs nothing. Re-apply this edit
after any version bump; the check is `grep -c AIzaSy excalidraw.production.min.js` → 0.

**What is deliberately absent.** `excalidraw-assets/vendor-*.js` (2.96 MB) is a lazily
imported chunk. Rendering, editing, and image export do not touch it — a scene renders
identically without it, which is why the vendored set is 1.6 MB rather than 4.5 MB. The
features that do import it (the Mermaid-to-Excalidraw dialog, chiefly) fail in an offline
page; `--cdn` emits a viewer that loads the full runtime from unpkg instead.

**Upgrading.** Bump the version in `assets.py`, re-download all of the above from the
matching `dist/`, re-run the suite, and re-check that a hand-drawn scene still renders
with its fonts (`Virgil`) from the inlined data URIs — the font URLs resolve through
`window.EXCALIDRAW_ASSET_PATH`, which the offline page sets to `""` on purpose.
