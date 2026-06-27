from unittest.mock import MagicMock, patch

import pytest

from apps.core.llm.client import (
    AnthropicProvider,
    BaseLLMProvider,
    LLMClient,
    LLMProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
    ProviderFactory,
    get_provider_from_settings,
)


@pytest.mark.django_db
class TestProviderFactory:
    """Test cases for ProviderFactory"""

    def test_create_openai_provider(self):
        """Test creating OpenAI provider"""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("django.conf.settings.OPENAI_API_KEY", "test-key"):
                provider = ProviderFactory.create(LLMProvider.OPENAI)
                assert isinstance(provider, OpenAIProvider)
                assert provider.provider_name == LLMProvider.OPENAI

    def test_create_anthropic_provider(self):
        """Test creating Anthropic provider"""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("django.conf.settings.ANTHROPIC_API_KEY", "test-key"):
                provider = ProviderFactory.create(LLMProvider.ANTHROPIC)
                assert isinstance(provider, AnthropicProvider)
                assert provider.provider_name == LLMProvider.ANTHROPIC

    def test_create_openrouter_provider(self):
        """Test creating OpenRouter provider"""
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("django.conf.settings.OPENROUTER_API_KEY", "test-key"):
                provider = ProviderFactory.create(LLMProvider.OPENROUTER)
                assert isinstance(provider, OpenRouterProvider)
                assert provider.provider_name == LLMProvider.OPENROUTER

    def test_create_ollama_provider(self):
        """Test creating Ollama provider (no API key needed)"""
        provider = ProviderFactory.create(LLMProvider.OLLAMA)
        assert isinstance(provider, OllamaProvider)
        assert provider.provider_name == LLMProvider.OLLAMA

    def test_create_invalid_provider(self):
        """Test creating invalid provider"""
        with pytest.raises(ValueError, match="Provider ناشناخته"):
            ProviderFactory.create("invalid_provider")

    def test_create_provider_with_custom_model(self):
        """Test creating provider with custom model"""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("django.conf.settings.OPENAI_API_KEY", "test-key"):
                provider = ProviderFactory.create(
                    LLMProvider.OPENAI, model="gpt-4o-mini"
                )
                assert provider.get_model_name() == "gpt-4o-mini"

    def test_register_new_provider(self):
        """Test registering a new provider"""

        class CustomProvider(BaseLLMProvider):
            # ✅ ProviderFactory.create همیشه temperature=0.3 پاس می‌ده
            # بدون **kwargs اینجا → TypeError: CustomProvider() takes no arguments
            def __init__(self, **kwargs):
                pass

            def get_chat_model(self, **kwargs):
                pass

            def get_model_name(self) -> str:
                return "custom"

            @property
            def provider_name(self) -> str:
                return "custom"

        ProviderFactory.register("custom", CustomProvider)
        provider = ProviderFactory.create("custom")
        assert isinstance(provider, CustomProvider)


@pytest.mark.django_db
class TestBaseLLMProvider:
    """Test cases for base LLM provider interface"""

    def test_base_provider_is_abstract(self):
        """Test that base provider cannot be instantiated directly"""
        with pytest.raises(TypeError):
            BaseLLMProvider()

    def test_provider_interface_methods(self):
        """Test that all providers implement required interface"""
        # Test OpenAIProvider
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("django.conf.settings.OPENAI_API_KEY", "test-key"):
                provider = OpenAIProvider()
                assert hasattr(provider, "get_chat_model")
                assert hasattr(provider, "get_model_name")
                assert hasattr(provider, "provider_name")

        # Test AnthropicProvider
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("django.conf.settings.ANTHROPIC_API_KEY", "test-key"):
                provider = AnthropicProvider()
                assert hasattr(provider, "get_chat_model")
                assert hasattr(provider, "get_model_name")
                assert hasattr(provider, "provider_name")

        # Test OpenRouterProvider
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("django.conf.settings.OPENROUTER_API_KEY", "test-key"):
                provider = OpenRouterProvider()
                assert hasattr(provider, "get_chat_model")
                assert hasattr(provider, "get_model_name")
                assert hasattr(provider, "provider_name")

        # Test OllamaProvider
        provider = OllamaProvider()
        assert hasattr(provider, "get_chat_model")
        assert hasattr(provider, "get_model_name")
        assert hasattr(provider, "provider_name")


