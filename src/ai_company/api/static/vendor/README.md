# Vendored frontend assets

These files are downloaded, unmodified third-party libraries served
locally under the dashboard's strict CSP (`script-src 'self'` — no CDN,
no `unsafe-inline`). No build step, no Node toolchain (ADR 0008).

| File | Library | Version | Source | License |
| --- | --- | --- | --- | --- |
| `htmx.min.js` | htmx | 1.9.12 | https://unpkg.com/htmx@1.9.12/dist/htmx.min.js | BSD-2-Clause |
| `ws.js` | htmx WebSocket extension | 1.9.12 | https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/ext/ws.js | BSD-2-Clause |
| `marked.min.js` | marked | 12.0.2 | https://unpkg.com/marked@12.0.2/marked.min.js | MIT |
| `dompurify.min.js` | DOMPurify | 3.1.6 | https://unpkg.com/dompurify@3.1.6/dist/purify.min.js | Apache-2.0 / MPL-2.0 (dual) |
| `mermaid.min.js` | mermaid | 10.9.1 | https://unpkg.com/mermaid@10.9.1/dist/mermaid.min.js | MIT |

DOMPurify is used to sanitize Markdown-rendered HTML and Mermaid source
before insertion (R11). All assets are served only to loopback clients
(R9). To update, re-download from the pinned URLs, replace the file, and
update the version in this table.
