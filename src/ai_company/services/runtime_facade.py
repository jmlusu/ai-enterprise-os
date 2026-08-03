"""Runtime facade — the shared, stable surface over the runtime engine.

ADR 0003: the CLI, the dashboard API, and OpenCode prompt execution are thin
adapters; business logic lives exactly once. This facade stabilizes the
:class:`RuntimeEngine` public API so every surface asks the same questions
("is the system healthy?", "what is the status?") through one well-tested
object instead of duplicating runtime wiring per surface.

Phase 1 (WS-1.0) extends the facade with read-only methods over the domain
engines (registry, executives, memory, graph, reports, validator, diagnostics,
orchestration, generate targets). Every method is a thin adapter that mirrors
the equivalent CLI read command and returns JSON-ready dictionaries — the
dashboard API and the parity test suite consume these same methods so the two
interfaces cannot drift (risk R3).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Self

from ai_company.runtime import RuntimeEngine, create_runtime

logger = logging.getLogger(__name__)

__all__ = ["RuntimeFacade"]

#: Default relative paths mirroring the CLI read commands (parity contract).
_DEFAULT_COMPANY_DIR = Path("company")
_DEFAULT_CONFIG_COMPANY_DIR = Path("config/company")
_DEFAULT_MEMORY_CONFIG = Path("config/memory/memory.yaml")
_DEFAULT_MEMORY_STORAGE = Path("memory/store.jsonl")


def _registry_summary(reg: Any) -> dict[str, Any]:
    """Lightweight JSON summary of a loaded :class:`CompanyRegistry`."""
    return {
        "vision": reg.vision.model_dump(mode="json"),
        "departments": {
            name: {
                "roles": len(dept.roles),
                "role_titles": [r.title for r in dept.roles],
            }
            for name, dept in sorted(reg.departments.items())
        },
        "board": len(reg.board),
        "executives": len(reg.executives),
        "executive_agents": len(reg.executive_agents),
        "policies": len(reg.policies),
        "specialists": len(reg.specialists),
        "workflows": len(reg.workflows),
        "kpis": len(reg.kpis),
        "budgets": len(reg.budgets),
        "unresolved_refs": list(reg.unresolved_refs),
    }


def _registry_errors(result: Any) -> list[str]:
    """Errors from a RegistryLoadResult, or a message when unloadable."""
    errors = list(getattr(result, "errors", []) or [])
    if not errors and result is not None and getattr(result, "registry", None) is None:
        errors.append("Registry could not be loaded.")
    return errors


def _decision_from_history_entry(entry: dict[str, Any]) -> Any | None:
    """Reconstruct a :class:`Decision` from a persisted history entry.

    ``DecisionHistory._load_from_disk`` only rebuilds the raw history list, so
    the queryable index is empty after a restart. This helper rebuilds a
    :class:`Decision` (best-effort) from one JSONL entry so the approval inbox
    stays useful across restarts.
    """
    from datetime import datetime as _datetime

    from ai_company.decision.models import (
        Decision,
        DecisionCategory,
        DecisionPriority,
        DecisionStatus,
    )

    try:
        data = dict(entry)
        data.pop("recorded_at", None)
        for key in ("created_at", "updated_at", "resolved_at"):
            value = data.get(key)
            data[key] = _datetime.fromisoformat(value) if value else None
        data["category"] = DecisionCategory(data.get("category") or "other")
        data["status"] = DecisionStatus(data.get("status") or "pending")
        data["priority"] = DecisionPriority(int(data.get("priority") or 2))
        return Decision(**data)
    except Exception:
        return None


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping file; missing/corrupt files yield ``{}``."""
    import yaml

    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write a YAML mapping file, preserving key order and unicode."""
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


class RuntimeFacade:
    """Thin, shared adapter over the enterprise runtime engine.

    The facade never owns business logic; it only normalizes the runtime's
    public surface and returns JSON-ready dictionaries. All methods are
    synchronous — the async API layer bridges them through a thread executor
    (ADR 0002) so runtime locks are never held on the event loop.
    """

    def __init__(
        self,
        config_dir: str = "config",
        runtime: RuntimeEngine | None = None,
    ) -> None:
        self._config_dir = config_dir
        self._runtime = (
            runtime if runtime is not None else create_runtime(config_dir=config_dir)
        )
        # Lazy, facade-owned singletons for wave 2b surfaces (kept off the
        # hot read path; created on first use).
        self._generate_runner: Any | None = None
        self._decision_engine: Any | None = None

    @property
    def runtime(self) -> RuntimeEngine:
        """The underlying runtime engine."""
        return self._runtime

    @property
    def config_dir(self) -> str:
        """Directory containing ``config/runtime/*.yaml``."""
        return self._config_dir

    @property
    def event_bus(self) -> Any | None:
        """The runtime's event bus (None until the runtime provides one)."""
        return getattr(self._runtime, "event_bus", None)

    @property
    def phase(self) -> str:
        """Current lifecycle phase (``running``, ``stopped``, ...)."""
        try:
            return self._runtime.status().phase.value
        except Exception:
            return "unknown"

    @property
    def is_running(self) -> bool:
        """Whether the runtime lifecycle phase is ``running``."""
        return self.phase == "running"

    def ensure_running(self) -> None:
        """Boot the runtime if it is not already running."""
        if not self.is_running:
            self._runtime.start()

    def status(self) -> dict[str, Any]:
        """Canonical runtime status view (R12).

        Phase, engines, processes, and active counts — plus the four-state
        ``overall``, ``health_summary``, and a snapshot ``timestamp`` — from
        the canonical status service shared with the CLI and dashboard views.
        Legacy ``RuntimeStatus`` keys are preserved (additive change).
        """
        from ai_company.services.status_service import build_canonical_status

        return build_canonical_status(self._runtime).model_dump(mode="json")

    def health(self) -> list[dict[str, Any]]:
        """Health probe results for every engine plus the system check."""
        return [check.model_dump(mode="json") for check in self._runtime.health()]

    def health_summary(self) -> dict[str, Any]:
        """Aggregated healthy/degraded/unhealthy counts."""
        return self._runtime.health_summary()

    def metrics(self) -> dict[str, Any]:
        """Runtime metrics snapshot (gauges, counters, timers)."""
        return self._runtime.metrics().model_dump(mode="json")

    def engine_states(self) -> list[dict[str, Any]]:
        """Lifecycle + health state of every registered engine."""
        return [
            state.model_dump(mode="json") for state in self._runtime.engine_states()
        ]

    # ── Phase 1 WS-1.0: read-only domain views (parity P1) ──────────

    def registry_list(
        self, company_dir: Path | None = None, config_dir: Path | None = None
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company registry list``."""
        from ai_company.registry.registry import RegistryEngine

        engine = RegistryEngine()
        result = engine.load(
            company_dir or _DEFAULT_COMPANY_DIR,
            config_dir=config_dir or _DEFAULT_CONFIG_COMPANY_DIR,
        )
        errors = _registry_errors(result)
        if errors:
            return {
                "success": False,
                "errors": errors,
                "warnings": list(getattr(result, "warnings", []) or []),
                "registry": None,
            }
        return {
            "success": True,
            "errors": [],
            "warnings": list(getattr(result, "warnings", []) or []),
            "registry": _registry_summary(result.registry),
        }

    def registry_show(
        self,
        name: str,
        company_dir: Path | None = None,
        config_dir: Path | None = None,
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company registry show <name>``."""
        from ai_company.registry.registry import RegistryEngine

        engine = RegistryEngine()
        result = engine.load(
            company_dir or _DEFAULT_COMPANY_DIR,
            config_dir=config_dir or _DEFAULT_CONFIG_COMPANY_DIR,
        )
        errors = _registry_errors(result)
        if errors:
            return {"success": False, "name": name, "errors": errors}
        reg = result.registry
        if name == "vision":
            return {
                "success": True,
                "name": name,
                "entry": reg.vision.model_dump(mode="json"),
            }
        if name == "departments" or name in reg.departments:
            if name == "departments":
                return {
                    "success": True,
                    "name": name,
                    "entry": {
                        dept_name: {
                            "name": dept.name,
                            "roles": [r.model_dump(mode="json") for r in dept.roles],
                        }
                        for dept_name, dept in sorted(reg.departments.items())
                    },
                }
            dept = reg.departments[name]
            return {
                "success": True,
                "name": name,
                "entry": {
                    "name": dept.name,
                    "roles": [r.model_dump(mode="json") for r in dept.roles],
                },
            }
        if name == "board":
            return {
                "success": True,
                "name": name,
                "entry": [b.model_dump(mode="json") for b in reg.board],
            }
        if name == "executives":
            return {
                "success": True,
                "name": name,
                "entry": [{"name": e.name, "title": e.title} for e in reg.executives],
            }
        if name == "policies":
            return {
                "success": True,
                "name": name,
                "entry": [p.model_dump(mode="json") for p in reg.policies],
            }
        if name == "specialists":
            return {
                "success": True,
                "name": name,
                "entry": [s.model_dump(mode="json") for s in reg.specialists],
            }
        if name == "workflows":
            return {
                "success": True,
                "name": name,
                "entry": [w.model_dump(mode="json") for w in reg.workflows],
            }
        return {
            "success": False,
            "name": name,
            "errors": [
                (
                    f"Unknown entry: {name}. Try: vision, departments, board, "
                    "executives, policies, specialists, workflows"
                )
            ],
        }

    def registry_verify(
        self, company_dir: Path | None = None, config_dir: Path | None = None
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company registry verify``."""
        from ai_company.registry.registry import RegistryEngine

        engine = RegistryEngine()
        result = engine.load(
            company_dir or _DEFAULT_COMPANY_DIR,
            config_dir=config_dir or _DEFAULT_CONFIG_COMPANY_DIR,
        )
        errors = _registry_errors(result)
        if errors or result.registry is None:
            return {
                "success": False,
                "errors": errors,
                "warnings": list(getattr(result, "warnings", []) or []),
            }
        return {
            "success": True,
            "errors": [],
            "warnings": list(getattr(result, "warnings", []) or []),
            "vision": result.registry.vision.name,
            "departments": len(result.registry.departments),
            "valid": True,
        }

    def executives_list(
        self, company_dir: Path | None = None, config_dir: Path | None = None
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company exec list``."""
        from ai_company.registry.registry import RegistryEngine

        engine = RegistryEngine()
        result = engine.load(
            company_dir or _DEFAULT_COMPANY_DIR,
            config_dir=config_dir or _DEFAULT_CONFIG_COMPANY_DIR,
        )
        errors = _registry_errors(result)
        if errors or result.registry is None:
            return {"success": False, "errors": errors, "executives": []}
        executives = [
            {
                "name": ex.name,
                "title": ex.title,
                "department": ex.department,
                "status": ex.status or "active",
                "kpis": list(ex.kpis),
            }
            for ex in result.registry.executives
            if ex.name
        ]
        return {"success": True, "errors": [], "executives": executives}

    def executive_show(
        self,
        name: str,
        company_dir: Path | None = None,
        config_dir: Path | None = None,
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company exec show <name>``."""
        from ai_company.registry.registry import RegistryEngine

        engine = RegistryEngine()
        result = engine.load(
            company_dir or _DEFAULT_COMPANY_DIR,
            config_dir=config_dir or _DEFAULT_CONFIG_COMPANY_DIR,
        )
        errors = _registry_errors(result)
        if errors or result.registry is None:
            return {"success": False, "name": name, "errors": errors}
        reg = result.registry
        ex = next(
            (e for e in reg.executives if e.name and e.name.lower() == name.lower()),
            None,
        )
        if ex is None:
            return {
                "success": False,
                "name": name,
                "errors": [f"Executive '{name}' not found."],
            }
        ac = ex.agent_config
        exec_kpis = [
            k
            for k in reg.kpis
            if k.owner
            and (
                k.owner.lower() in (ex.title or "").lower()
                or k.owner.lower() in (ex.name or "").lower()
            )
        ]
        if not exec_kpis:
            exec_kpis = [k for k in reg.kpis if k.name in (ex.kpis or [])]
        dept = ex.department or ""
        budget = next(
            (b for b in reg.budgets if b.department.lower() == dept.lower()), None
        )
        return {
            "success": True,
            "name": ex.name,
            "executive": {
                "name": ex.name,
                "title": ex.title,
                "department": ex.department,
                "status": ex.status or "active",
                "reports_to": ex.reports_to or "Board of Directors",
                "start_date": ex.start_date,
                "email": ex.email,
                "bio": ex.bio,
                "responsibilities": list(ex.responsibilities),
                "direct_reports": list(ex.direct_reports),
                "budget_authority": ex.budget_authority,
                "kpis": [k.model_dump(mode="json") for k in exec_kpis],
                "budget": budget.model_dump(mode="json") if budget else None,
                "agent_config": ac.model_dump(mode="json"),
            },
        }

    def org_chart(
        self, company_dir: Path | None = None, config_dir: Path | None = None
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company exec org-chart`` (Mermaid source only)."""
        from ai_company.registry.registry import RegistryEngine

        engine = RegistryEngine()
        result = engine.load(
            company_dir or _DEFAULT_COMPANY_DIR,
            config_dir=config_dir or _DEFAULT_CONFIG_COMPANY_DIR,
        )
        errors = _registry_errors(result)
        if errors or result.registry is None:
            return {"success": False, "errors": errors, "mermaid": None}
        reg = result.registry
        lines = ["```mermaid", "graph TD", ""]
        lines.append("    Board[Board of Directors] --> CEO")
        lines.append("")
        ceo_name = ""
        ceo_title = "CEO"
        for ex in reg.executives:
            if ex.name and "ceo" in (ex.title or "").lower():
                ceo_name = ex.name
                ceo_title = ex.title or "CEO"
                lines.append(f"    CEO[{ceo_name} - {ceo_title}]")
                break
        if not ceo_name:
            if reg.executives and reg.executives[0].name:
                ceo_name = reg.executives[0].name
                ceo_title = reg.executives[0].title or "CEO"
                lines.append(f'    CEO["{ceo_name} - {ceo_title}"]')
            else:
                lines.append('    CEO["Chief Executive Officer"]')
        for ex in reg.executives:
            if not ex.name or "ceo" in (ex.title or "").lower():
                continue
            safe_name = ex.name.replace(" ", "_").replace(".", "")
            manager = "CEO"
            if ex.reports_to:
                for e2 in reg.executives:
                    if e2.name and e2.name.lower() in ex.reports_to.lower():
                        manager = e2.name.replace(" ", "_").replace(".", "")
                        break
            lines.append(f'    {manager} --> {safe_name}["{ex.name} - {ex.title}"]')
        lines.append("")
        lines.append("```")
        return {
            "success": True,
            "errors": [],
            "mermaid": "\n".join(lines),
            "executives": len(reg.executives),
        }

    def _memory_engine(
        self,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> Any:
        """Build a read-oriented MemoryEngine (mirrors the CLI memory group)."""
        if memory_engine is not None:
            return memory_engine
        from ai_company.memory.engine import MemoryEngine

        if config_path is None:
            config_path = _DEFAULT_MEMORY_CONFIG
        if config_path.exists():
            return MemoryEngine.from_config(str(config_path))
        return MemoryEngine(storage_path=str(storage_path or _DEFAULT_MEMORY_STORAGE))

    def memory_list(
        self,
        memory_type: str | None = None,
        namespace: str | None = None,
        limit: int = 20,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company memory list`` (read-only)."""
        try:
            engine = self._memory_engine(memory_engine, config_path, storage_path)
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "entries": []}
        try:
            if memory_type and namespace:
                results = engine.search(
                    namespace=namespace, memory_type=memory_type, limit=limit
                )
            elif memory_type:
                results = engine.retrieve_by_type(memory_type)
            elif namespace:
                results = engine.retrieve_by_namespace(namespace)
            else:
                results = sorted(
                    engine.retrieve_all(), key=lambda e: e.created_at, reverse=True
                )[:limit]
            return {
                "success": True,
                "errors": [],
                "count": len(results),
                "entries": [e.to_dict() for e in results],
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "entries": []}

    def memory_get(
        self,
        memory_id: str,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company memory get <id>``."""
        try:
            engine = self._memory_engine(memory_engine, config_path, storage_path)
            # Read-only: use the store directly — engine.retrieve() touches and
            # saves the entry (a write, forbidden in the read-only facade).
            entry = engine.store.get(memory_id)
        except Exception as exc:
            return {"success": False, "memory_id": memory_id, "errors": [str(exc)]}
        if entry is None:
            return {
                "success": False,
                "memory_id": memory_id,
                "errors": [f"Memory not found: {memory_id}"],
            }
        return {"success": True, "memory_id": memory_id, "entry": entry.to_dict()}

    def memory_search(
        self,
        query: str = "",
        memory_type: str | None = None,
        namespace: str | None = None,
        tags: str = "",
        limit: int = 20,
        min_importance: float = 0.0,
        include_archived: bool = False,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company memory search`` (read-only)."""
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        try:
            engine = self._memory_engine(memory_engine, config_path, storage_path)
            results = engine.search(
                query=query,
                memory_type=memory_type,
                namespace=namespace,
                tags=tag_list,
                limit=limit,
                min_importance=min_importance,
                include_archived=include_archived,
            )
            return {
                "success": True,
                "errors": [],
                "count": len(results),
                "results": [e.to_dict() for e in results],
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "results": []}

    def memory_stats(
        self,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company memory stats``."""
        try:
            engine = self._memory_engine(memory_engine, config_path, storage_path)
            return {"success": True, "errors": [], "stats": engine.get_statistics()}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "stats": None}

    def memory_snapshots(
        self,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company memory snapshots``."""
        try:
            engine = self._memory_engine(memory_engine, config_path, storage_path)
            return {
                "success": True,
                "errors": [],
                "snapshots": engine.list_snapshots(),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "snapshots": []}

    def graph_show(
        self, company_dir: Path | None = None, config_dir: Path | None = None
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company graph show``."""
        from ai_company.registry.registry import RegistryEngine

        engine = RegistryEngine()
        result = engine.load(
            company_dir or _DEFAULT_COMPANY_DIR,
            config_dir=config_dir or _DEFAULT_CONFIG_COMPANY_DIR,
        )
        errors = _registry_errors(result)
        if errors or result.registry is None:
            return {"success": False, "errors": errors}
        reg = result.registry
        total_roles = sum(len(d.roles) for d in reg.departments.values())
        return {
            "success": True,
            "errors": [],
            "vision": reg.vision.name,
            "departments": {
                name: {"roles": [r.title for r in dept.roles]}
                for name, dept in sorted(reg.departments.items())
            },
            "board": len(reg.board),
            "executives": len(reg.executives),
            "edges": total_roles + len(reg.unresolved_refs),
        }

    def graph_stats(
        self, company_dir: Path | None = None, config_dir: Path | None = None
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company graph stats``."""
        from ai_company.registry.registry import RegistryEngine

        engine = RegistryEngine()
        result = engine.load(
            company_dir or _DEFAULT_COMPANY_DIR,
            config_dir=config_dir or _DEFAULT_CONFIG_COMPANY_DIR,
        )
        errors = _registry_errors(result)
        if errors or result.registry is None:
            return {"success": False, "errors": errors}
        reg = result.registry
        total_roles = sum(len(d.roles) for d in reg.departments.values())
        total_nodes = 1 + len(reg.departments) + total_roles
        total_edges = total_roles + len(reg.unresolved_refs)
        density = (
            total_edges / (total_nodes * (total_nodes - 1)) if total_nodes > 1 else 0
        )
        return {
            "success": True,
            "errors": [],
            "nodes": total_nodes,
            "edges": total_edges,
            "density": round(density, 4),
            "unresolved_refs": len(reg.unresolved_refs),
        }

    def reports_list(self) -> dict[str, Any]:
        """JSON mirror of ``ai-company report generate`` valid types."""
        return {
            "success": True,
            "errors": [],
            "types": ["summary", "detailed", "health"],
        }

    def report_generate_read(
        self,
        report_type: str = "summary",
        company_dir: Path | None = None,
        config_dir: Path | None = None,
    ) -> dict[str, Any]:
        """JSON mirror of the read path of ``ai-company report generate <type>``."""
        from ai_company.registry.registry import RegistryEngine

        if report_type not in ("summary", "detailed", "health"):
            return {
                "success": False,
                "report_type": report_type,
                "errors": [
                    (
                        f"Unknown report type: {report_type}. "
                        "Available: summary, detailed, health"
                    )
                ],
            }
        engine = RegistryEngine()
        result = engine.load(
            company_dir or _DEFAULT_COMPANY_DIR,
            config_dir=config_dir or _DEFAULT_CONFIG_COMPANY_DIR,
        )
        errors = _registry_errors(result)
        if errors or result.registry is None:
            return {
                "success": False,
                "report_type": report_type,
                "errors": errors,
            }
        reg = result.registry
        if report_type == "summary":
            total_roles = sum(len(d.roles) for d in reg.departments.values())
            return {
                "success": True,
                "report_type": report_type,
                "errors": [],
                "company": reg.vision.company_name or reg.vision.name,
                "vision": reg.vision.name,
                "departments": len(reg.departments),
                "roles": total_roles,
                "board": len(reg.board),
                "workflows": len(reg.workflows),
                "warnings": list(getattr(result, "warnings", []) or []),
            }
        if report_type == "detailed":
            return {
                "success": True,
                "report_type": report_type,
                "errors": [],
                "vision": reg.vision.model_dump(mode="json"),
                "departments": {
                    dept_name: {
                        "name": dept.name,
                        "roles": [r.model_dump(mode="json") for r in dept.roles],
                    }
                    for dept_name, dept in sorted(reg.departments.items())
                },
                "board": [b.model_dump(mode="json") for b in reg.board],
                "executives": [
                    {"name": e.name, "title": e.title} for e in reg.executives
                ],
                "workflows": [w.model_dump(mode="json") for w in reg.workflows],
            }
        validation = self.validate_read(company_dir=company_dir, config_dir=config_dir)
        return {
            "success": True,
            "report_type": report_type,
            "errors": [],
            "validation": validation,
        }

    def validate_read(
        self,
        company_dir: Path | None = None,
        config_dir: Path | None = None,
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company validate`` (read-only run)."""
        from ai_company.validator.engine import ValidatorEngine

        try:
            validator = ValidatorEngine(
                company_dir=company_dir or _DEFAULT_COMPANY_DIR,
                manifest_path=(config_dir or _DEFAULT_CONFIG_COMPANY_DIR).joinpath(
                    "company.yaml"
                ),
                templates_dir=Path("templates"),
                output_dir=Path("generated"),
            )
            result = validator.validate_all()
            return {
                "success": True,
                "errors": [],
                "passed": result.passed,
                "summary": result.summary(),
                "total_checks": result.total_checks,
                "total_errors": result.total_errors,
                "total_warnings": result.total_warnings,
                "reports": [r.model_dump(mode="json") for r in result.reports],
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    def diagnostics(self) -> dict[str, Any]:
        """Full runtime diagnostic report (JSON-ready)."""
        report = self._runtime.diagnostics()
        return report.model_dump(mode="json")

    def orchestration_status(self, engine: Any | None = None) -> dict[str, Any]:
        """JSON mirror of ``ai-company orchestrate status``."""
        from ai_company.orchestration import OrchestrationEngine

        owns = engine is None
        try:
            engine = engine or OrchestrationEngine()
            status = engine.engine_status()
            return {
                "success": True,
                "errors": [],
                "engine": status.model_dump(mode="json"),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "engine": None}
        finally:
            if owns and engine is not None:
                try:
                    engine.close()
                except Exception:
                    logger.debug("Orchestration engine close failed", exc_info=True)

    def orchestration_history(
        self, plan_id: str | None = None, limit: int = 20, engine: Any | None = None
    ) -> dict[str, Any]:
        """JSON mirror of ``ai-company orchestrate history``."""
        from ai_company.orchestration import OrchestrationEngine
        from ai_company.services.deep_links import enrich_plan, project_directory

        owns = engine is None
        directory = project_directory(self._config_dir)
        try:
            engine = engine or OrchestrationEngine()
            records = engine.history(plan_id)[:limit]
            return {
                "success": True,
                "errors": [],
                "count": len(records),
                "records": [
                    enrich_plan(r.model_dump(mode="json"), directory) for r in records
                ],
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "records": []}
        finally:
            if owns and engine is not None:
                try:
                    engine.close()
                except Exception:
                    logger.debug("Orchestration engine close failed", exc_info=True)

    def generate_targets(self) -> dict[str, Any]:
        """JSON mirror of ``ai-company targets``."""
        from ai_company.cli.command_map import load_command_map
        from ai_company.services.deep_links import enrich_target, project_directory

        directory = project_directory(self._config_dir)
        try:
            command_map = load_command_map()
            return {
                "success": True,
                "errors": [],
                "targets": [
                    enrich_target(
                        {
                            "key": key,
                            "description": entry.description,
                            "agent": entry.agent,
                            "model": entry.model,
                            "prompt_file": entry.prompt_file,
                        },
                        directory,
                    )
                    for key, entry in sorted(command_map.items())
                ],
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "targets": []}

    # ── Phase 2 (WS-2.1): write actions (ADR 0010 — auth-guarded by the API) ──
    # Thin adapters mirroring the equivalent CLI write commands. The API layer
    # enforces bearer token + CSRF + audit before any of these run; the facade
    # itself stays an honest, dependency-free mirror of the CLI semantics.

    def runtime_start(self) -> dict[str, Any]:
        """Start the runtime (parity with ``ai-company runtime start``)."""
        try:
            status = self._runtime.start()
            return {
                "success": True,
                "errors": [],
                "phase": getattr(status, "phase", "running").value
                if hasattr(getattr(status, "phase", None), "value")
                else str(getattr(status, "phase", "running")),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    def runtime_stop(self, reason: str = "manual") -> dict[str, Any]:
        """Stop the runtime (parity with ``ai-company runtime stop``)."""
        try:
            status = self._runtime.stop(reason=reason)
            return {
                "success": True,
                "errors": [],
                "phase": str(getattr(status, "phase", "stopped")),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    def runtime_restart(self, reason: str = "manual") -> dict[str, Any]:
        """Restart the runtime (parity with ``ai-company runtime restart``)."""
        try:
            status = self._runtime.restart(reason=reason)
            return {
                "success": True,
                "errors": [],
                "phase": str(getattr(status, "phase", "running")),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    def runtime_reload(self) -> dict[str, Any]:
        """Hot-reload runtime configuration (parity with ``runtime reload``)."""
        try:
            changed = self._runtime.reload()
            return {"success": True, "errors": [], "changed": list(changed)}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    def runtime_recover(self, engine: str, reason: str = "manual") -> dict[str, Any]:
        """Recover one failed engine (parity with ``runtime recover``)."""
        try:
            result = self._runtime.recover_engine(engine, reason=reason)
            return {
                "success": True,
                "errors": [],
                "engine": engine,
                "recovered": bool(getattr(result, "recovered", True)),
                "attempts": getattr(result, "attempts", None),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    def runtime_unisolate(self, engine: str) -> dict[str, Any]:
        """Un-isolate an engine (parity with ``runtime unisolate``)."""
        try:
            self._runtime.unisolate(engine)
            return {"success": True, "errors": [], "engine": engine}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    def orchestrate_plan(
        self,
        name: str | None = None,
        yaml_path: str | None = None,
        data: dict[str, Any] | None = None,
        description: str = "",
        engine: Any | None = None,
    ) -> dict[str, Any]:
        """Create an orchestration plan (parity with ``orchestrate plan``)."""
        from ai_company.orchestration import OrchestrationEngine

        owns = engine is None
        try:
            engine = engine or OrchestrationEngine()
            plan = engine.plan(
                name=name, yaml_path=yaml_path, data=data, description=description
            )
            return {
                "success": True,
                "errors": [],
                "plan": plan.model_dump(mode="json"),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "plan": None}
        finally:
            if owns and engine is not None:
                try:
                    engine.close()
                except Exception:
                    logger.debug("Orchestration engine close failed", exc_info=True)

    def orchestrate_start(
        self, plan_id: str, engine: Any | None = None
    ) -> dict[str, Any]:
        """Start a planned pipeline (parity with ``orchestrate start``)."""
        from ai_company.orchestration import OrchestrationEngine

        owns = engine is None
        try:
            engine = engine or OrchestrationEngine()
            plan = next((p for p in engine.list_plans() if p.id == plan_id), None)
            if plan is None:
                return {
                    "success": False,
                    "errors": [f"Plan not found: {plan_id}"],
                    "record": None,
                }
            record = engine.start(plan)
            return {
                "success": True,
                "errors": [],
                "record": record.model_dump(mode="json"),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "record": None}
        finally:
            if owns and engine is not None:
                try:
                    engine.close()
                except Exception:
                    logger.debug("Orchestration engine close failed", exc_info=True)

    def orchestrate_resume(
        self,
        plan_id: str,
        checkpoint_id: str | None = None,
        engine: Any | None = None,
    ) -> dict[str, Any]:
        """Resume a paused pipeline (parity with ``orchestrate resume``)."""
        from ai_company.orchestration import OrchestrationEngine

        owns = engine is None
        try:
            engine = engine or OrchestrationEngine()
            record = engine.resume(plan_id, checkpoint_id=checkpoint_id)
            return {
                "success": True,
                "errors": [],
                "record": record.model_dump(mode="json"),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "record": None}
        finally:
            if owns and engine is not None:
                try:
                    engine.close()
                except Exception:
                    logger.debug("Orchestration engine close failed", exc_info=True)

    def orchestrate_retry(
        self, plan_id: str, engine: Any | None = None
    ) -> dict[str, Any]:
        """Retry a failed pipeline (parity with ``orchestrate retry``)."""
        from ai_company.orchestration import OrchestrationEngine

        owns = engine is None
        try:
            engine = engine or OrchestrationEngine()
            record = engine.retry(plan_id)
            return {
                "success": True,
                "errors": [],
                "record": record.model_dump(mode="json"),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "record": None}
        finally:
            if owns and engine is not None:
                try:
                    engine.close()
                except Exception:
                    logger.debug("Orchestration engine close failed", exc_info=True)

    def orchestrate_rollback(
        self, plan_id: str, reason: str = "manual rollback", engine: Any | None = None
    ) -> dict[str, Any]:
        """Roll back a pipeline (parity with ``orchestrate rollback``)."""
        from ai_company.orchestration import OrchestrationEngine

        owns = engine is None
        try:
            engine = engine or OrchestrationEngine()
            plan = engine.rollback(plan_id, reason=reason)
            return {
                "success": True,
                "errors": [],
                "rollback": plan.model_dump(mode="json"),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "rollback": None}
        finally:
            if owns and engine is not None:
                try:
                    engine.close()
                except Exception:
                    logger.debug("Orchestration engine close failed", exc_info=True)

    def memory_save(
        self,
        content: dict[str, Any],
        memory_type: str | None = None,
        namespace: str | None = None,
        tags: list[str] | None = None,
        source: str = "dashboard",
        importance: float | None = None,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> dict[str, Any]:
        """Save a memory entry (parity with ``ai-company memory save``)."""
        try:
            engine = self._memory_engine(memory_engine, config_path, storage_path)
            entry = engine.save(
                content=content,
                memory_type=memory_type or "system",
                namespace=namespace or "global",
                tags=tags or [],
                source=source,
                importance=importance,
            )
            return {"success": True, "errors": [], "entry": entry.to_dict()}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "entry": None}

    def memory_update(
        self,
        memory_id: str,
        content: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        importance: float | None = None,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> dict[str, Any]:
        """Update a memory entry (parity with ``ai-company memory update``)."""
        try:
            engine = self._memory_engine(memory_engine, config_path, storage_path)
            entry = engine.update(
                memory_id,
                content=content,
                tags=tags,
                importance=importance,
            )
            return {"success": True, "errors": [], "entry": entry.to_dict()}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "entry": None}

    def memory_archive(
        self,
        memory_id: str,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> dict[str, Any]:
        """Archive a memory entry (parity with ``ai-company memory archive``)."""
        try:
            engine = self._memory_engine(memory_engine, config_path, storage_path)
            archived = engine.archive(memory_id)
            return {
                "success": True,
                "errors": [],
                "memory_id": memory_id,
                "archived": bool(archived),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "archived": False}

    def memory_unarchive(
        self,
        memory_id: str,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> dict[str, Any]:
        """Un-archive a memory entry (parity with ``ai-company memory unarchive``)."""
        try:
            engine = self._memory_engine(memory_engine, config_path, storage_path)
            unarchived = engine.unarchive(memory_id)
            return {
                "success": True,
                "errors": [],
                "memory_id": memory_id,
                "unarchived": bool(unarchived),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "unarchived": False}

    def memory_snapshot(
        self,
        name: str | None = None,
        memory_ids: list[str] | None = None,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> dict[str, Any]:
        """Create a memory snapshot (parity with ``ai-company memory snapshot``)."""
        from datetime import datetime as _datetime

        try:
            engine = self._memory_engine(memory_engine, config_path, storage_path)
            snapshot_name = (
                name or f"snapshot-{_datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            snapshot_id = engine.snapshot(snapshot_name, memory_ids)
            return {
                "success": True,
                "errors": [],
                "snapshot_id": snapshot_id,
                "name": snapshot_name,
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "snapshot_id": None}

    def memory_restore(
        self,
        snapshot_id: str,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> dict[str, Any]:
        """Restore from a snapshot (parity with ``ai-company memory restore``)."""
        try:
            engine = self._memory_engine(memory_engine, config_path, storage_path)
            restored = engine.restore_snapshot(snapshot_id)
            return {
                "success": True,
                "errors": [],
                "snapshot_id": snapshot_id,
                "restored": int(restored),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "restored": 0}

    def memory_export(
        self,
        path: Path | None = None,
        memory_engine: Any | None = None,
        config_path: Path | None = None,
        storage_path: Path | None = None,
    ) -> dict[str, Any]:
        """Export memory to JSON (parity with ``ai-company memory export``)."""
        from datetime import datetime as _datetime

        try:
            engine = self._memory_engine(memory_engine, config_path, storage_path)
            target = path or Path(
                f"generated/exports/memory-{_datetime.now().strftime('%Y%m%d%H%M%S')}.json"
            )
            exported = engine.export_to_json(target)
            return {"success": True, "errors": [], "path": str(exported)}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "path": None}

    def validate_run(
        self,
        company_dir: Path | None = None,
        config_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Authenticated validation run (POST /api/validate).

        Executes the same :class:`ValidatorEngine` pass as the read-only view;
        the API layer audits this as an operator action (ADR 0010).
        """
        return self.validate_read(company_dir=company_dir, config_dir=config_dir)

    def report_generate_write(
        self,
        report_type: str = "summary",
        company_dir: Path | None = None,
        config_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Authenticated on-demand report generation (POST /api/reports/generate).

        Mirrors ``ai-company report generate <type>`` — the CLI renders the
        report to the console (no file write), so the write surface is the
        audited on-demand run of the same rendering.
        """
        return self.report_generate_read(
            report_type=report_type, company_dir=company_dir, config_dir=config_dir
        )

    def build_run(self) -> dict[str, Any]:
        """Run the artifact build pipeline (parity with ``ai-company build``)."""
        from ai_company.bootstrap.bootstrap import BootstrapGenerator
        from ai_company.company.generator import CompanyGenerator

        try:
            bootstrap = BootstrapGenerator()
            result = bootstrap.run()
            if not result.success:
                return {
                    "success": False,
                    "errors": list(result.errors),
                    "created_files": 0,
                }
            company_gen = CompanyGenerator()
            all_result = company_gen.generate_all()
            return {
                "success": True,
                "errors": [],
                "warnings": list(all_result.warnings),
                "created_files": len(all_result.created_files),
                "summaries": {
                    name: dict(summary)
                    for name, summary in all_result.summaries.items()
                },
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "created_files": 0}

    def bootstrap_run(self) -> dict[str, Any]:
        """Scaffold + generate the full company (parity with ``bootstrap``)."""
        return self.build_run()

    # ── Phase 2 (WS-2.2): wave 2b operations ─────────────────────────────────
    # Generate loop, decision/approval inbox, per-artifact validators, graph
    # export write, company CRUD, agent sync, backup, and R5 telemetry.
    # Reads are dependency-free; writes are auth-guarded by the API layer.

    # ── generate loop ────────────────────────────────────────────────────────

    def _generate_runner_instance(self) -> Any:
        """Lazily build the shared :class:`GenerateRunner`."""
        if self._generate_runner is None:
            from ai_company.services.generate_runner import GenerateRunner

            self._generate_runner = GenerateRunner()
        return self._generate_runner

    def generate_runs(self, limit: int = 50) -> dict[str, Any]:
        """Recent generate runs (newest first)."""
        from ai_company.services.deep_links import enrich_run, project_directory

        directory = project_directory(self._config_dir)
        try:
            runs = self._generate_runner_instance().list_runs(limit=limit)
            return {
                "success": True,
                "errors": [],
                "runs": [enrich_run(run.to_dict(), directory) for run in runs],
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "runs": []}

    def generate_run(self, run_id: str) -> dict[str, Any]:
        """One generate run by id."""
        from ai_company.services.deep_links import enrich_run, project_directory

        run = self._generate_runner_instance().get(run_id)
        if run is None:
            return {
                "success": False,
                "errors": [f"run not found: {run_id}"],
                "run": None,
            }
        return {
            "success": True,
            "errors": [],
            "run": enrich_run(run.to_dict(), project_directory(self._config_dir)),
        }

    def generate_log(self, run_id: str, max_lines: int = 400) -> dict[str, Any]:
        """Tail of one run's streamed log."""
        try:
            lines = self._generate_runner_instance().log_tail(
                run_id, max_lines=max_lines
            )
            return {"success": True, "errors": [], "lines": lines}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "lines": []}

    def generate_start(self, target: str, reason: str = "") -> dict[str, Any]:
        """Dispatch one generate run (mirrors ``ai-company generate <target>``)."""
        from ai_company.services.deep_links import enrich_run, project_directory

        try:
            run = self._generate_runner_instance().start(target, reason=reason)
        except ValueError as exc:
            return {"success": False, "errors": [str(exc)], "run": None}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "run": None}
        return {
            "success": True,
            "errors": [],
            "run": enrich_run(run.to_dict(), project_directory(self._config_dir)),
        }

    def generate_cancel(self, run_id: str) -> dict[str, Any]:
        """Cancel a running generate dispatch."""
        run = self._generate_runner_instance().cancel(run_id)
        if run is None:
            return {
                "success": False,
                "errors": [f"run not found: {run_id}"],
                "run": None,
            }
        return {"success": True, "errors": [], "run": run.to_dict()}

    # ── decisions / approval inbox ───────────────────────────────────────────

    def _decision_engine_instance(self) -> Any:
        """Lazily build the shared :class:`DecisionEngine` (history-backed)."""
        if self._decision_engine is None:
            from ai_company.decision.engine import DecisionEngine
            from ai_company.decision.history import DecisionHistory

            history = DecisionHistory(storage_path="runtime/decisions.jsonl")
            rebuilt = [
                decision
                for entry in history.get_history(limit=10**6)
                if (decision := _decision_from_history_entry(entry)) is not None
            ]
            history.import_decisions(rebuilt)
            self._decision_engine = DecisionEngine(decision_history=history)
        return self._decision_engine

    def decisions_list(
        self,
        status: str | None = None,
        category: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Decisions for the approval inbox (optionally filtered)."""
        try:
            engine = self._decision_engine_instance()
            decisions = engine.list_decisions(
                status=status, category=category, limit=limit
            )
            return {
                "success": True,
                "errors": [],
                "decisions": [d.to_dict() for d in decisions],
                "count": len(decisions),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "decisions": []}

    def decision_get(self, decision_id: str) -> dict[str, Any]:
        """One decision plus its explainability summary."""
        try:
            engine = self._decision_engine_instance()
            decision = engine.get_decision(decision_id)
            if decision is None:
                return {
                    "success": False,
                    "errors": [f"decision not found: {decision_id}"],
                    "decision": None,
                }
            return {
                "success": True,
                "errors": [],
                "decision": decision.to_dict(),
                "explanation": engine.explain(decision),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "decision": None}

    def decision_create(
        self,
        title: str,
        description: str,
        category: str = "operational",
        priority: str = "medium",
        requester: str = "dashboard",
        owner: str = "",
        options: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a decision for the approval inbox."""
        try:
            engine = self._decision_engine_instance()
            # ``create_decision`` evaluates risk, resolves the approval path,
            # and persists to the decision history itself.
            decision = engine.create_decision(
                title=title,
                description=description,
                category=category,
                priority=priority,
                requester=requester,
                owner=owner,
                options=options or [],
            )
            return {
                "success": True,
                "errors": [],
                "decision": decision.to_dict(),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "decision": None}

    def review_submit(
        self,
        title: str,
        description: str,
        artifact_paths: list[str] | None = None,
        session_id: str = "",
        model: str = "",
        base_url: str = "http://127.0.0.1:8000/",
    ) -> dict[str, Any]:
        """Submit a generated artifact from a desktop session for review (P4).

        Creates a ``review`` decision in the approval inbox tagged as a
        desktop submission and returns a ``review_link`` deep link that
        focuses the new review on the dashboard (``/decisions?focus=<id>``).
        The desktop agent hands ``review_link`` to the operator; it is a
        desktop-HTTP surface with no CLI counterpart (ADR 0006 / R3 N/A).
        """
        from ai_company.services.deep_links import review_link

        try:
            engine = self._decision_engine_instance()
            decision = engine.create_decision(
                title=title,
                description=description,
                category="operational",
                requester=session_id or "desktop",
                tags=["review", "desktop"],
                metadata={
                    "source": "desktop",
                    "session_id": session_id,
                    "artifact_paths": artifact_paths or [],
                    "model": model,
                },
            )
            return {
                "success": True,
                "errors": [],
                "decision": decision.to_dict(),
                "review_link": review_link(decision.id, base_url),
            }
        except Exception as exc:
            return {
                "success": False,
                "errors": [str(exc)],
                "decision": None,
                "review_link": None,
            }

    def decision_approve(
        self,
        decision_id: str,
        selected_option: str,
        rationale: str,
        approved_by: str = "dashboard-operator",
    ) -> dict[str, Any]:
        """Approve a decision by selecting an option (audited by the API)."""
        try:
            engine = self._decision_engine_instance()
            decision = engine.get_decision(decision_id)
            if decision is None:
                return {
                    "success": False,
                    "errors": [f"decision not found: {decision_id}"],
                }
            if decision.status.value not in ("pending", "in_review"):
                return {
                    "success": False,
                    "errors": [f"decision already resolved: {decision.status.value}"],
                }
            resolved = engine.make_decision(
                decision=decision,
                selected_option=selected_option,
                rationale=rationale,
                approved_by=approved_by,
            )
            return {"success": True, "errors": [], "decision": resolved.to_dict()}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    def decision_reject(self, decision_id: str, reason: str) -> dict[str, Any]:
        """Reject a pending decision (requires a reason)."""
        try:
            engine = self._decision_engine_instance()
            decision = engine.get_decision(decision_id)
            if decision is None:
                return {
                    "success": False,
                    "errors": [f"decision not found: {decision_id}"],
                }
            if decision.status.value not in ("pending", "in_review"):
                return {
                    "success": False,
                    "errors": [f"decision already resolved: {decision.status.value}"],
                }
            rejected = engine.reject(decision, reason)
            return {"success": True, "errors": [], "decision": rejected.to_dict()}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    def decision_escalate(self, decision_id: str, note: str = "") -> dict[str, Any]:
        """Escalate a decision to the next approval level."""
        try:
            engine = self._decision_engine_instance()
            decision = engine.get_decision(decision_id)
            if decision is None:
                return {
                    "success": False,
                    "errors": [f"decision not found: {decision_id}"],
                }
            escalated = engine.escalate(decision, note)
            return {"success": True, "errors": [], "decision": escalated.to_dict()}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    def decision_cancel(self, decision_id: str, reason: str) -> dict[str, Any]:
        """Cancel a pending decision (requires a reason)."""
        try:
            engine = self._decision_engine_instance()
            decision = engine.get_decision(decision_id)
            if decision is None:
                return {
                    "success": False,
                    "errors": [f"decision not found: {decision_id}"],
                }
            cancelled = engine.cancel(decision, reason)
            return {"success": True, "errors": [], "decision": cancelled.to_dict()}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    # ── per-artifact validators ──────────────────────────────────────────────

    def validate_artifacts(
        self,
        artifact: str = "all",
        company_dir: Path | None = None,
        config_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Run one (or all) of the per-artifact validation passes.

        Mirrors the five ``ValidatorEngine`` passes (yaml/registry/templates/
        manifest/output). ``artifact="all"`` runs every pass and rolls the
        reports into one result, matching ``ai-company validate``.
        """
        from ai_company.validator.engine import ValidatorEngine
        from ai_company.validator.reports import ValidatorResult

        try:
            engine = ValidatorEngine(
                company_dir=company_dir or Path("company"),
                manifest_path=config_dir / Path("company/company.yaml")
                if config_dir
                else Path("config/company/company.yaml"),
            )
            if artifact == "all":
                result: ValidatorResult = engine.validate_all()
            else:
                method = getattr(engine, f"validate_{artifact}", None)
                if method is None:
                    return {
                        "success": False,
                        "errors": [f"unknown artifact: {artifact}"],
                        "reports": [],
                    }
                # Per-artifact passes return one report; wrap it so the
                # response shape matches ``validate_all``.
                result = ValidatorResult(reports=[method()])
            return {
                "success": result.passed,
                "errors": [],
                "artifact": artifact,
                "summary": result.summary(),
                "reports": [r.model_dump(mode="json") for r in result.reports],
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "reports": []}

    # ── graph export write ───────────────────────────────────────────────────

    def graph_export_write(self, output_dir: str = "generated") -> dict[str, Any]:
        """Export the company graph as Mermaid + enriched JSON.

        Mirrors ``ai-company graph export`` (the CLI writes artifacts; the
        read-only ``graph_show``/``graph_stats`` stay query surfaces).
        """
        from ai_company.company.graph_exporter import GraphExporter
        from ai_company.registry.registry import RegistryEngine

        try:
            reg = (
                RegistryEngine()
                .load(Path("company"), config_dir=Path("config/company"))
                .registry
            )
            if reg is None:
                return {"success": False, "errors": ["registry could not load"]}
            exporter = GraphExporter(reg)
            errors = exporter.validate()
            if errors:
                return {"success": False, "errors": list(errors)}
            result = exporter.generate()
            created = exporter.write_artifacts(result, Path(output_dir))
            return {
                "success": True,
                "errors": [],
                "files": [str(path) for path in created],
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    # ── company CRUD (declarative YAML write surface) ───────────────────────

    def company_files(self) -> dict[str, Any]:
        """List the registry YAML files that back the company."""
        registry_dir = Path("company")
        files = (
            sorted(path.name for path in registry_dir.glob("*.yaml"))
            if registry_dir.is_dir()
            else []
        )
        return {"success": True, "errors": [], "files": files}

    def company_department_add(
        self,
        name: str,
        title: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Add a department to ``company/departments.yaml`` + the manifest."""
        import re as _re

        slug = _re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
        if not slug:
            return {"success": False, "errors": ["invalid department name"]}

        departments_path = Path("company/departments.yaml")
        data = _load_yaml(departments_path)
        if slug in data:
            return {"success": False, "errors": [f"department exists: {slug}"]}
        role = (title or "").strip() or slug.replace("-", " ").title()
        data[slug] = [{role: (description or "").strip() or role}]
        _save_yaml(departments_path, data)

        manifest_path = Path("config/company/company.yaml")
        manifest = _load_yaml(manifest_path)
        departments = manifest.get("departments")
        if isinstance(departments, list) and slug not in departments:
            departments.append(slug)
            _save_yaml(manifest_path, manifest)

        return {
            "success": True,
            "errors": [],
            "department": slug,
            "role": role,
        }

    def company_department_remove(self, name: str) -> dict[str, Any]:
        """Remove a department from ``company/departments.yaml`` + manifest."""
        import re as _re

        slug = _re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
        if not slug:
            return {"success": False, "errors": ["invalid department name"]}

        departments_path = Path("company/departments.yaml")
        data = _load_yaml(departments_path)
        if slug not in data:
            return {"success": False, "errors": [f"department not found: {slug}"]}
        del data[slug]
        _save_yaml(departments_path, data)

        manifest_path = Path("config/company/company.yaml")
        manifest = _load_yaml(manifest_path)
        departments = manifest.get("departments")
        if isinstance(departments, list) and slug in departments:
            departments[:] = [d for d in departments if d != slug]
            _save_yaml(manifest_path, manifest)

        return {"success": True, "errors": [], "department": slug}

    def company_manifest_update(
        self,
        name: str | None = None,
        company_name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update manifest metadata in ``config/company/company.yaml``."""
        manifest_path = Path("config/company/company.yaml")
        manifest = _load_yaml(manifest_path)
        changed: list[str] = []
        if name is not None and manifest.get("name") != name:
            manifest["name"] = name
            changed.append("name")
        if company_name is not None and manifest.get("company_name") != company_name:
            manifest["company_name"] = company_name
            changed.append("company_name")
        if description is not None and manifest.get("description") != description:
            manifest["description"] = description
            changed.append("description")
        if changed:
            _save_yaml(manifest_path, manifest)
        return {"success": True, "errors": [], "changed": changed}

    # ── agent sync ───────────────────────────────────────────────────────────

    def agents_sync(self, scope: str = "both", force: bool = False) -> dict[str, Any]:
        """Sync persona agents into opencode (mirrors ``ai-company exec sync``)."""
        from ai_company.agents.sync import AgentSyncConfig, AgentSyncEngine

        if scope not in ("project", "global", "both"):
            return {
                "success": False,
                "errors": [f"invalid scope: {scope}"],
            }
        try:
            engine = AgentSyncEngine(config=AgentSyncConfig(scope=scope, force=force))
            result = engine.run()
            return {
                "success": not result.errors,
                "errors": list(result.errors),
                "created": list(result.created),
                "updated": list(result.updated),
                "skipped": list(result.skipped),
                "conflicts": list(result.conflicts),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    # ── backup ───────────────────────────────────────────────────────────────

    def backup_create(self, dest_dir: str = "backups") -> dict[str, Any]:
        """Create a timestamped backup archive (mirrors ``python -m ai_company.backup``)."""
        from ai_company.backup.backup import create_backup

        try:
            created = create_backup(dest_dir=dest_dir)
            return {"success": True, "errors": [], "path": str(created)}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "path": None}

    def backup_status(self, limit: int = 10) -> dict[str, Any]:
        """List existing backup archives (newest first) for the R6 tile."""
        from datetime import datetime as _datetime

        backup_dir = Path("backups")
        if not backup_dir.is_dir():
            return {"success": True, "errors": [], "backups": [], "total": 0}
        try:
            archives = sorted(
                backup_dir.glob("*.tar.gz"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError as exc:
            return {"success": False, "errors": [str(exc)], "backups": [], "total": 0}
        return {
            "success": True,
            "errors": [],
            "backups": [
                {
                    "name": path.name,
                    "size_bytes": path.stat().st_size,
                    "modified": _datetime.fromtimestamp(
                        path.stat().st_mtime
                    ).isoformat(),
                }
                for path in archives[:limit]
            ],
            "total": len(archives),
        }

    # ── telemetry (risk R5) ──────────────────────────────────────────────────

    def _read_model_engine(self) -> Any | None:
        """The runtime's ``read_model`` engine, or None (fail-open).

        The read model is registered by the ``initialize_read_model`` startup
        step. A bare facade (tests, runtime not started) has no such engine —
        callers fall back to the JSONL sources, so telemetry never breaks.
        """
        try:
            engine = self._runtime.get_engine_optional("read_model")
        except Exception:
            return None
        if engine is None or not hasattr(engine, "sync"):
            return None
        return engine

    def sync_read_model(self) -> dict[str, Any]:
        """Incrementally sync the SQLite read model from the JSONL sources.

        Fail-open: when the ``read_model`` engine is not registered this is a
        no-op (``synced: False``) and reads fall back to JSONL. When it is,
        rows appended since the last sync are imported (ADR 0004 — the JSONL
        files stay the source of truth; the projection stays current during a
        live session without a restart).
        """
        engine = self._read_model_engine()
        if engine is None:
            return {"synced": False, "reason": "read model engine unavailable"}
        try:
            return {"synced": True, **engine.sync()}
        except Exception as exc:
            logger.debug("Read model sync failed: %s", exc)
            return {"synced": False, "reason": str(exc)}

    def metrics_persist(self) -> dict[str, Any]:
        """Snapshot the current runtime metrics into the persisted history.

        Also syncs the SQLite read model (ADR 0004) from the JSONL sources so
        dashboard reads are served from a projection that stays current during
        a live session. Both steps are fail-open — telemetry never breaks the
        caller's path.
        """
        from ai_company.telemetry.metrics import log_metrics_snapshot

        try:
            snapshot = self.metrics()
            log_metrics_snapshot(snapshot)
            self.sync_read_model()
            return {"success": True, "errors": [], "snapshot": snapshot}
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    def metrics_history_summary(self, limit: int = 100) -> dict[str, Any]:
        """Dashboard summary over persisted metrics snapshots (R5).

        Served from the SQLite read model (ADR 0004) when available — the
        live projection kept current by the periodic sync — falling open to
        the JSONL log so telemetry reads never break.
        """
        engine = self._read_model_engine()
        if engine is not None:
            try:
                summary = engine.metrics_summary(limit=limit)
                summary.setdefault("persistence_enabled", True)
                return {"success": True, "errors": [], "summary": summary}
            except Exception as exc:
                logger.debug("Read model metrics summary failed: %s", exc)

        from ai_company.telemetry.metrics import metrics_summary

        try:
            return {
                "success": True,
                "errors": [],
                "summary": metrics_summary(limit=limit),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "summary": {}}

    def provider_usage_summary(self, limit: int = 500) -> dict[str, Any]:
        """Aggregated provider usage by model (R5 Model Usage panel).

        Served from the SQLite read model (ADR 0004) when available — the
        live projection kept current by the periodic sync — falling open to
        the JSONL log so telemetry reads never break.
        """
        engine = self._read_model_engine()
        if engine is not None:
            try:
                summary = engine.provider_usage_by_model(limit=limit)
                summary.setdefault("persistence_enabled", True)
                return {"success": True, "errors": [], "summary": summary}
            except Exception as exc:
                logger.debug("Read model provider usage failed: %s", exc)

        from ai_company.telemetry.provider import provider_usage_summary

        try:
            return {
                "success": True,
                "errors": [],
                "summary": provider_usage_summary(limit=limit),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "summary": {}}

    def alerts_summary(self, limit: int = 200) -> dict[str, Any]:
        """Current open isolation alerts + recent record tail (sprint 5.4 T3).

        Fail-open JSONL read (``runtime/alerts.jsonl``) — monitoring never
        breaks the API path. The summary collapses repeated isolates per
        component into one open alert until a ``resolved`` record supersedes
        it (alerts resolved on recovery / un-isolation).
        """
        from ai_company.telemetry.alerts import alerts_summary

        try:
            return {
                "success": True,
                "errors": [],
                "summary": alerts_summary(limit=limit),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "summary": {}}

    def retention_status(self) -> dict[str, Any]:
        """Telemetry retention dry-run report (sprint 5.4 T2).

        Reports raw/expired/rollup counts per source under the policies in
        ``config/runtime/telemetry.yaml`` — read-only, never mutates files.
        The `telemetry_retention` scheduler job performs the actual
        rollup-then-truncate apply.
        """
        from ai_company.telemetry.retention import load_policies, retention_summary

        try:
            policies = load_policies(self._section_telemetry())
            return {
                "success": True,
                "errors": [],
                "summary": retention_summary(policies=policies),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "summary": {}}

    def session_telemetry_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Persist one OpenCode session checkpoint (sprint 5.5 P2).

        The endpoint layer already validated the payload against the Pydantic
        body model; this adapter is a thin fail-open call into the telemetry
        module so ingestion never breaks the caller's path.
        """
        from ai_company.telemetry.sessions import record_session_telemetry

        try:
            record_session_telemetry(**record)
            return {
                "success": True,
                "errors": [],
                "session_id": record.get("session_id", ""),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)]}

    def session_telemetry_summary(self, limit: int = 200) -> dict[str, Any]:
        """OpenCode session checkpoints summary (sprint 5.5 P2 Sessions panel).

        Fail-open JSONL read (``runtime/session_telemetry.jsonl``) — telemetry
        reads never break the API path. The newest checkpoint per session is
        reported with aggregate totals, per-model rows, and end-reason counts.
        """
        from ai_company.telemetry.sessions import session_telemetry_summary

        try:
            return {
                "success": True,
                "errors": [],
                "summary": session_telemetry_summary(limit=limit),
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "summary": {}}

    def _section_telemetry(self) -> dict[str, Any]:
        """Return the ``telemetry`` config section (empty when unavailable)."""
        try:
            runtime = getattr(self, "_runtime", None)
            if runtime is None:
                return {}
            section = runtime.runtime_config.section("telemetry")
            return section or {}
        except Exception:
            return {}

    def close(self) -> None:
        """Best-effort graceful shutdown of the runtime (idempotent)."""
        try:
            status = self._runtime.status()
            if status.phase.value not in ("stopped", "failed"):
                self._runtime.stop(reason="server-shutdown")
        except Exception as exc:  # never mask the caller's shutdown path
            logger.debug("Runtime facade close skipped: %s", exc)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