@pytest.mark.django_db
class TestOpenAIProvider:
    """Test cases for OpenAI provider"""

    def test_init_openai_provider_with_api_key(self):
        """Test initializing OpenAI provider with API key"""
        with patch("django.conf.settings.OPENAI_API_KEY", "test-key"):
            provider = OpenAIProvider()
            assert provider.provider_name == LLMProvider.OPENAI
            assert provider.get_model_name() == "gpt-4o"  # default

    def test_init_openai_provider_without_api_key_raises(self):
        """Test initializing OpenAI provider without API key raises error"""
        with patch("django.conf.settings.OPENAI_API_KEY", None):
            with pytest.raises(
                ValueError, match="OPENAI_API_KEY در settings تنظیم نشده"
            ):
                OpenAIProvider()

    def test_openai_provider_custom_model(self):
        """Test OpenAI provider with custom model"""
        with patch("django.conf.settings.OPENAI_API_KEY", "test-key"):
            provider = OpenAIProvider(model="gpt-4o-mini")
            assert provider.get_model_name() == "gpt-4o-mini"


@pytest.mark.django_db
class TestAnthropicProvider:
    """Test cases for Anthropic provider"""

    def test_init_anthropic_provider_with_api_key(self):
        """Test initializing Anthropic provider with API key"""
        with patch("django.conf.settings.ANTHROPIC_API_KEY", "test-key"):
            provider = AnthropicProvider()
            assert provider.provider_name == LLMProvider.ANTHROPIC
            assert provider.get_model_name() == "claude-sonnet-4-20250514"  # default

    def test_init_anthropic_provider_without_api_key_raises(self):
        """Test initializing Anthropic provider without API key raises error"""
        with patch("django.conf.settings.ANTHROPIC_API_KEY", None):
            with pytest.raises(
                ValueError, match="ANTHROPIC_API_KEY در settings تنظیم نشده"
            ):
                AnthropicProvider()


@pytest.mark.django_db
class TestOpenRouterProvider:
    """Test cases for OpenRouter provider"""

    def test_init_openrouter_provider_with_api_key(self):
        """Test initializing OpenRouter provider with API key"""
        with patch("django.conf.settings.OPENROUTER_API_KEY", "test-key"):
            provider = OpenRouterProvider()
            assert provider.provider_name == LLMProvider.OPENROUTER
            assert provider.get_model_name() == "google/gemini-flash-1.5"  # default

    def test_init_openrouter_provider_without_api_key_raises(self):
        """Test initializing OpenRouter provider without API key raises error"""
        with patch("django.conf.settings.OPENROUTER_API_KEY", None):
            with pytest.raises(
                ValueError, match="OPENROUTER_API_KEY در settings تنظیم نشده"
            ):
                OpenRouterProvider()


@pytest.mark.django_db
class TestOllamaProvider:
    """Test cases for Ollama provider"""

    def test_init_ollama_provider_no_api_key_needed(self):
        """Test initializing Ollama provider (no API key required)"""
        provider = OllamaProvider()
        assert provider.provider_name == LLMProvider.OLLAMA
        assert provider.get_model_name() == "llama3.2:3b"  # default

    def test_ollama_provider_custom_base_url(self):
        """Test Ollama provider with custom base URL"""
        provider = OllamaProvider(base_url="http://custom:11434")
        assert provider._base_url == "http://custom:11434"


