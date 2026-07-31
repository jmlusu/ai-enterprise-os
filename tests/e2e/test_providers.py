"""Provider integration tests — validates all provider backends."""

import pytest
from ai_company.providers.base import (
    BaseProvider,
    ChatMessage,
    CompletionResult,
    ProviderConfig,
)
from ai_company.providers.factory import ProviderFactory
from ai_company.providers.mock import MockProvider
from ai_company.providers.registry import ProviderRegistry


class TestE2EProviders:
    def test_base_provider_abstract_methods(self) -> None:
        with pytest.raises(TypeError):
            BaseProvider()

    def test_mock_provider_creates(self) -> None:
        p = MockProvider()
        assert p is not None

    def test_mock_provider_complete(self) -> None:
        p = MockProvider()
        result = p.complete("test prompt")
        assert isinstance(result, CompletionResult)
        assert "mock" in result.content.lower()

    def test_mock_provider_chat(self) -> None:
        p = MockProvider()
        msg = ChatMessage(role="user", content="hello")
        result = p.chat([msg])
        assert isinstance(result, CompletionResult)
        assert result.content is not None

    def test_mock_provider_embed(self) -> None:
        p = MockProvider()
        embeddings = p.embed(["text1", "text2"])
        assert len(embeddings) == 2
        assert all(len(e) == 3 for e in embeddings)

    def test_mock_provider_health(self) -> None:
        p = MockProvider()
        assert p.check_health() is True

    def test_mock_provider_config(self) -> None:
        cfg = ProviderConfig(model="test-model", temperature=0.5)
        p = MockProvider(config=cfg)
        assert p.config.model == "test-model"
        assert p.config.temperature == 0.5

    def test_mock_provider_default_config(self) -> None:
        p = MockProvider()
        assert isinstance(p.config, ProviderConfig)
        assert p.config.model == "default"

    def test_mock_provider_set_mock_response(self) -> None:
        p = MockProvider()
        p.set_mock_response("custom response")
        result = p.complete("any prompt")
        assert "custom response" in result.content

    def test_provider_factory_creates_mock(self) -> None:
        factory = ProviderFactory()
        p = factory.create("mock")
        assert isinstance(p, MockProvider)

    def test_provider_factory_creates_with_config(self) -> None:
        factory = ProviderFactory()
        cfg = ProviderConfig(model="custom-model")
        p = factory.create("mock", cfg)
        assert p.config.model == "custom-model"

    def test_provider_factory_raises_on_unknown(self) -> None:
        factory = ProviderFactory()
        with pytest.raises(ValueError):
            factory.create("nonexistent")

    def test_provider_factory_list_supported(self) -> None:
        factory = ProviderFactory()
        providers = factory.list_supported()
        assert "mock" in providers

    def test_provider_factory_register_provider(self) -> None:
        factory = ProviderFactory()
        factory.register_provider("custom", MockProvider)
        assert "custom" in factory.list_supported()

    def test_provider_registry_register_instance(self) -> None:
        r = ProviderRegistry()
        p = MockProvider()
        registered = r.register("test_provider", p)
        assert registered is p

    def test_provider_registry_get_by_name(self) -> None:
        r = ProviderRegistry()
        p = MockProvider()
        r.register("get_test", p)
        assert r.get("get_test") is p

    def test_provider_registry_get_default_when_only_one(self) -> None:
        r = ProviderRegistry()
        r.register("only_provider", MockProvider())
        assert r.get() is not None

    def test_provider_registry_raises_on_missing(self) -> None:
        r = ProviderRegistry()
        with pytest.raises(KeyError):
            r.get("non_existent")

    def test_provider_registry_unregister(self) -> None:
        r = ProviderRegistry()
        r.register("temp_provider", MockProvider())
        r.unregister("temp_provider")
        assert "temp_provider" not in r.list_providers()

    def test_provider_registry_set_default(self) -> None:
        r = ProviderRegistry()
        p = MockProvider()
        r.register("main", p)
        r.set_default("main")
        assert r.get_default_name() == "main"
        assert r.get() is p

    def test_provider_registry_register_with_make_default(self) -> None:
        r = ProviderRegistry()
        r.register("first", MockProvider(), make_default=True)
        assert r.get_default_name() == "first"

    def test_registry_clear(self) -> None:
        r = ProviderRegistry()
        r.register("a", MockProvider())
        r.register("b", MockProvider())
        r.clear()
        assert r.get_default_name() == ""
        assert len(r.list_providers()) == 0

    def test_registry_contains(self) -> None:
        r = ProviderRegistry()
        r.register("existing", MockProvider())
        assert "existing" in r
        assert "nonexistent" not in r

    def test_registry_len(self) -> None:
        r = ProviderRegistry()
        r.register("x", MockProvider())
        r.register("y", MockProvider())
        assert len(r) == 2

    def test_registry_with_string_type(self) -> None:
        r = ProviderRegistry()
        p = r.register("auto_mock", "mock")
        assert isinstance(p, MockProvider)

    def test_multiple_registry_instances_isolated(self) -> None:
        r1 = ProviderRegistry()
        r2 = ProviderRegistry()
        r1.register("only_in_r1", MockProvider())
        assert "only_in_r1" in r1.list_providers()
        assert "only_in_r1" not in r2.list_providers()

    def test_provider_factory_creates_with_dict_config(self) -> None:
        factory = ProviderFactory()
        p = factory.create("mock", {"model": "dict-model"})
        assert p.config.model == "dict-model"

    def test_provider_factory_create_all_supported(self) -> None:
        factory = ProviderFactory()
        for name in factory.list_supported():
            p = factory.create(name)
            assert p is not None

    def test_mock_provider_complete_returns_content(self) -> None:
        p = MockProvider()
        result = p.complete("test")
        assert len(result.content) > 0

    def test_mock_provider_provider_name(self) -> None:
        p = MockProvider()
        assert p.provider_name == "MockProvider"

    def test_mock_provider_is_healthy_property(self) -> None:
        p = MockProvider()
        p.check_health()
        assert p.is_healthy is True

    def test_mock_provider_update_config(self) -> None:
        p = MockProvider()
        new_cfg = ProviderConfig(model="new-model")
        p.update_config(new_cfg)
        assert p.config.model == "new-model"
