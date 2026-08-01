# ADR 0007 — Supervisor self-healing: restart before isolate

Status: Accepted
Date: 2026-08-01
Deciders: Software Engineering, Cloud Architecture

## Context

The runtime's recovery loop could not actually restart engines:

1. `RecoveryManager` was constructed without a component factory and no
   per-engine factories were registered, so the `restart` recovery action
   always raised `RecoveryError`.
2. `recovery.yaml` policies are keyed by category (`engine`, `process`),
   but `policy_for()` only matched exact names or `name*` suffixes — real
   engines (`memory`, `decision`, ...) matched **no** policy and were
   isolated on the first failure.
3. The `isolate` action returned success even when nothing was isolated
   (no process record), so engines were falsely "recovered via isolate"
   and kept failing until max attempts.

Observed result: every engine `failed`/`unhealthy` with
`restart_count: 0` in `runtime/runtime_state.json`.

## Decision

1. `RuntimeEngine.register_engine` registers a restart factory per engine;
   the factory calls `instance.restart()` when available and re-admits the
   engine with a fresh heartbeat window (`_restart_engine`).
2. `RecoveryManager.policy_for` falls back to the `engine`/`process`
   category policies for registered engines/processes (via `is_engine`).
3. `RecoveryManager._isolate` raises when there is no process record to
   stop, so a fake isolate no longer counts as recovery; the supervisor
   then performs real isolation (unregister monitoring).
4. The supervisor also isolates when recovery succeeded via an `isolate`
   action (the component is dead).

## Consequences

- Heartbeat timeouts now trigger real restart attempts (up to the policy
  max) before isolation.
- Engines that recover stay RUNNING/HEALTHY; genuinely dead engines are
  isolated after max attempts as designed.
- Covered by new unit tests in `tests/unit/runtime/test_recovery.py` and
  `tests/unit/runtime/test_engine.py`.
