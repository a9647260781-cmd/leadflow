# Assets: durable context

## Ownership

Generated website assets live under `frontend/public/assets/`. This role does not modify frontend source or deployment files.

## Selected public-form asset

- `frontend/public/assets/service-tools.png` is the standalone tool photograph for redesign option 1 («Сервисный бланк»).
- Canvas: `2172×724` PNG (3:1), RGBA with real transparency and soft semi-transparent contact shadows.
- Composition: a muted service-green handled adjustable wrench enters from the left and points right; one bolt seated in a nut, one separate nut, and one loose bolt sit to the right of the wrench head.
- Intended rendering: `object-fit: contain`, anchored left/bottom. The frontend target is roughly `680×230` on desktop and `358×145` on mobile.
- The built-in ImageGen output is preserved at `C:\Users\Maboy\.codex\generated_images\01a16e62-37c1-71d3-aad2-0cf07ce5a48b\exec-473ce81a-d60a-4088-a24b-257f040edc9b.png`.

## Verification

- PNG header reports color type 6 (RGBA).
- Alpha scan: 1,023,905 fully transparent pixels; 547,751 partially transparent pixels; 872 fully opaque pixels. This confirms transparent empty space and anti-aliased/contact-shadow edges.
- SHA-256: `736C6B1F45EC1D55218172EB12EA7CD7F97BE5A4E04BDD9BF1056B9CA23D59F7`.
