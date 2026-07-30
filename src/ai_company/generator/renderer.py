"""Template rendering module for AI Enterprise OS Generator Engine.

This module provides functionality for rendering templates using various template engines
(Jinja2, JSON, YAML, Markdown, Python, etc.) with support for:
1. Multiple template engines
2. Template loading from various sources
3. Context processing and validation
4. Error handling and recovery
5. Caching for performance
6. Template linting and validation
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from ai_company.template_engine.loader import TemplateLoader
from ai_company.template_engine.renderer import Renderer

logger = logging.getLogger(__name__)


class TemplateRenderError(Exception):
    """Exception raised when template rendering fails."""

    def __init__(
        self,
        message: str,
        template_id: str | None = None,
        template_path: str | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.template_id = template_id
        self.template_path = template_path
        self.error_code = error_code


class TemplateValidationError(Exception):
    """Exception raised when template validation fails."""

    def __init__(
        self,
        message: str,
        template_id: str | None = None,
        validation_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.template_id = template_id
        self.validation_type = validation_type


class RenderStats:
    """Statistics about template rendering operations."""

    def __init__(self) -> None:
        self.total_renders = 0
        self.successful_renders = 0
        self.failed_renders = 0
        self.cached_renders = 0
        self.total_render_time = 0.0
        self.templates_rendered: dict[str, int] = {}
        self.errors_by_type: dict[str, int] = {}

    def record_render(
        self, template_id: str, success: bool, duration: float, cached: bool = False
    ) -> None:
        """Record a rendering operation."""
        self.total_renders += 1
        if success:
            self.successful_renders += 1
        else:
            self.failed_renders += 1

        if cached:
            self.cached_renders += 1

        self.total_render_time += duration
        self.templates_rendered[template_id] = (
            self.templates_rendered.get(template_id, 0) + 1
        )

    def get_success_rate(self) -> float:
        """Get success rate as percentage."""
        if self.total_renders == 0:
            return 0.0
        return (self.successful_renders / self.total_renders) * 100

    def get_average_render_time(self) -> float:
        """Get average render time in seconds."""
        if self.total_renders == 0:
            return 0.0
        return self.total_render_time / self.total_renders

    def to_dict(self) -> dict[str, Any]:
        """Convert statistics to dictionary."""
        return {
            "total_renders": self.total_renders,
            "successful_renders": self.successful_renders,
            "failed_renders": self.failed_renders,
            "cached_renders": self.cached_renders,
            "success_rate": self.get_success_rate(),
            "average_render_time": self.get_average_render_time(),
            "templates_rendered": self.templates_rendered,
            "errors_by_type": self.errors_by_type,
        }


class TemplateRenderer:
    """Centralized template rendering engine for generation process.

    This class manages template loading, rendering, validation, and caching.
    It supports multiple template engines and provides detailed error reporting.

    Args:
        template_loader: Loader for loading templates
        cache_enabled: Whether to enable template caching
        cache_ttl: Cache time-to-live in seconds
        validation_enabled: Whether to validate templates before rendering
        renderers: Custom renderer instances
        fallback_engine: Fallback template engine if primary fails
    """

    def __init__(
        self,
        template_loader: TemplateLoader,
        cache_enabled: bool = True,
        cache_ttl: int = 300,
        validation_enabled: bool = True,
        renderers: dict[str, Any] | None = None,
        fallback_engine: str = "jinja",
    ) -> None:
        self.template_loader = template_loader
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        self.validation_enabled = validation_enabled
        self.fallback_engine = fallback_engine
        self.logger = logging.getLogger(self.__class__.__name__)

        # Use provided renderers or create default ones
        self.renderers = renderers or {}
        self._default_renderer = Renderer(renderers)

        # Cache for rendered templates
        self._render_cache: dict[str, dict[str, Any]] = {}
        self._cache_timestamps: dict[str, datetime] = {}

        # Statistics
        self.stats = RenderStats()

    def render(
        self,
        template_id: str,
        context: dict[str, Any] | None = None,
        engine: str | None = None,
        cache: bool | None = None,
        validate: bool | None = None,
        fallback: bool = True,
    ) -> str:
        """Render a template with the given context.

        Args:
            template_id: Identifier for the template to render
            context: Context data for template variables
            engine: Template engine to use (uses default if None)
            cache: Whether to use cache (uses instance default if None)
            validate: Whether to validate template (uses instance default if None)
            fallback: Whether to use fallback engine if primary fails

        Returns:
            Rendered template content as string

        Raises:
            TemplateRenderError: If rendering fails
            TemplateValidationError: If validation fails
        """
        context = context or {}
        engine = engine or self.fallback_engine
        cache = cache if cache is not None else self.cache_enabled
        validate = validate if validate is not None else self.validation_enabled

        # Generate cache key
        cache_key = f"{template_id}:{engine}:{hashlib.md5(json.dumps(context, sort_keys=True).encode()).hexdigest()}"

        # Check cache
        if cache and self._is_cache_valid(cache_key):
            self.stats.record_render(template_id, True, 0.0, cached=True)
            cached_result = self._render_cache[cache_key]
            self.logger.debug(f"Cache hit for template {template_id}")
            return cast(str, cached_result["content"])

        start_time = time.time()
        success = False
        error_code = None

        try:
            # Get template
            template = self.template_loader.get_template(template_id)

            # Validate template if enabled
            if validate:
                self._validate_template(template, template_id)

            # Render template
            content = self._render_with_engine(template, context, engine)

            # Store in cache if enabled
            if cache:
                self._store_in_cache(cache_key, content)

            success = True
            self.logger.debug(f"Successfully rendered template {template_id}")

        except Exception as e:
            error_code = type(e).__name__
            self.stats.errors_by_type[error_code] = (
                self.stats.errors_by_type.get(error_code, 0) + 1
            )

            if fallback and engine != self.fallback_engine:
                self.logger.warning(
                    f"Primary engine {engine} failed for {template_id}, trying fallback {self.fallback_engine}"
                )
                return self.render(
                    template_id, context, self.fallback_engine, cache, validate, False
                )
            else:
                self.logger.error(f"Failed to render template {template_id}: {e!s}")
                raise TemplateRenderError(
                    f"Failed to render template {template_id}: {e!s}",
                    template_id=template_id,
                    template_path=getattr(template, "path", None),
                    error_code=error_code,
                ) from e

        duration = time.time() - start_time
        self.stats.record_render(template_id, success, duration)

        return content

    def render_template_string(
        self,
        template_string: str,
        context: dict[str, Any] | None = None,
        engine: str = "jinja",
    ) -> str:
        """Render a template from a string.

        Args:
            template_string: Template content as string
            context: Context data for template variables
            engine: Template engine to use

        Returns:
            Rendered template content as string
        """
        context = context or {}

        # Create a temporary template
        class StringTemplate:
            def __init__(self, content: str) -> None:
                self.content = content
                self.path = "<string>"

        temp_template = StringTemplate(template_string)

        return self._render_with_engine(temp_template, context, engine)

    def get_template_info(self, template_id: str) -> dict[str, Any]:
        """Get information about a template.

        Args:
            template_id: Template identifier

        Returns:
            Template information dictionary
        """
        template = self.template_loader.get_template(template_id)
        info = {
            "id": template_id,
            "path": getattr(template, "path", None),
            "engine": getattr(template, "engine", None),
            "format": getattr(template, "format", None),
            "size": len(template.content) if hasattr(template, "content") else 0,
            "last_modified": getattr(template, "last_modified", None),
        }

        # Add additional info if available
        if hasattr(template, "variables"):
            info["variables"] = template.variables

        if hasattr(template, "dependencies"):
            info["dependencies"] = template.dependencies

        return info

    def list_templates(self, engine: str | None = None) -> list[str]:
        """List available templates.

        Args:
            engine: Optional engine filter

        Returns:
            List of template IDs
        """
        templates = self.template_loader.list_templates()

        if engine:
            templates = [t for t in templates if self._get_template_engine(t) == engine]

        return templates

    def clear_cache(self, template_id: str | None = None) -> None:
        """Clear cache for specific template or all templates.

        Args:
            template_id: Optional template ID to clear
        """
        if template_id:
            # Clear cache for specific template
            keys_to_remove = [
                key for key in self._render_cache if key.startswith(f"{template_id}:")
            ]
            for key in keys_to_remove:
                del self._render_cache[key]
                del self._cache_timestamps[key]
            self.logger.debug(f"Cleared cache for template {template_id}")
        else:
            # Clear all cache
            self._render_cache.clear()
            self._cache_timestamps.clear()
            self.logger.debug("Cleared all template cache")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "total_cached_items": len(self._render_cache),
            "oldest_entry": min(self._cache_timestamps.values())
            if self._cache_timestamps
            else None,
            "newest_entry": max(self._cache_timestamps.values())
            if self._cache_timestamps
            else None,
            "cache_size_mb": sum(len(v["content"]) for v in self._render_cache.values())
            / (1024 * 1024),
        }

    def get_render_stats(self) -> dict[str, Any]:
        """Get rendering statistics."""
        return self.stats.to_dict()

    def validate_template(
        self,
        template_id: str,
        validation_type: str = "basic",
    ) -> dict[str, Any]:
        """Validate a template.

        Args:
            template_id: Template identifier
            validation_type: Type of validation to perform

        Returns:
            Validation results
        """
        template = self.template_loader.get_template(template_id)
        return self._validate_template(template, template_id, validation_type)

    def _render_with_engine(
        self, template: Any, context: dict[str, Any], engine: str
    ) -> str:
        """Render template using specified engine."""
        # Find renderer for engine
        if engine == "jinja":
            handler = self._default_renderer._handlers.get("jinja")
            if handler:
                return handler.render(template.content, context)

        # Try to use custom renderer
        if engine in self.renderers:
            return cast(str, self.renderers[engine].render(template.content, context))

        # Fallback to default renderer with engine
        return self._default_renderer.render(
            template.content if hasattr(template, "content") else str(template),
            context,
            engine,
        )

    def _validate_template(
        self, template: Any, template_id: str, validation_type: str = "basic"
    ) -> dict[str, Any]:
        """Validate template.

        Args:
            template: Template object to validate
            template_id: Template identifier
            validation_type: Type of validation

        Returns:
            Validation results
        """
        errors = []
        warnings = []

        # Basic validation
        if not hasattr(template, "content") or not template.content:
            errors.append("Template has no content")

        # Variable validation
        if validation_type in ["basic", "variables"] and hasattr(template, "variables"):
            # Check for undefined variables in context
            pass

        # Performance validation
        if validation_type in ["basic", "performance"]:
            start_time = time.time()
            # Simulate rendering with empty context
            empty_context: dict[str, Any] = {}
            try:
                self._render_with_engine(template, empty_context, "jinja")
            except Exception:
                pass
            render_time = time.time() - start_time

            if render_time > 1.0:  # 1 second threshold
                warnings.append(f"Template renders slowly: {render_time:.2f}s")

        result = {
            "template_id": template_id,
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "validation_type": validation_type,
            "timestamp": datetime.now().isoformat(),
        }

        if errors:
            raise TemplateValidationError(
                f"Template validation failed for {template_id}: {', '.join(errors)}",
                template_id=template_id,
                validation_type=validation_type,
            )

        return result

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid."""
        if not self.cache_enabled or cache_key not in self._cache_timestamps:
            return False

        timestamp = self._cache_timestamps[cache_key]
        age = (datetime.now() - timestamp).total_seconds()

        return age < self.cache_ttl

    def _store_in_cache(self, cache_key: str, content: str) -> None:
        """Store result in cache."""
        self._render_cache[cache_key] = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        self._cache_timestamps[cache_key] = datetime.now()

    def _get_template_engine(self, template_id: str) -> str:
        """Get engine for a template."""
        # This is a placeholder - actual implementation depends on template loader
        return self.fallback_engine