@pytest.mark.django_db
class TestLLMClient:
    """Test cases for LLMClient"""

    @patch("apps.core.llm.client.ProviderFactory.create")
    def test_llm_client_initialization(self, mock_create):
        """Test LLMClient initialization"""
        mock_provider = MagicMock(spec=BaseLLMProvider)
        mock_provider.provider_name = LLMProvider.OPENAI
        mock_provider.get_model_name.return_value = "gpt-4o"
        mock_create.return_value = mock_provider

        with patch("django.conf.settings.LLM_PROVIDER", LLMProvider.OPENAI):
            with patch("django.conf.settings.LLM_MODEL", None):
                client = LLMClient()
                assert client._provider_instance == mock_provider
                mock_create.assert_called_once_with(
                    provider=LLMProvider.OPENAI,
                    model=None,
                    temperature=0.3,
                )

    @patch("apps.core.llm.client.ProviderFactory.create")
    def test_llm_client_with_explicit_provider(self, mock_create):
        """Test LLMClient with explicit provider"""
        mock_provider = MagicMock(spec=BaseLLMProvider)
        mock_provider.provider_name = LLMProvider.OPENROUTER
        mock_provider.get_model_name.return_value = "google/gemini-flash-1.5"
        mock_create.return_value = mock_provider

        client = LLMClient(provider="openrouter", model="google/gemini-flash-1.5")
        assert client._provider_instance == mock_provider
        mock_create.assert_called_once_with(
            provider="openrouter",
            model="google/gemini-flash-1.5",
            temperature=0.3,
        )

    @patch("apps.core.llm.client.LLMClient._get_default")
    def test_evaluate_default_class_method(self, mock_get_default):
        """Test LLMClient.evaluate_default class method"""
        mock_client = MagicMock()
        mock_client.evaluate.return_value = {"score": 8.5, "feedback": "Good"}
        mock_get_default.return_value = mock_client

        context = {
            "question_text": "What is Django?",
            "reference_answer": "Django is a web framework",
            "user_answer": "Django is a Python web framework",
        }
        result = LLMClient.evaluate_default(context)

        assert result == {"score": 8.5, "feedback": "Good"}
        mock_client.evaluate.assert_called_once_with(context)

    @patch("apps.core.llm.client.LLMClient._get_default")
    def test_generate_default_report_summary_class_method(self, mock_get_default):
        """Test LLMClient.generate_default_report_summary class method"""
        mock_client = MagicMock()
        mock_client.generate_report_summary.return_value = {"summary": "Test report"}
        mock_get_default.return_value = mock_client

        session_data = {"session_uuid": "test-uuid"}
        result = LLMClient.generate_default_report_summary(session_data)

        assert result == {"summary": "Test report"}
        mock_client.generate_report_summary.assert_called_once_with(session_data)


@pytest.mark.django_db
class TestLLMProviderEnum:
    """Test cases for LLMProvider enum"""

    def test_provider_values(self):
        """Test provider enum values"""
        assert LLMProvider.OPENAI == "openai"
        assert LLMProvider.ANTHROPIC == "anthropic"
        assert LLMProvider.OPENROUTER == "openrouter"
        assert LLMProvider.OLLAMA == "ollama"

    def test_provider_enum_in_factory(self):
        """Test that all enum values are registered in factory"""
        for provider in LLMProvider:
            assert provider.value in ProviderFactory._registry


@pytest.mark.django_db
class TestGetProviderFromSettings:
    """Test cases for get_provider_from_settings helper"""

    @patch("django.conf.settings.LLM_PROVIDER", "openrouter")
    def test_get_provider_from_settings(self):
        """Test getting provider from settings"""
        provider = get_provider_from_settings()
        assert provider == "openrouter"

    def test_get_provider_from_settings_default(self):
        """Test default provider when LLM_PROVIDER is not in settings"""
        with patch("django.conf.settings") as mock_settings:
            del mock_settings.LLM_PROVIDER
            provider = get_provider_from_settings()
            assert provider == LLMProvider.OPENAI
