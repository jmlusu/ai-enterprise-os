import json
import tempfile
from pathlib import Path

import pytest
import yaml

from ai_company.template_engine import TemplateLoader, TemplateContext, Renderer, Writer
from ai_company.template_engine.handlers import (
    BaseHandler,
    JinjaHandler,
    PythonHandler,
    MarkdownHandler,
    JsonHandler,
    YamlHandler,
    DEFAULT_HANDLERS,
)


class TestTemplateLoader:
    def test_load_from_string(self) -> None:
        loader = TemplateLoader()
        content, fmt = loader.load("Hello {{ name }}")
        assert content == "Hello {{ name }}"
        assert fmt == "jinja"

    def test_load_from_path(self, tmp_path: Path) -> None:
        f = tmp_path / "template.j2"
        f.write_text("Hello {{ name }}", encoding="utf-8")
        loader = TemplateLoader()
        content, fmt = loader.load(f)
        assert content == "Hello {{ name }}"
        assert fmt == "jinja"

    def test_load_from_path_with_search_path(self, tmp_path: Path) -> None:
        d = tmp_path / "templates"
        d.mkdir()
        f = d / "greeting.j2"
        f.write_text("Hi {{ name }}", encoding="utf-8")
        loader = TemplateLoader(search_path=d)
        content, fmt = loader.load("greeting.j2")
        assert content == "Hi {{ name }}"
        assert fmt == "jinja"

    def test_detect_format_by_extension(self) -> None:
        loader = TemplateLoader()
        assert loader.detect_format(Path("t.py")) == "python"
        assert loader.detect_format(Path("t.json")) == "json"
        assert loader.detect_format(Path("t.yaml")) == "yaml"
        assert loader.detect_format(Path("t.yml")) == "yaml"
        assert loader.detect_format(Path("t.md")) == "markdown"
        assert loader.detect_format(Path("t.j2")) == "jinja"
        assert loader.detect_format(Path("t.jinja")) == "jinja"
        assert loader.detect_format(Path("t.jinja2")) == "jinja"
        assert loader.detect_format(Path("t.unknown")) == "jinja"

    def test_load_template_returns_content(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("# {title}", encoding="utf-8")
        loader = TemplateLoader()
        content = loader.load_template(f)
        assert content == "# {title}"

    def test_load_template_from_string(self) -> None:
        loader = TemplateLoader()
        assert loader.load_template("inline content") == "inline content"


class TestTemplateContext:
    def test_create_from_dict(self) -> None:
        ctx = TemplateContext({"name": "World", "count": 42})
        assert ctx.get("name") == "World"
        assert ctx.get("count") == 42

    def test_from_dict_classmethod(self) -> None:
        ctx = TemplateContext.from_dict({"a": 1})
        assert ctx.get("a") == 1

    def test_from_file_yaml(self, tmp_path: Path) -> None:
        f = tmp_path / "ctx.yaml"
        f.write_text("name: Test", encoding="utf-8")
        ctx = TemplateContext.from_file(f)
        assert ctx.get("name") == "Test"

    def test_from_file_json(self, tmp_path: Path) -> None:
        f = tmp_path / "ctx.json"
        f.write_text('{"name": "Test"}', encoding="utf-8")
        ctx = TemplateContext.from_file(f)
        assert ctx.get("name") == "Test"

    def test_from_file_unsupported_format(self, tmp_path: Path) -> None:
        f = tmp_path / "ctx.txt"
        f.write_text("data", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported context file format"):
            TemplateContext.from_file(f)

    def test_get_with_default(self) -> None:
        ctx = TemplateContext({"a": 1})
        assert ctx.get("missing", "fallback") == "fallback"

    def test_get_dotted_key(self) -> None:
        ctx = TemplateContext({"company": {"name": "Acme"}})
        assert ctx.get("company.name") == "Acme"

    def test_get_dotted_key_missing(self) -> None:
        ctx = TemplateContext({"company": {"name": "Acme"}})
        assert ctx.get("company.version", "1.0") == "1.0"

    def test_merge_with_dict(self) -> None:
        a = TemplateContext({"x": 1, "y": 2})
        b = a.merge({"y": 3, "z": 4})
        assert b.get("x") == 1
        assert b.get("y") == 3
        assert b.get("z") == 4

    def test_merge_with_context(self) -> None:
        a = TemplateContext({"a": 1})
        b = TemplateContext({"b": 2})
        c = a.merge(b)
        assert c.get("a") == 1
        assert c.get("b") == 2

    def test_merge_nested(self) -> None:
        a = TemplateContext({"user": {"name": "Alice", "age": 30}})
        b = a.merge({"user": {"name": "Bob"}})
        assert b.get("user.name") == "Bob"
        assert b.get("user.age") == 30

    def test_validate_all_present(self) -> None:
        ctx = TemplateContext({"a": 1, "b": 2})
        assert ctx.validate(["a", "b"]) == []

    def test_validate_missing_keys(self) -> None:
        ctx = TemplateContext({"a": 1})
        missing = ctx.validate(["a", "b", "c"])
        assert missing == ["b", "c"]

    def test_to_dict(self) -> None:
        ctx = TemplateContext({"x": 10})
        assert ctx.to_dict() == {"x": 10}

    def test_keys_and_items(self) -> None:
        ctx = TemplateContext({"a": 1, "b": 2})
        assert ctx.keys() == {"a", "b"}
        assert set(ctx.items()) == {("a", 1), ("b", 2)}


class TestHandlers:
    def test_jinja_handler(self) -> None:
        h = JinjaHandler()
        result = h.render("Hello {{ name }}!", {"name": "World"})
        assert result == "Hello World!"

    def test_jinja_handler_error(self) -> None:
        h = JinjaHandler()
        with pytest.raises(ValueError, match="Jinja2 rendering failed"):
            h.render("{% bad syntax %}", {})

    def test_python_handler(self) -> None:
        h = PythonHandler()
        result = h.render("Hello {name}!", {"name": "World"})
        assert result == "Hello World!"

    def test_python_handler_dotted(self) -> None:
        h = PythonHandler()
        result = h.render("{company.name} v{company.version}", {
            "company": {"name": "Acme", "version": "2.0"}
        })
        assert result == "Acme v2.0"

    def test_python_handler_missing_key(self) -> None:
        h = PythonHandler()
        result = h.render("Hello {name}!", {})
        assert result == "Hello {name}!"

    def test_markdown_handler(self) -> None:
        h = MarkdownHandler()
        result = h.render("# {title}\n\n{body}", {"title": "Doc", "body": "Content"})
        assert result == "# Doc\n\nContent"

    def test_json_handler(self) -> None:
        h = JsonHandler()
        template = '{"name": "{user.name}", "ver": "{version}"}'
        result = h.render(template, {"user": {"name": "Acme"}, "version": 1})
        parsed = json.loads(result)
        assert parsed == {"name": "Acme", "ver": "1"}

    def test_json_handler_invalid(self) -> None:
        h = JsonHandler()
        with pytest.raises(ValueError, match="Invalid JSON template"):
            h.render("{bad json}", {})

    def test_yaml_handler(self) -> None:
        h = YamlHandler()
        template = "name: {project}\nver: {version}"
        result = h.render(template, {"project": "Foo", "version": 2})
        parsed = yaml.safe_load(result)
        assert parsed == {"name": "Foo", "ver": 2}

    def test_yaml_handler_nested(self) -> None:
        h = YamlHandler()
        template = "app:\n  name: {app.name}\n  port: {app.port}"
        result = h.render(template, {"app": {"name": "web", "port": 8080}})
        parsed = yaml.safe_load(result)
        assert parsed == {"app": {"name": "web", "port": 8080}}

    def test_yaml_handler_invalid(self) -> None:
        h = YamlHandler()
        with pytest.raises(ValueError, match="Invalid YAML template"):
            h.render(": bad indent", {})

    def test_default_handlers_registered(self) -> None:
        assert "jinja" in DEFAULT_HANDLERS
        assert "python" in DEFAULT_HANDLERS
        assert "markdown" in DEFAULT_HANDLERS
        assert "json" in DEFAULT_HANDLERS
        assert "yaml" in DEFAULT_HANDLERS

    def test_handler_instantiation(self) -> None:
        for cls in DEFAULT_HANDLERS.values():
            instance = cls()
            assert isinstance(instance, BaseHandler)


class TestRenderer:
    def test_render_jinja(self) -> None:
        r = Renderer()
        result = r.render("Hello {{ name }}!", {"name": "World"}, fmt="jinja")
        assert result == "Hello World!"

    def test_render_python(self) -> None:
        r = Renderer()
        result = r.render("Hello {name}!", {"name": "World"}, fmt="python")
        assert result == "Hello World!"

    def test_render_markdown(self) -> None:
        r = Renderer()
        result = r.render("# {title}", {"title": "Doc"}, fmt="markdown")
        assert result == "# Doc"

    def test_render_json(self) -> None:
        r = Renderer()
        result = r.render('{"msg": "{text}"}', {"text": "hi"}, fmt="json")
        assert json.loads(result) == {"msg": "hi"}

    def test_render_yaml(self) -> None:
        r = Renderer()
        result = r.render("msg: {text}", {"text": "hi"}, fmt="yaml")
        assert yaml.safe_load(result) == {"msg": "hi"}

    def test_unknown_format(self) -> None:
        r = Renderer()
        with pytest.raises(ValueError, match="Unknown format"):
            r.render("content", {}, fmt="nope")

    def test_custom_handlers(self) -> None:
        class UppercaseHandler(BaseHandler):
            def render(self, template: str, context: dict) -> str:
                return template.upper()

        r = Renderer(handlers={"upper": UppercaseHandler})
        result = r.render("hello", {}, fmt="upper")
        assert result == "HELLO"

    def test_register_handler(self) -> None:
        class ReverseHandler(BaseHandler):
            def render(self, template: str, context: dict) -> str:
                return template[::-1]

        r = Renderer()
        r.register_handler("rev", ReverseHandler())
        result = r.render("abc", {}, fmt="rev")
        assert result == "cba"


class TestWriter:
    def test_write_to_file(self, tmp_path: Path) -> None:
        w = Writer()
        dest = tmp_path / "out.txt"
        result = w.write("Hello", dest)
        assert result == dest
        assert dest.read_text(encoding="utf-8") == "Hello"

    def test_write_creates_directories(self, tmp_path: Path) -> None:
        w = Writer()
        dest = tmp_path / "sub" / "deep" / "out.txt"
        result = w.write("nested", dest)
        assert result == dest
        assert dest.read_text(encoding="utf-8") == "nested"

    def test_write_to_stdout(self, capsys: pytest.CaptureFixture) -> None:
        w = Writer()
        result = w.write("Hello stdout")
        assert result == "Hello stdout"
        captured = capsys.readouterr()
        assert captured.out == "Hello stdout\n"


class TestIntegration:
    def test_full_pipeline(self, tmp_path: Path) -> None:
        template_file = tmp_path / "greeting.j2"
        template_file.write_text("Hello {{ name }}!", encoding="utf-8")

        loader = TemplateLoader()
        content, fmt = loader.load(template_file)
        assert fmt == "jinja"

        ctx = TemplateContext.from_dict({"name": "World"})
        assert ctx.get("name") == "World"

        renderer = Renderer()
        output = renderer.render(content, ctx.to_dict(), fmt=fmt)
        assert output == "Hello World!"

        dest = tmp_path / "output.txt"
        writer = Writer()
        written = writer.write(output, dest)
        assert written == dest
        assert dest.read_text(encoding="utf-8") == "Hello World!"

    def test_all_formats_from_context(self) -> None:
        ctx = TemplateContext({"project": "Acme", "version": "1.0"})
        renderer = Renderer()

        jinja_out = renderer.render("Project: {{ project }} v{{ version }}", ctx.to_dict(), fmt="jinja")
        assert jinja_out == "Project: Acme v1.0"

        python_out = renderer.render("Project: {project} v{version}", ctx.to_dict(), fmt="python")
        assert python_out == "Project: Acme v1.0"

        md_out = renderer.render("# {project} v{version}", ctx.to_dict(), fmt="markdown")
        assert md_out == "# Acme v1.0"

        json_out = renderer.render(
            '{"project": "{project}", "version": "{version}"}',
            ctx.to_dict(),
            fmt="json",
        )
        assert json.loads(json_out) == {"project": "Acme", "version": "1.0"}

        yaml_out = renderer.render(
            "project: {project}\nversion: {version}",
            ctx.to_dict(),
            fmt="yaml",
        )
        assert yaml.safe_load(yaml_out) == {"project": "Acme", "version": "1.0"}