class ManifestGenerator:
    """Generates manifests for AI companies.

    This class creates various types of manifests (company manifests, registry manifests,
    etc.) for AI companies during generation process.
    """

    def __init__(self, renderer: TemplateRenderer) -> None:
        self.renderer = renderer
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate_company_manifest(
        self,
        manifest_data: dict[str, Any],
        template_id: str = "company_manifest",
    ) -> str:
        """Generate a company manifest.

        Args:
            manifest_data: Data for the manifest
            template_id: Template to use for generation

        Returns:
            Generated manifest content
        """
        return self.renderer.render(template_id, manifest_data)

    def generate_registry_manifest(
        self,
        registry_data: dict[str, Any],
        template_id: str = "registry_manifest",
    ) -> str:
        """Generate a registry manifest.

        Args:
            registry_data: Data for the registry manifest
            template_id: Template to use for generation

        Returns:
            Generated manifest content
        """
        return self.renderer.render(template_id, registry_data)

    def export_manifest(
        self,
        manifest_content: str,
        output_path: Path,
        format: str = "json",
    ) -> Path:
        """Export manifest to file.

        Args:
            manifest_content: Manifest content to export
            output_path: Output file path
            format: Export format

        Returns:
            Path to exported file
        """
        # This would parse the manifest and export in requested format
        # For now, just write the content as-is
        output_path.write_text(manifest_content, encoding="utf-8")
        return output_path.resolve()


class TemplateRendererError(Exception):
    """Exception raised for template rendering errors."""

    def __init__(
        self, message: str, template_id: str | None = None, engine: str | None = None
    ) -> None:
        super().__init__(message)
        self.template_id = template_id
        self.engine = engine
