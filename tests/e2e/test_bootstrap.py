from ai_company.bootstrap.bootstrap import BootstrapGenerator


class TestE2EBootstrap:
    def test_bootstrap_success(self) -> None:
        gen = BootstrapGenerator()
        result = gen.run()
        assert result.success, f"Bootstrap failed: {result.errors}"
        assert len(result.errors) == 0

    def test_bootstrap_creates_files(self) -> None:
        gen = BootstrapGenerator()
        result = gen.run()
        assert len(result.created_files) > 0, "No files created by bootstrap"

    def test_bootstrap_generated_readme(self) -> None:
        gen = BootstrapGenerator()
        result = gen.run()
        assert any("README.md" in f for f in result.created_files)

    def test_bootstrap_generated_docs(self) -> None:
        gen = BootstrapGenerator()
        result = gen.run()
        assert any("docs" in f for f in result.created_files)

    def test_bootstrap_generated_prompts(self) -> None:
        gen = BootstrapGenerator()
        result = gen.run()
        assert any("prompts" in f for f in result.created_files)

    def test_bootstrap_is_idempotent(self) -> None:
        gen = BootstrapGenerator()
        r1 = gen.run()
        r2 = gen.run()
        assert r1.success and r2.success

    def test_bootstrap_registry_loaded(self) -> None:
        gen = BootstrapGenerator()
        result = gen.run()
        assert result.registry_result is not None
        assert result.registry_result.success
        assert result.registry_result.registry is not None

    def test_bootstrap_fails_on_missing_manifest(self, tmp_path) -> None:
        gen = BootstrapGenerator(
            company_dir=tmp_path,
            manifest_path=tmp_path / "nonexistent.yaml",
            templates_dir=tmp_path,
            output_dir=tmp_path / "out",
        )
        result = gen.run()
        assert not result.success
        assert len(result.errors) > 0

    def test_bootstrap_returns_warnings(self) -> None:
        gen = BootstrapGenerator()
        result = gen.run()
        assert hasattr(result, "warnings")
