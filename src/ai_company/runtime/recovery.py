"""Recovery — applies configured RecoveryPolicies to failed components.

A recovery policy (from ``config/runtime/recovery.yaml``) declares the
ordered ``actions`` to take when a component fails:

* ``restart`` — restart the component (process restart via the
  ProcessManager, or engine re-init via a registered factory).
* ``reload_state`` — reload persisted state for the component.
* ``isolate`` — mark the component failed and stop monitoring it.
* ``escalate`` — report the failure on the event bus so higher-level
  supervision can intervene.

Actions are attempted in order; the first success ends the sequence.
Recovery results are recorded as :class:`RecoveryResult` instances.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ai_company.runtime.models import (
    RecoveryError,
    RecoveryPolicy,
    RecoveryResult,
    publish_runtime_event,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RecoveryManager:
    """Executes recovery policies for failed runtime components.

    Args:
        config: The ``recovery`` config section dict.
        process_manager: Optional ProcessManager for ``restart`` actions.
        component_factory: Optional callable ``(name) -> component`` used to
            re-create components whose factory is registered.
        event_bus: Optional event bus for ``escalate`` actions.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        process_manager: Any | None = None,
        component_factory: Callable[[str], Any] | None = None,
        event_bus: Any | None = None,
        is_engine: Callable[[str], bool] | None = None,
    ) -> None:
        self.config = config or {}
        self.default_max_attempts = int(self.config.get("default_max_attempts", 3))
        self.process_manager = process_manager
        self.component_factory = component_factory
        self.event_bus = event_bus
        # Optional predicate used to fall back to the "engine"/"process"
        # category policies for components without an exact-name policy.
        self.is_engine = is_engine
        self._policies: dict[str, RecoveryPolicy] = {}
        self._attempts: dict[str, int] = {}
        self._results: dict[str, list[RecoveryResult]] = {}
        self._factories: dict[str, Callable[[], Any]] = {}
        self._lock = threading.Lock()
        self._parse_policies(self.config.get("policies", {}))

    def _parse_policies(self, raw: dict[str, Any]) -> None:
        for name, spec in raw.items():
            if isinstance(spec, RecoveryPolicy):
                self._policies[name] = spec
            elif isinstance(spec, dict):
                self._policies[name] = RecoveryPolicy.model_validate(
                    {"name": name, **spec}
                )

    def register_factory(self, name: str, factory: Callable[[], Any]) -> None:
        """Register a factory used to re-create a component on restart."""
        with self._lock:
            self._factories[name] = factory

    def policy_for(self, component: str) -> RecoveryPolicy | None:
        """Return the recovery policy matching a component name.

        Resolution order:
        1. Exact component-name match.
        2. Suffix wildcard (``name*``) match.
        3. Category fallback: the ``engine`` policy for registered
           engines, and the ``process`` policy for managed processes.
        """
        if component in self._policies:
            return self._policies[component]
        for pattern, policy in self._policies.items():
            if pattern.endswith("*") and component.startswith(pattern[:-1]):
                return policy
        if self.is_engine is not None and self.is_engine(component):
            return self._policies.get("engine")
        if self.process_manager is not None:
            if self.process_manager.get_optional(component) is not None:
                return self._policies.get("process")
        return None

    def attempts(self, component: str) -> int:
        return self._attempts.get(component, 0)

    def results(self, component: str) -> list[RecoveryResult]:
        return list(self._results.get(component, []))

    def reset(self, component: str) -> None:
        """Reset attempt tracking (e.g. after a stable healthy period)."""
        with self._lock:
            self._attempts[component] = 0

    # ── Recovery ───────────────────────────────────────────────────

    def recover(self, component: str, reason: str = "unknown") -> RecoveryResult:
        """Apply the recovery policy for a failed component.

        Returns:
            The RecoveryResult describing what was done.
        """
        with self._lock:
            self._attempts[component] = self._attempts.get(component, 0) + 1
            attempts = self._attempts[component]
        policy = self.policy_for(component)
        if policy is None or not policy.enabled:
            return RecoveryResult(
                component=component,
                success=False,
                attempts=attempts,
                message="No enabled recovery policy configured",
                recovered_at=_utcnow(),
            )
        max_attempts = (
            int(policy.max_attempts)
            if policy.max_attempts is not None
            else self.default_max_attempts
        )
        logger.warning(
            "Recovering %s (attempt %d/%d, actions=%s, reason=%s)",
            component,
            attempts,
            max_attempts,
            policy.actions,
            reason,
        )
        if attempts > max_attempts:
            result = RecoveryResult(
                component=component,
                success=False,
                attempts=attempts,
                message=(
                    f"Max attempts ({max_attempts}) exceeded; "
                    f"actions attempted: {', '.join(policy.actions)}"
                ),
                recovered_at=_utcnow(),
            )
        else:
            result = self._execute(component, policy, reason, attempts)
        with self._lock:
            self._results.setdefault(component, []).append(result)
        return result

    def _execute(
        self,
        component: str,
        policy: RecoveryPolicy,
        reason: str,
        attempts: int,
    ) -> RecoveryResult:
        taken: list[str] = []
        for action in policy.actions:
            try:
                if action == "restart":
                    self._restart(component, policy)
                elif action == "reload_state":
                    self._reload_state(component)
                elif action == "isolate":
                    self._isolate(component, policy)
                elif action == "escalate":
                    self._escalate(component, policy, reason)
                else:
                    raise RecoveryError(f"Unknown recovery action: {action}")
            except Exception as exc:
                logger.warning(
                    "Recovery action %s failed for %s: %s",
                    action,
                    component,
                    exc,
                )
                continue
            taken.append(action)
            if action != "escalate":
                break  # first successful concrete action ends the sequence
        if taken:
            return RecoveryResult(
                component=component,
                success=True,
                actions_taken=taken,
                attempts=attempts,
                message=f"Recovery succeeded via: {', '.join(taken)}",
                recovered_at=_utcnow(),
            )
        return RecoveryResult(
            component=component,
            success=False,
            attempts=attempts,
            message=(
                f"All recovery actions failed for {component}: "
                f"{', '.join(policy.actions)}"
            ),
            recovered_at=_utcnow(),
        )

    def _restart(self, component: str, policy: RecoveryPolicy) -> None:
        if self.process_manager is not None:
            optional = self.process_manager.get_optional(component)
            if optional is not None:
                self.process_manager.restart(component)
                return
        factory = self._factories.get(component)
        if factory is not None:
            factory()
            return
        if self.component_factory is not None:
            self.component_factory(component)
            return
        raise RecoveryError(
            f"No restart mechanism for {component} "
            "(no process record, factory, or component factory)"
        )

    def _reload_state(self, component: str) -> None:
        if self.component_factory is None:
            raise RecoveryError(
                f"No state reload mechanism for {component} "
                "(component_factory not configured)"
            )
        self.component_factory(component)

    def _isolate(self, component: str, policy: RecoveryPolicy) -> None:
        if self.process_manager is not None:
            optional = self.process_manager.get_optional(component)
            if optional is not None:
                self.process_manager.stop(component)
                logger.warning("Component %s isolated from runtime", component)
                return
        # Nothing was actually isolated — report failure so the supervisor
        # performs its own isolation (unregister monitoring) and the engine
        # is marked failed instead of falsely "recovered via isolate".
        raise RecoveryError(
            f"No process record for {component}; nothing to isolate "
            "(supervisor isolation not wired to RecoveryManager)"
        )

    def _escalate(self, component: str, policy: RecoveryPolicy, reason: str) -> None:
        if self.event_bus is None:
            raise RecoveryError("No event bus available for escalation")
        publish_runtime_event(
            self.event_bus,
            "runtime.component_failed",
            {
                "component": component,
                "reason": reason,
                "actions": policy.actions,
            },
            source="runtime.recovery",
        )

    # ── Inspection ─────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "policies": list(self._policies),
                "attempts": dict(self._attempts),
                "results": {
                    component: [
                        {
                            "success": r.success,
                            "actions_taken": r.actions_taken,
                            "message": r.message,
                        }
                        for r in results
                    ]
                    for component, results in self._results.items()
                },
            }
