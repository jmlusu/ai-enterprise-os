# Session Bridge & Telemetry-on-Close Sequence

Sprint 5.5 P1–P4: every OpenCode desktop session loads the constitution/sprint
state on open (P1), reports activity to the dashboard on close (P2), can be
opened from the dashboard ("continue in OpenCode", P3), and can submit a
generated artifact for review (P4). Everything is fail-open — an abrupt close
loses at most the in-flight checkpoint.

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant OC as OpenCode desktop
    participant PLUGIN as session-telemetry.ts plugin<br/>(machine-local, gitignored)
    participant API as ai-company serve<br/>(FastAPI 127.0.0.1:8000)
    participant G as WriteGuard
    participant SVC as RuntimeFacade +<br/>telemetry/sessions.py
    participant LOG as runtime/<br/>session_telemetry.jsonl
    participant DASH as Dashboard (/telemetry)

    Note over Op,OC: P1 — session bridge (session start)
    Op->>OC: opencode (repo root, new session)
    OC->>OC: AGENTS.md auto-loads → reads<br/>.ai-company/constitution/rules.md<br/>.ai-company/state/current_sprint.yaml<br/>.ai/current-work.md (no manual step)

    Note over OC,PLUGIN: P2 — activity capture during session
    OC->>PLUGIN: session.updated · message.updated<br/>tool.execute.after (deduped via Sets)
    PLUGIN->>PLUGIN: roll up tokens/cost, tool usage,<br/>commands run (dirty flag)

    Note over OC,LOG: P2 — flush on close
    Op->>OC: session.idle / session.deleted / shutdown
    OC->>PLUGIN: flush if dirty
    PLUGIN->>API: GET /api/write-csrf
    API-->>PLUGIN: {"csrf_token": "<per-run>"}
    PLUGIN->>API: POST /api/telemetry/session<br/>X-CSRF-Token: <csrf><br/>body: session checkpoints + counters
    API->>G: guard("telemetry.session.persist")<br/>NOT high-impact · no reason
    alt Loopback & token not required
        G-->>API: pass (token optional, validated if present)
    end
    API->>SVC: session_telemetry_record(...)
    SVC->>LOG: append checkpoint (fail-open,<br/>strictly increasing timestamps, prune cap)
    API-->>PLUGIN: 200 {"success": true}
    PLUGIN-->>OC: flush done (one 403 retry,<br/>throttled error logs)

    Note over API,DASH: Sessions panel (read path)
    API->>SVC: session_telemetry_summary(limit)
    SVC->>LOG: read tail
    SVC-->>DASH: newest-per-session dedupe · totals<br/>by_model · by_end_reason
    DASH-->>DASH: /telemetry OpenCode Sessions panel

    Note over Op,DASH: P4 — desktop → submit for review
    Op->>OC: "submit generated artifact for review"
    OC->>API: POST /api/review/submit<br/>X-CSRF-Token (source="desktop")
    API->>G: guard("review.submit") · not high-impact
    API->>SVC: review_submit(title, description,<br/>artifact_paths, session_id, model)
    SVC->>SVC: create "review" decision<br/>(requester = session_id, tags ["review","desktop"])
    SVC-->>API: {"review_link": "/decisions?focus=<id>"}
    API-->>OC: review_link
    OC-->>Op: hand review_link to operator
    Op->>DASH: open review_link → /decisions?focus=<id><br/>(scrolls to + highlights the decision)
```

## D5 contribution (P5)

The action share numerator counts `gui` (guarded dashboard writes),
`desktop` (explicit records such as `review.submit`), and the OpenCode
**session activity** — commands run + tool calls at the newest checkpoint per
session (`telemetry/actions.py::_desktop_session_actions`). The
`telemetry.session.persist` plumbing call is **excluded** (`source=None`), so
infrastructure writes never inflate the metric.

## References

- `AGENTS.md` §"Session bridge (P1)" and §"Submit for review (Sprint 5.5 P4)"
- `.opencode/plugins/session-telemetry.ts` (machine-local, gitignored)
- `src/ai_company/telemetry/sessions.py` — server-side source of truth
- `src/ai_company/api/operational_endpoints.py` — `POST /api/telemetry/session`
  and `POST /api/review/submit`
- `src/ai_company/telemetry/actions.py` — `action_share_summary()` D5 math
