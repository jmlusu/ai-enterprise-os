from typer.testing import CliRunner

from ai_company.cli.main import app

runner = CliRunner()


class TestE2ECLI:
    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ["bootstrap", "build", "generate", "validate", "doctor"]:
            assert cmd in result.stdout

    def test_bootstrap(self) -> None:
        result = runner.invoke(app, ["bootstrap"])
        assert result.exit_code == 0
        assert "Bootstrapping" in result.stdout

    def test_build(self) -> None:
        result = runner.invoke(app, ["build"])
        assert result.exit_code == 0
        assert "Building" in result.stdout

    def test_validate(self) -> None:
        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0
        assert "Validating" in result.stdout

    def test_doctor(self) -> None:
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "diagnostics" in result.stdout.lower()

    def test_targets(self) -> None:
        result = runner.invoke(app, ["targets"])
        assert result.exit_code == 0

    def test_status(self) -> None:
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Status" in result.stdout or "status" in result.stdout.lower()

    def test_generate_dry_run(self) -> None:
        result = runner.invoke(app, ["generate", "bootstrap", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry run" in result.stdout

    def test_generate_unknown_target(self) -> None:
        result = runner.invoke(app, ["generate", "nonexistent", "--dry-run"])
        assert result.exit_code == 1

    def test_registry_list(self) -> None:
        result = runner.invoke(app, ["registry", "list"])
        assert result.exit_code == 0

    def test_registry_show(self) -> None:
        result = runner.invoke(app, ["registry", "show", "vision"])
        assert result.exit_code == 0

    def test_memory_show(self) -> None:
        result = runner.invoke(app, ["memory", "show"])
        assert result.exit_code == 0

    def test_graph_show(self) -> None:
        result = runner.invoke(app, ["graph", "show"])
        assert result.exit_code == 0

    def test_graph_stats(self) -> None:
        result = runner.invoke(app, ["graph", "stats"])
        assert result.exit_code == 0

    def test_report_summary(self) -> None:
        result = runner.invoke(app, ["report", "generate", "summary"])
        assert result.exit_code == 0

    def test_exec_commands(self) -> None:
        result = runner.invoke(app, ["exec", "--help"])
        assert result.exit_code == 0
