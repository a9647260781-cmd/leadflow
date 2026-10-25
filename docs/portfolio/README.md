# LeadFlow portfolio images

Curated screenshots of the real local application for the portfolio case. Primary README hero: `images/public-desktop.jpg`.

| File | Caption | Route / state | Viewport |
| --- | --- | --- | --- |
| `images/public-desktop.jpg` | Public repair request form; empty and ready to use | `/` | 1440 × 1024 |
| `images/public-mobile-390x844.jpg` | Mobile public form, exact narrow viewport | `/` | 390 × 844 |
| `images/manager-demo-list.jpg` | Manager list filtered by the synthetic `+7 000 000-00-` number prefix; exactly six deterministic `Демо · …` rows | `/manager` | 1440 × 1024 |
| `images/lead-manual-extraction.jpg` | Lead detail with service, budget, timeframe and evidence quotes saved manually | `/manager/leads/:id` | 1440 × 1024 |
| `images/lead-not-configured-mobile-390x844.jpg` | Honest no-key state with manual entry and connection-check actions | `/manager/leads/:id` | 390 × 844 |

## Provenance

- Captured on 2026-10-25 from the real application at `http://127.0.0.1:8080` in Chrome through the authorized browser session, DPR 1.
- The manager views use the actual shared PostgreSQL and the six deterministic synthetic demo rows created by the project seeder. Names begin with `Демо ·`, and phone numbers use the reserved-looking `+7 000 …` demo pattern.
- The manual extraction screenshot is seeded manual data, **not** a live Yandex AI Studio result. The `not_configured` screenshot is the actual missing-credential state.
- Yandex AI Studio and Telegram were not connected during capture. No external AI or Telegram call was made.
- No real PII, secrets, `.env` values or runtime credentials are visible.
- These are direct browser viewport captures saved as JPEG (quality 86–88). There is no ImageGen replacement, UI retouching or compositing; the mobile no-key detail uses only a deliberate page scroll to frame the relevant section.
