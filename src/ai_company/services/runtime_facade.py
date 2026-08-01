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
        """Runtime status view (phase, engines, processes, active counts)."""
        return self._runtime.status().model_dump(mode="json")

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

        owns = engine is None
        try:
            engine = engine or OrchestrationEngine()
            records = engine.history(plan_id)[:limit]
            return {
                "success": True,
                "errors": [],
                "count": len(records),
                "records": [r.model_dump(mode="json") for r in records],
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

        try:
            command_map = load_command_map()
            return {
                "success": True,
                "errors": [],
                "targets": [
                    {
                        "key": key,
                        "description": entry.description,
                        "agent": entry.agent,
                        "model": entry.model,
                        "prompt_file": entry.prompt_file,
                    }
                    for key, entry in sorted(command_map.items())
                ],
            }
        except Exception as exc:
            return {"success": False, "errors": [str(exc)], "targets": []}

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
