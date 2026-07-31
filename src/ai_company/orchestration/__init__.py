"""Enterprise Orchestration Engine for AI Enterprise OS.

The orchestration engine acts as the COO: it plans declarative pipelines,
schedules them (immediate / scheduled / recurring / dependency), executes
tasks through a coordinator that dispatches to the Registry, Bootstrap,
Generator, Workflow, Decision, Memory, Event Bus, Graph, Reporting, and
Audit engines, and provides checkpoint, rollback, and recovery so runs
survive failure and interruption.

Key entry point: :class:`OrchestrationEngine`.

Public components:

- :class:`OrchestrationEngine` — facade / COO.
- :class:`~ai_company.orchestration.coordinator.Coordinator` — task dispatch.
- :class:`~ai_company.orchestration.planner.PipelinePlanner` — declarative planning.
- :class:`~ai_company.orchestration.scheduler.OrchestrationScheduler` — scheduling.
- :class:`~ai_company.orchestration.pipeline.PipelineRunner` — stage execution.
- :class:`~ai_company.orchestration.checkpoint.CheckpointManager` — snapshots.
- :class:`~ai_company.orchestration.rollback.RollbackManager` — undo steps.
- :class:`~ai_company.orchestration.recovery.RecoveryManager` — recovery.
- Models live in :mod:`ai_company.orchestration.models`.
"""

from ai_company.orchestration.checkpoint import CheckpointManager
from ai_company.orchestration.config import load_all_orchestration_configs
from ai_company.orchestration.coordinator import Coordinator, default_coordinator
from ai_company.orchestration.dependencies import DependencyGraph
from ai_company.orchestration.engine import OrchestrationEngine
from ai_company.orchestration.executor import TaskExecutor, TaskResult
from ai_company.orchestration.health import HealthChecker
from ai_company.orchestration.metrics import MetricsCollector
from ai_company.orchestration.models import (
    Checkpoint,
    EngineStatus,
    ExecutionMetrics,
    ExecutionRecord,
    ExecutionState,
    HealthStatus,
    OrchestrationPlan,
    Pipeline,
    PipelineStage,
    PipelineStatus,
    PipelineTask,
    RecoveryAction,
    RecoveryResult,
    RetryPolicy,
    RollbackPlan,
    RollbackStep,
    ScheduleMode,
    StageMode,
    TaskDependency,
    TaskStatus,
)
from ai_company.orchestration.monitoring import Monitor
from ai_company.orchestration.notifications import Notifier
from ai_company.orchestration.pipeline import PipelineResult, PipelineRunner
from ai_company.orchestration.planner import PipelinePlanner
from ai_company.orchestration.recovery import RecoveryManager
from ai_company.orchestration.rollback import RollbackManager
from ai_company.orchestration.scheduler import OrchestrationScheduler
from ai_company.orchestration.state import ExecutionStateStore

__all__ = [
    "Checkpoint",
    "CheckpointManager",
    "Coordinator",
    "DependencyGraph",
    "EngineStatus",
    "ExecutionMetrics",
    "ExecutionRecord",
    "ExecutionState",
    "ExecutionStateStore",
    "HealthChecker",
    "HealthStatus",
    "MetricsCollector",
    "Monitor",
    "Notifier",
    "OrchestrationEngine",
    "OrchestrationPlan",
    "OrchestrationScheduler",
    "Pipeline",
    "PipelinePlanner",
    "PipelineResult",
    "PipelineRunner",
    "PipelineStage",
    "PipelineStatus",
    "PipelineTask",
    "RecoveryAction",
    "RecoveryManager",
    "RecoveryResult",
    "RetryPolicy",
    "RollbackManager",
    "RollbackPlan",
    "RollbackStep",
    "ScheduleMode",
    "StageMode",
    "TaskDependency",
    "TaskExecutor",
    "TaskResult",
    "TaskStatus",
    "default_coordinator",
    "load_all_orchestration_configs",
]
