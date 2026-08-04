# Generate Dispatch + Local-Model Fallback (R4 / D9)

Every `generate` surface (frozen CLI `ai-company generate <target>`, dashboard
`/generate`, desktop session) funnels through one shared dispatcher:
`services/generate_dispatch.py`. The primary provider is the local `opencode`
binary (the frozen CLI contract, ADR 0006). When OpenCode dispatch fails —
binary missing from PATH, startup failure (`OSError`), or non-zero exit — the
run falls back to a local/free model via the `ollama` CLI (decision D4 default
`ollama/llama3.1:8b`, decision D9) unless fallback is disabled. The outcome
reports **which** provider and model actually ran, keeping run records and
telemetry honest (R5).

```mermaid
flowchart TB
    subgraph ENTRY["Entry points"]
        CLI["CLI: ai-company generate &lt;target&gt;"]
        DASH["Dashboard: POST /api/generate<br/>(WriteGuard + audit)"]
        PIPE["Pipeline 'generation' stage"]
    end

    RUNNER["GenerateRunner (services/generate_runner.py)<br/>thread-safe · one daemon worker per run<br/>streams child output → runtime/generate_logs/&lt;run_id&gt;.log"]
    CMAP["Command map (config/generation/commands.yaml)<br/>target → prompt_file · agent · model"]
    RENDER["Render mapped prompt file<br/>(company-registry interpolation)"]

    FALLBACK_CFG["config/runtime/model_fallback.yaml<br/>fallback: enabled · provider=ollama<br/>model=ollama/llama3.1:8b"]

    subgraph DISPATCH["dispatch_generate(agent, model, prompt_path, ...)"]
        P1["PRIMARY: opencode<br/>shutil.which('opencode')"]
        E1["opencode not found on PATH"]
        P2["opencode run --file &lt;prompt&gt;<br/>--agent &lt;agent&gt; --model &lt;model&gt;<br/>Execute the attached prompt..."]
        E2["OSError → failed to start opencode"]
        E3["exit code ≠ 0"]
        GATE{"last attempt exit_code == 0?"}
        F1["FALLBACK (enabled): ollama<br/>shutil.which('ollama')"]
        F2["model = fallback_model.split('/')[-1]<br/>ollama run llama3.1:8b<br/>(stdin = prompt file)"]
        E4["fallback unavailable: 'ollama' not on PATH"]
        E5["OSError → failed to start ollama"]
        E6["exit code ≠ 0"]
    end

    OUTCOME["DispatchOutcome<br/>provider · model · exit_code · attempts[]<br/>used_fallback = provider != 'opencode'"]
    RECORD["GenerateRun record<br/>provider/model = what actually ran (R5)<br/>runtime/generate_runs.jsonl (append-only)"]

    ENTRY --> RUNNER
    RUNNER --> CMAP
    RUNNER --> RENDER
    FALLBACK_CFG --> DISPATCH
    RUNNER --> DISPATCH
    RENDER --> P1
    P1 -- "found" --> P2
    P2 -- "rc == 0" --> GATE
    P1 -- "missing" --> E1 --> GATE
    P2 -- "OSError" --> E2 --> GATE
    P2 -- "rc ≠ 0" --> E3 --> GATE
    GATE -- "no (attempt failed)" --> F1
    GATE -- "yes → success" --> OUTCOME
    F1 -- "found" --> F2
    F1 -- "missing" --> E4 --> OUTCOME
    F2 -- "OSError" --> E5 --> OUTCOME
    F2 -- "rc ≠ 0" --> E6 --> OUTCOME
    F2 -- "rc == 0" --> OUTCOME
    OUTCOME --> RECORD

    classDef entry fill:#17202a,stroke:#7f8c8d,stroke-width:2px,color:#fff
    classDef eng fill:#6e2c00,stroke:#e67e22,stroke-width:2px,color:#fff
    classDef primary fill:#1a4a6a,stroke:#3498db,stroke-width:2px,color:#fff
    classDef fallback fill:#5b2c6f,stroke:#9b59b6,stroke-width:2px,color:#fff
    classDef gate fill:#641e16,stroke:#e74c3c,stroke-width:2px,color:#fff
    classDef out fill:#0e4d45,stroke:#1abc9c,stroke-width:2px,color:#fff

    class CLI,DASH,PIPE entry
    class RUNNER,CMAP,RENDER,FALLBACK_CFG eng
    class P1,P2 primary
    class F1,F2 fallback
    class GATE,E1,E2,E3,E4,E5,E6 gate
    class OUTCOME,RECORD out
```

## Dispatch decision table

| Primary attempt | Fallback enabled | Fallback present | Result (`DispatchOutcome`) |
|---|---|---|---|
| exit_code 0 | — | — | `provider="opencode"`, success (no fallback attempted) |
| not on PATH | no | — | `provider="opencode"`, `exit_code=None`, error "opencode not found on PATH" |
| not on PATH | yes | yes | `provider="local"`, `model="ollama/llama3.1:8b"` — outcome reports the **fallback** model |
| not on PATH | yes | no | `provider="local"`, `exit_code=None`, error "fallback unavailable: 'ollama' not found on PATH" |
| startup `OSError` | yes | yes | `provider="local"`, fallback ran |
| non-zero exit | yes | yes | `provider="local"`, fallback ran (append-mode log keeps both attempts) |
| non-zero exit (last that ran) | yes | no | `provider="local"`, `exit_code` = last exit code, `used_fallback=True` |

## Failure contracts

- **Cancellation:** `GenerateRunner.cancel()` terminates the live child via
  `register_proc`; run recorded `cancelled`.
- **Restart replay:** runs still `queued`/`running` at boot are replayed from
  history as `failed` with `interrupted by restart` (the worker thread is gone —
  truthful state).
- **Logs:** `_run_process` streams merged stdout+stderr to the run log; a
  fallback run **appends** (never truncates) so the failed primary's output
  stays in the same honest history.
- **Fallback disabled + opencode missing:** fails fast with a descriptive error
  (no thread), mirroring the frozen CLI.

## References

- `src/ai_company/services/generate_dispatch.py` — `FallbackConfig`,
  `DispatchAttempt`, `DispatchOutcome`, `dispatch_generate()`, `_run_process()`
- `src/ai_company/services/generate_runner.py` — `GenerateRunner` run lifecycle,
  history, log streaming, `_execute()`
- `config/runtime/model_fallback.yaml` — fallback `enabled/provider/model`
- `docs/dashboard/initiative.md` — risk R4 `[MITIGATED]`, decision D9
- `src/ai_company/cli/commands/generate.py` — frozen CLI wiring (surface
  unchanged, R8 gate)
