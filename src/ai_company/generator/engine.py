"""Generator engine for AI Enterprise OS.

This module implements the Generator Engine that builds dependencies-aware generation
plans, executes generation tasks, and manages the complete artifact generation
process for AI-native companies.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_company.generator.context import GeneratorContext
from ai_company.generator.dependency import DependencyResolver
from ai_company.generator.planner import GenerationPlan, GenerationPlanner

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class GenerationConfig:
    """Configuration for generation process."""

    def __init__(
        self,
        output_dir: Path | None = None,
        templates_dir: Path | None = None,
        company_dir: Path | None = None,
        config_dir: Path | None = None,
        dry_run: bool = False,
        incremental: bool = False,
        custom_templates: list[str] | None = None,
        max_workers: int = 4,
        timeout: int = 3600,
        enable_checksums: bool = True,
        backup_existing: bool = True,
        validation_enabled: bool = True,
        rollback_enabled: bool = True,
    ) -> None:
        self.output_dir = output_dir or Path("generated")
        self.templates_dir = templates_dir or Path("templates")
        self.company_dir = company_dir or Path("company")
        self.config_dir = config_dir or Path("config/company")
        self.dry_run = dry_run
        self.incremental = incremental
        self.custom_templates = custom_templates or []
        self.max_workers = max_workers
        self.timeout = timeout
        self.enable_checksums = enable_checksums
        self.backup_existing = backup_existing
        self.validation_enabled = validation_enabled
        self.rollback_enabled = rollback_enabled


class GenerationStep:
    """Represents a single step in the generation process."""

    def __init__(
        self,
        step_id: str,
        description: str,
        task_type: str,
        dependencies: list[str],
        name: str = "",
        priority: int = 0,
        retry_count: int = 0,
        max_retries: int = 3,
    ) -> None:
        self.step_id = step_id
        self.description = description
        self.task_type = task_type
        self.name = name
        self.dependencies = dependencies
        self.priority = priority
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.status: str = "pending"
        self.error_message: str | None = None


class GenerationStatus:
    """Tracks the status of a generation process."""

    def __init__(self, plan_id: str) -> None:
        self.plan_id = plan_id
        self.current_step = 0
        self.total_steps = 0
        self.completed_steps: list[str] = []
        self.failed_steps: list[str] = []
        self.skipped_steps: list[str] = []
        self.started_at = datetime.now()
        self.completed_at: datetime | None = None
        self.total_duration: float = 0.0
        self.status: str = "running"
        self.error_message: str | None = None
        self.checksums: dict[str, str] = {}
        self.rollback_data: dict[str, Any] = {}


class GeneratorEngine:
    """Core engine for generating AI company artifacts.

    This engine:
    1. Loads the company registry and validates the data
    2. Creates a dependency-aware generation plan
    3. Executes generation tasks in the correct order
    4. Supports dry-run and incremental generation
    5. Tracks progress and generates checksums
    6. Supports rollback on failure
    7. Logs all operations for auditing

    Args:
        config: Generator configuration
        context: Generator context with manifest and registry
        planner: Generation planner for creating execution plans
        dependency_resolver: Resolver for task dependencies
        checksum_provider: Optional checksum provider for file verification
    """

    def __init__(
        self,
        config: GenerationConfig,
        context: GeneratorContext,
        planner: GenerationPlanner,
        dependency_resolver: DependencyResolver | None = None,
        checksum_provider: Any | None = None,
    ) -> None:
        self.config = config
        self.context = context
        self.planner = planner
        self.dependency_resolver = dependency_resolver or DependencyResolver()
        self.checksum_provider = checksum_provider or self._default_checksum_provider
        self.logger = logging.getLogger(self.__class__.__name__)
        self.status: GenerationStatus | None = None
        self.current_plan: GenerationPlan | None = None

        # Ensure directories exist
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.templates_dir.mkdir(parents=True, exist_ok=True)
        self.config.company_dir.mkdir(parents=True, exist_ok=True)
        self.config.config_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        plan_overrides: dict[str, Any] | None = None,
        callbacks: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the complete generation process.

        Args:
            plan_overrides: Dictionary of plan parameters to override defaults
            callbacks: Dictionary of callback functions for various events

        Returns:
            Dictionary with generation results including:
            - plan_id: Unique identifier for the generation run
            - status: Overall generation status
            - plan: Generation plan details
            - steps: Generated file paths and locations
            - duration: Total generation time
            - checksums: File checksums if enabled
            - metadata: Additional generation metadata
        """
        plan_id = f"generation_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]}"

        try:
            # Initialize status tracking
            self.status = GenerationStatus(plan_id)

            # Update plan with overrides
            if plan_overrides:
                self._apply_plan_overrides(plan_overrides)

            # Create generation plan
            self.current_plan = self.planner.create_plan(
                dry_run=self.config.dry_run,
                incremental=self.config.incremental,
            )

            # Validate plan
            if self.config.validation_enabled:
                plan_errors = self.current_plan.validate()
                if plan_errors:
                    raise ValueError(f"Plan validation errors: {plan_errors}")

            # Load checksums for incremental generation
            if self.config.incremental:
                self._load_checksums()

            # Execute generation
            execution_result = self._execute_plan(plan_id, callbacks)

            # Generate final checksums
            if self.config.enable_checksums:
                self._generate_checksums()

            # Update and return result
            self.status.completed_at = datetime.now()
            self.status.total_duration = (
                self.status.completed_at - self.status.started_at
            ).total_seconds()

            result = {
                "plan_id": plan_id,
                "status": "completed",
                "duration": self.status.total_duration,
                "plan": self._serialize_plan() if self.current_plan else {},
                "steps": execution_result.get("steps", []),
                "checksums": self.status.checksums
                if self.config.enable_checksums
                else {},
                "metadata": {
                    "output_dir": str(self.config.output_dir),
                    "dry_run": self.config.dry_run,
                    "incremental": self.config.incremental,
                    "generated_at": self.status.started_at.isoformat(),
                    "completed_at": self.status.completed_at.isoformat()
                    if self.status.completed_at
                    else None,
                },
            }

            self.logger.info(f"Generation completed: {plan_id}")
            return result

        except Exception as e:
            self.logger.error(f"Generation failed: {str(e)}")

            # Perform rollback if enabled
            if self.config.rollback_enabled and self.status:
                self._rollback(plan_id)

            result = {
                "plan_id": plan_id,
                "status": "failed",
                "error": str(e),
                "duration": (datetime.now() - self.status.started_at).total_seconds()
                if self.status
                else 0,
                "plan": self._serialize_plan() if self.current_plan else {},
                "failed_at": datetime.now().isoformat(),
                "rollback_performed": bool(
                    self.config.rollback_enabled and self.status
                ),
                "metadata": {
                    "output_dir": str(self.config.output_dir),
                    "dry_run": self.config.dry_run,
                    "incremental": self.config.incremental,
                },
            }

            raise

    def _execute_plan(
        self, plan_id: str, callbacks: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Execute the generation plan step by step."""
        if not self.current_plan or not self.status:
            return {"steps": []}

        steps = []
        execution_order = self.current_plan.execution_order
        self.status.total_steps = len(execution_order)

        for step_id in execution_order:
            self.status.current_step += 1
            step_result = self._execute_step(step_id, plan_id)
            steps.append(step_result)

            # Callbacks
            if callbacks:
                self._call_callbacks(callbacks, step_id, step_result)

        return {"steps": steps}

    def _execute_step(self, step_id: str, plan_id: str) -> dict[str, Any]:
        """Execute a single generation step."""
        if not self.current_plan:
            return {"step_id": step_id, "status": "skipped", "error": "No plan"}

        assert self.status is not None

        task = self.current_plan.get_task(step_id)
        if not task:
            return {"step_id": step_id, "status": "skipped", "error": "Task not found"}

        step = GenerationStep(
            step_id=step_id,
            description=f"{task.task_type}: {task.name}",
            task_type=task.task_type,
            name=task.name,
            dependencies=task.dependencies,
            priority=task.priority,
            retry_count=0,
            max_retries=3,
        )

        self.logger.info(
            f"Executing step {self.status.current_step}/{self.status.total_steps}: {step.description}"
        )

        # Check if dry run
        if self.config.dry_run:
            result = self._dry_run_step(step)
            self._update_status(step_id, "completed", None)
            return result

        # Check if incremental and file unchanged
        if self.config.incremental and self._should_skip_step(step):
            result = self._skip_step(step)
            self._update_status(step_id, "skipped", None)
            return result

        # Execute with retry logic
        max_retries = step.max_retries
        last_error: str | None = None

        for attempt in range(max_retries + 1):
            try:
                step.retry_count = attempt
                start_time = time.time()
                step.start_time = datetime.now()
                step.status = "running"

                # Update status
                self._update_status(step_id, "running", None)

                # Execute actual generation
                result = self._generate_step(step)

                # Calculate duration
                end_time = time.time()
                step.end_time = datetime.now()
                step.status = "completed"

                # Update status
                self._update_status(step_id, "completed", None)

                self.logger.info(f"Step {step_id} completed successfully")

                return {
                    "step_id": step_id,
                    "status": "completed",
                    "result": result,
                    "duration": end_time - start_time,
                    "attempt": attempt,
                    "output": result.get("output_path"),
                }

            except Exception as e:
                last_error = str(e)
                self.logger.error(
                    f"Step {step_id} failed (attempt {attempt + 1}/{max_retries + 1}): {last_error}"
                )

                step.status = "failed"
                self._update_status(step_id, "failed", last_error)

                if attempt < max_retries:
                    self.logger.info(f"Retrying step {step_id}...")
                    time.sleep(1)  # Brief pause before retry

        # All retries failed
        self.logger.error(f"Step {step_id} failed after all retries")
        return {
            "step_id": step_id,
            "status": "failed",
            "error": last_error,
            "attempts": step.retry_count,
        }

    def _generate_step(self, step: GenerationStep) -> dict[str, Any]:
        """Generate content for a single step."""
        step_type = step.task_type
        step_name = step.name

        # This would call the actual generation logic based on step type
        # For now, return a placeholder result
        result = {
            "content": f"Generated content for {step_type}: {step_name}",
            "template": f"{step_type}.template",
            "context": {"name": step_name, "type": step_type},
        }

        # In a real implementation, this would:
        # 1. Load the appropriate template
        # 2. Prepare context using self.context
        # 3. Render the template using self.context.renderer
        # 4. Write the output using self.context.writer

        return result

    def _dry_run_step(self, step: GenerationStep) -> dict[str, Any]:
        """Simulate generation for dry run."""
        self.logger.info(f"[DRY RUN] Would generate step: {step.description}")
        return {
            "step_id": step.step_id,
            "status": "dry_run",
            "preview": {"type": step.task_type, "name": step.name},
        }

    def _skip_step(self, step: GenerationStep) -> dict[str, Any]:
        """Skip a step that would produce unchanged output."""
        self.logger.info(f"Skipping step (incremental generation): {step.description}")
        return {
            "step_id": step.step_id,
            "status": "skipped",
            "reason": "File unchanged (incremental generation)",
        }

    def _should_skip_step(self, step: GenerationStep) -> bool:
        """Check if a step should be skipped based on incremental generation."""
        # This would check if the output file exists and is up-to-date
        # For now, return False
        return False

    def _load_checksums(self) -> None:
        """Load existing checksums for incremental generation."""
        if not self.status:
            return
        checksum_file = self.config.output_dir / "checksums.json"
        if checksum_file.exists():
            try:
                with open(checksum_file, "r") as f:
                    self.status.checksums = json.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to load checksums: {e}")

    def _generate_checksums(self) -> None:
        """Generate checksums for all generated files."""
        if not self.status:
            return

        self.status.checksums = {}

        # Generate checksums for output files
        for output_file in self.config.output_dir.rglob("*"):
            if output_file.is_file():
                checksum = self.checksum_provider(str(output_file))
                self.status.checksums[
                    str(output_file.relative_to(self.config.output_dir))
                ] = checksum

        # Save checksums
        checksum_file = self.config.output_dir / "checksums.json"
        with open(checksum_file, "w") as f:
            json.dump(self.status.checksums, f, indent=2)

    def _rollback(self, plan_id: str) -> dict[str, Any]:
        """Perform rollback if enabled."""
        self.logger.warning(f"Performing rollback for plan {plan_id}")
        # In a real implementation, this would restore files from backup
        # or revert changes to the state
        return {"status": "rollback_completed", "plan_id": plan_id}

    def _update_status(
        self, step_id: str, status: str, error: str | None = None
    ) -> None:
        """Update generation status."""
        if not self.status:
            return

        if status == "running":
            self.status.completed_steps.append(step_id)
        elif status == "failed":
            self.status.failed_steps.append(step_id)
            self.status.error_message = error
        elif status == "skipped":
            self.status.skipped_steps.append(step_id)

    def _call_callbacks(
        self, callbacks: dict[str, Any], step_id: str, result: dict[str, Any]
    ) -> None:
        """Call registered callbacks for step completion."""
        for callback_name, callback in callbacks.items():
            try:
                if callable(callback):
                    callback(step_id, result, self.status)
            except Exception as e:
                self.logger.error(f"Callback {callback_name} failed: {e}")

    def _apply_plan_overrides(self, overrides: dict[str, Any]) -> None:
        """Apply plan overrides to configuration."""
        for key, value in overrides.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

    def _serialize_plan(self) -> dict[str, Any]:
        """Serialize the current plan to a dictionary."""
        if not self.current_plan:
            return {}

        return {
            "plan_id": self.current_plan.__dict__,
            "tasks": {
                task_id: task.__dict__
                for task_id, task in self.current_plan.tasks.items()
            },
            "execution_order": self.current_plan.execution_order,
        }

    def _default_checksum_provider(self, file_path: str) -> str:
        """Default checksum provider using MD5."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def get_status(self) -> dict[str, Any] | None:
        """Get current generation status."""
        if not self.status:
            return None

        return {
            "plan_id": self.status.plan_id,
            "current_step": self.status.current_step,
            "total_steps": self.status.total_steps,
            "completed_steps": len(self.status.completed_steps),
            "failed_steps": len(self.status.failed_steps),
            "skipped_steps": len(self.status.skipped_steps),
            "started_at": self.status.started_at.isoformat(),
            "completed_at": self.status.completed_at.isoformat()
            if self.status.completed_at
            else None,
            "total_duration": self.status.total_duration,
            "steps": {
                "completed": self.status.completed_steps,
                "failed": self.status.failed_steps,
                "skipped": self.status.skipped_steps,
            },
        }

    def cancel(self) -> dict[str, Any]:
        """Cancel the current generation process."""
        if not self.status or self.status.status == "completed":
            return {
                "status": "not_running",
                "message": "No active generation to cancel",
            }

        self.status.status = "cancelled"
        self.logger.info("Generation cancelled by user")

        return {
            "status": "cancelled",
            "cancelled_at": datetime.now().isoformat(),
            "completed_steps": self.status.completed_steps,
            "failed_steps": self.status.failed_steps,
        }


class ChecksumError(Exception):
    """Exception raised when checksum validation fails."""

    def __init__(self, message: str, file_path: str | None = None) -> None:
        super().__init__(message)
        self.file_path = file_path


class GenerationError(Exception):
    """Exception raised during generation process errors."""

    def __init__(self, message: str, step_id: str | None = None) -> None:
        super().__init__(message)
        self.step_id = step_id
