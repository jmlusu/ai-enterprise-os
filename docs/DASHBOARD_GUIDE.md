# AI Enterprise OS — Dashboard Guide

How to start, access, and use the web dashboard (FastAPI + Jinja2/htmx,
ADR 0002 / ADR 0008 / ADR 0009 / ADR 0010). The dashboard is the visual
operator surface over the runtime: read-only by default, with guarded
write actions (token + CSRF + audit) where they are needed.

The same data is available from the CLI — see
[docs/USER_GUIDE.md](USER_GUIDE.md) — and from the REST API (see
[§8 REST API](#8-rest-api)).

---

## 1. Start the dashboard

### 1.1 Quick start (default)

```powershell
uv run ai-company serve
```

This boots the runtime if needed (11-step startup sequence) and starts the
API server. You will see:

```
Dashboard API: http://127.0.0.1:8000/
Write auth (ADR 0010): token optional on loopback, required on non-loopback hosts; CSRF via GET /api/write-csrf -> X-CSRF-Token header
```

Open <http://127.0.0.1:8000/> in your browser. The process stays in the
foreground — press **Ctrl-C** to stop it gracefully (the runtime is shut
down cleanly on exit).

### 1.2 Options

| Option | Default | Purpose |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address. Loopback-only by default (security baseline R9). |
| `--port` | `8000` | Listen port. Change it if 8000 is busy. |
| `--config-dir` | `config` | Directory containing the `config/runtime/*.yaml` files. |
| `--hash-at-rest` | off | Store the write token as a SHA-256 digest instead of plaintext. |
| `--require-loopback-token` | off | Demand a valid write token even on loopback. Non-loopback hosts always require it. |

Examples:

```powershell
uv run ai-company serve --port 9000
uv run ai-company serve --require-loopback-token --hash-at-rest
```

> **Security model (ADR 0010).** The server only accepts loopback `Host`
> headers (`127.0.0.1`, `localhost`, `::1`) — a DNS-rebinding defense.
> If you bind to a non-loopback address, every write endpoint *fails
> closed* without a valid bearer token.

### 1.3 Prerequisites

- Python ≥ 3.12 and `uv` — `uv sync` first (see `docs/USER_GUIDE.md` §2).
- `opencode` on `PATH` — needed for the **Generate** panel (dispatches
  generation runs) and for `ai-company doctor`. Verify with
  `uv run ai-company doctor`.

---

## 2. Dashboard pages

The sidebar groups the pages:

| Page | URL | What it shows |
|---|---|---|
| **Pulse** | `/` | Landing page: health overall (ok / degraded / unhealthy), status, engine phases, memory stats, backup age |
| **System Health** | `/health` | Full health-probe report + runtime diagnostics |
| **Telemetry** | `/telemetry` | KPI panel, model/provider usage, agent health (persisted metrics, R5) |
| **Agents** | `/agents` | Executive roster + org chart (Mermaid, rendered client-side) |
| **Generate** | `/generate` | Dispatch generation targets to OpenCode, watch live logs, cancel runs |
| **Runs & History** | `/runs` | Orchestration engine status + pipeline execution history |
| **Memory** | `/memory` | Memory entries list (read view) |
| **Write History** | `/writes` | Write-token entry, operator action buttons, audit log |
| **Decision Inbox** | `/decisions` | Create decisions, approve / reject / escalate / cancel |
| **Reports** | `/reports` | Available report types + summary + validation state |
| **Validation** | `/validation` | Validator Engine gate (5 targets) |
| **Registry & Org Graph** | `/registry` | Registry listing, graph statistics, org chart |
| **API Docs** | `/api/docs` | Swagger UI for the full REST + WebSocket contract |

Every page is server-rendered from the same facade the CLI uses (ADR 0003),
so dashboard views and CLI output stay in parity. A "last health poll" age
indicator sits in the page header — it turns yellow/red if the server stops
answering health checks.

---

## 3. Read vs. write

- **Everything is readable** without a token on loopback — health, status,
  registry, memory, reports, events, telemetry.
- **Write actions require auth** (ADR 0010): a bearer token plus a per-run
  CSRF token. The browser obtains CSRF automatically
  (`GET /api/write-csrf` → `X-CSRF-Token` header); you only ever handle the
  bearer token.
- On loopback the token is **optional by default**. It becomes mandatory
  when the server runs with `--require-loopback-token`, and it is *always*
  mandatory on non-loopback hosts (requests without it get `401`).
- Every accepted write publishes an `audit.write` event; every rejected one
  publishes `audit.write_rejected` (visible in **Write History**).

### 3.1 Set up the write token (one time)

1. **Create the token** (only needed if it does not exist yet):

   ```powershell
   uv run ai-company dashboard token create
   ```

   The plaintext value is printed **only on first creation** — store it
   somewhere safe. It is saved to `runtime/.write_token` (relative to the
   working directory). Rotating an existing token never prints the new value
   (ADR 0010 §1).

   Alternative: set the `AI_ENTERPRISE_WRITE_TOKEN` environment variable —
   it overrides the token file entirely (and `dashboard token revoke`
   refuses to delete an env-managed token).

2. **Enter it in the dashboard**: open **Write History** (`/writes`), paste
   the token into the *Write token* field, and click **Save token**. The
   token is kept in this browser only (`localStorage`, key
   `aios.write_token`).

3. **Rotate / revoke** when needed:

   ```powershell
   uv run ai-company dashboard token list    # metadata, never the value
   uv run ai-company dashboard token revoke  # invalidates all sessions
   ```

> If the server started with `--require-loopback-token` and no token
> existed, the CLI creates one and prints it at boot — paste that value
> into the Write History page before performing writes.

### 3.2 High-impact actions

Actions such as **Stop runtime**, **Restart runtime**, and orchestration
**rollback** are marked high-impact: the dashboard opens a reason dialog and
the reason is recorded in the audit event (ADR 0010 §5). Lower-risk actions
use a plain confirm dialog.

---

## 4. Operator actions available from the UI

| Action | Button / location | Endpoint |
|---|---|---|
| Start runtime | Write History | `POST /api/runtime/start` |
| Stop runtime (high-impact, reason required) | Write History | `POST /api/runtime/stop` |
| Restart runtime (high-impact, reason required) | Write History | `POST /api/runtime/restart` |
| Hot-reload config | Write History | `POST /api/runtime/reload` |
| Run validation gate | Write History | `POST /api/validate` |
| Run artifact build | Write History | `POST /api/build` |
| Dispatch a generation target | Generate | `POST /api/generate` |
| Cancel a generation run | Generate (Cancel button) | `POST /api/generate/{run_id}/cancel` |
| Create a decision | Decision Inbox | `POST /api/decisions` |
| Approve / reject / escalate / cancel | Decision Inbox | `POST /api/decisions/{id}/...` |

The **Generate** panel runs the same targets as
`ai-company generate <target>` (bootstrap, registry, company, board, exec,
dept, specialist, workflow, prompt, docs, graph). Dispatch requires
`opencode` on the server's `PATH`; live output streams to the run log.

---

## 5. Live event feed (WebSocket)

The event panel connects to `ws://127.0.0.1:8000/api/ws`. Behavior:

- **Replay on connect**: the client passes `?since=<ISO-8601 timestamp>`
  and the server replays matching persisted events before streaming live
  (deduplicated by event id).
- **Heartbeats**: the server sends a `{"kind": "ping"}` every 20 s to keep
  idle connections alive; the client auto-reconnects every 3 s on drop.
- **Auth**: on loopback the feed is open by default. On non-loopback hosts
  (or with `--require-loopback-token`) a valid token must be passed via
  `?token=` or the socket closes with code 1008.

REST fallback: `GET /api/events?since=<iso8601>&limit=<n>` returns the same
events.

---

## 6. Status vocabulary

Health is reported with a four-state vocabulary (color + text + icon —
never color alone, ADR 0009):

| State | Meaning |
|---|---|
| **ok** (green) | All checks healthy |
| **degraded** / **watch** | A system threshold crossed (CPU/memory/queue/error rate) |
| **unhealthy** / **action** | A health probe failed; the supervisor attempts recovery |
| **unknown** | No data yet / data pending |

---

## 7. Stopping the dashboard

Press **Ctrl-C** in the terminal running `ai-company serve`. The shutdown
sequence closes the event bridge, stops the metrics task, and shuts the
runtime down cleanly (`facade.close()`). You do not need a separate
`ai-company runtime stop`.

---

## 8. REST API

The JSON API is versioned, read-only-by-default surface over the same
facade. Interactive docs: `GET /api/docs` (Swagger UI) or
`GET /api/openapi.json`.

- **Index**: `GET /api` — full endpoint map + auth notes.
- **Runtime**: `/api/health`, `/api/status`, `/api/metrics`, `/api/engines`,
  `/api/diagnostics`.
- **Events**: `/api/events?since=<iso8601>&limit=<n>`; live push via
  `/api/ws`.
- **Domain reads**: `/api/registry`, `/api/executives`, `/api/org-chart`,
  `/api/memory`, `/api/graph`, `/api/reports`, `/api/validate`,
  `/api/orchestrate/status`, `/api/orchestrate/history`,
  `/api/generate/targets`, `/api/generate/runs`, `/api/decisions`,
  `/api/telemetry/metrics`, `/api/telemetry/providers`, `/api/company`.
- **Writes** (POST, guarded): see the `write` map in `GET /api` — all
  mutations require `Authorization: Bearer <token>` (where enforced) and
  `X-CSRF-Token` fetched from `GET /api/write-csrf`.

All API responses use the Pydantic runtime models as schemas (ADR 0009);
there is no parallel DTO layer in v1. Responses are JSON-only under a
`default-src 'none'` CSP — nothing executable is ever served from the API.

---

## 9. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `403 Host header not allowed` | You reached the server via a non-loopback host (e.g. machine IP or `http://0.0.0.0:8000`). Use `http://127.0.0.1:8000/` or `http://localhost:8000/`. |
| Write fails with `401` | Token missing/invalid. Create one (`ai-company dashboard token create`), save it on the Write History page, and retry. |
| Write fails with `403` (CSRF) | Per-run CSRF token mismatch — refresh the page and retry. |
| `Write token created (store it — never shown again)` but you lost it | Rotate: `ai-company dashboard token create` (the new value is *not* printed). Better: use `--require-loopback-token` and capture the value printed at boot, or manage via `AI_ENTERPRISE_WRITE_TOKEN`. |
| Port 8000 already in use | Start with `--port 9000` (or another free port) and open that URL. |
| WebSocket keeps reconnecting | Confirm you are on a loopback host; on non-loopback the socket needs `?token=<write token>`. |
| Generate dispatch fails | `opencode` is not on the server's `PATH`, or the LLM backend is down — run `uv run ai-company doctor` and check `command_map.yaml` model ids. |
| Pages show "data pending" / stale indicator | The runtime is not running or health polling failed; check the `serve` terminal and `uv run ai-company runtime health`. |
| Audit events missing from Write History | The event bus persistence may be disabled; the dashboard still fails open to `runtime/.audit.failed.jsonl` for rejected/undeliverable audits. |

---

## 10. Related documentation

- [USER_GUIDE](USER_GUIDE.md) — CLI operations, quality gates, troubleshooting
- [OPERATIONS_RUNBOOK](OPERATIONS_RUNBOOK.md) — runtime CLI daily operations
- [ADR 0009 — Dashboard API contract](adr/0009-dashboard-api-contract.md)
- [ADR 0010 — Phase 2 write auth / CSRF / audit](adr/0010-phase2-write-auth-csrf-audit.md)
- [ADR 0008 — Dashboard frontend stack](adr/0008-dashboard-frontend-stack.md)
- [ADR 0002 — Dashboard backend FastAPI](adr/0002-dashboard-backend-fastapi.md)
