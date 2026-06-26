# apps/core/llm/client.py
# =============================================================================
# LLM Client — Multi-Provider Wrapper
# =============================================================================

import logging
import threading
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# =============================================================================
#  Provider Enum
# =============================================================================

class LLMProvider(str, Enum):
    OPENAI      = "openai"
    ANTHROPIC   = "anthropic"
    OPENROUTER  = "openrouter"
    OLLAMA      = "ollama"       # local — برای dev بدون هزینه


# =============================================================================
#  Base Provider — Interface
# =============================================================================

class BaseLLMProvider(ABC):
    """
    Interface مشترک برای همه providers.
    هر provider باید این متدها رو implement کنه.
    """

    @abstractmethod
    def get_chat_model(self, **kwargs):
        """یه instance از ChatModel برگردون"""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """اسم مدل فعلی"""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...


# =============================================================================
#  OpenAI Provider
# =============================================================================

class OpenAIProvider(BaseLLMProvider):

    def __init__(self, model: str = "gpt-4o", temperature: float = 0.3):
        from django.conf import settings
        self._model       = model
        self._temperature = temperature
        self._api_key = getattr(settings, "OPENAI_API_KEY", None)
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY در settings تنظیم نشده.")

    def get_chat_model(self, **kwargs):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=self._model,
            temperature=kwargs.get("temperature", self._temperature),
            api_key=self._api_key,
            **{k: v for k, v in kwargs.items() if k != "temperature"},
        )

    def get_model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return LLMProvider.OPENAI


# =============================================================================
#  Anthropic Provider
# =============================================================================

class AnthropicProvider(BaseLLMProvider):

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.3,
    ):
        from django.conf import settings
        self._model       = model
        self._temperature = temperature
        self._api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
        if not self._api_key:
            raise ValueError("ANTHROPIC_API_KEY در settings تنظیم نشده.")

    def get_chat_model(self, **kwargs):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=self._model,
            temperature=kwargs.get("temperature", self._temperature),
            anthropic_api_key=self._api_key,
            **{k: v for k, v in kwargs.items() if k != "temperature"},
        )

    def get_model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return LLMProvider.ANTHROPIC


# =============================================================================
#  OpenRouter Provider
#  برای تست — دسترسی به مدل‌های مختلف با یه API key
# =============================================================================

class OpenRouterProvider(BaseLLMProvider):
    """
    OpenRouter به عنوان proxy برای مدل‌های مختلف.
    برای تست ارزون‌تر یا مقایسه مدل‌ها عالیه.

    مدل‌های پیشنهادی:
    - google/gemini-flash-1.5       ← سریع و ارزون
    - meta-llama/llama-3.1-70b      ← open source
    - mistralai/mixtral-8x7b        ← متوازن
    - anthropic/claude-3-haiku      ← سریع claude
    """

    def __init__(
        self,
        model: str = "google/gemini-flash-1.5",
        temperature: float = 0.3,
    ):
        from django.conf import settings
        self._model       = model
        self._temperature = temperature
        self._api_key = getattr(settings, "OPENROUTER_API_KEY", None)
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY در settings تنظیم نشده.")

    def get_chat_model(self, **kwargs):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=self._model,
            temperature=kwargs.get("temperature", self._temperature),
            api_key=self._api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://ai-interviewer.app",
                "X-Title"     : "AI Interviewer",
            },
            **{k: v for k, v in kwargs.items() if k != "temperature"},
        )

    def get_model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return LLMProvider.OPENROUTER


# =============================================================================
#  Ollama Provider
#  برای dev local — کاملاً رایگان
# =============================================================================

class OllamaProvider(BaseLLMProvider):
    """
    Ollama برای اجرای مدل local.
    نیاز به نصب ollama نداره توی docker.

    مدل‌های پیشنهادی:
    - llama3.2:3b   ← سبک، برای dev
    - llama3.1:8b   ← متوازن
    - mistral:7b    ← قوی
    """

    def __init__(
        self,
        model: str = "llama3.2:3b",
        temperature: float = 0.3,
        base_url: str = "http://localhost:11434",
    ):
        self._model       = model
        self._temperature = temperature
        self._base_url    = base_url

    def get_chat_model(self, **kwargs):
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=self._model,
            temperature=kwargs.get("temperature", self._temperature),
            base_url=self._base_url,
        )

    def get_model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return LLMProvider.OLLAMA


# =============================================================================
#  Provider Factory
# =============================================================================

class ProviderFactory:

    _registry: dict[str, type[BaseLLMProvider]] = {
        LLMProvider.OPENAI    : OpenAIProvider,
        LLMProvider.ANTHROPIC : AnthropicProvider,
        LLMProvider.OPENROUTER: OpenRouterProvider,
        LLMProvider.OLLAMA    : OllamaProvider,
    }

    @classmethod
    def create(
        cls,
        provider: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
    ) -> BaseLLMProvider:
        provider_class = cls._registry.get(provider)

        if not provider_class:
            raise ValueError(
                f"Provider ناشناخته: {provider}. "
                f"گزینه‌های معتبر: {list(cls._registry.keys())}"
            )

        kwargs = {"temperature": temperature}
        if model:
            kwargs["model"] = model

        return provider_class(**kwargs)

    @classmethod
    def register(cls, name: str, provider_class: type[BaseLLMProvider]):
        """
        ثبت provider جدید — برای extensibility.

        مثال:
            ProviderFactory.register("groq", GroqProvider)
        """
        cls._registry[name] = provider_class
        logger.info("New LLM provider registered: %s", name)


# =============================================================================
#  LLM Client — Main Interface
# =============================================================================

class LLMClient:
    """
    کلاینت اصلی LLM.
    از settings تشخیص میده کدوم provider رو استفاده کنه.

    استفاده:
        # از services
        from apps.core.llm.client import LLMClient
        result = LLMClient.evaluate(context)

        # با provider خاص (برای تست)
        client = LLMClient(provider="openrouter", model="google/gemini-flash-1.5")
        result = client.evaluate(context)
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
    ):
        from django.conf import settings

        # اگه provider مشخص نشده از settings بخون
        _provider = provider or getattr(settings, "LLM_PROVIDER", LLMProvider.OPENAI)
        _model    = model    or getattr(settings, "LLM_MODEL", None)

        self._provider_instance = ProviderFactory.create(
            provider=_provider,
            model=_model,
            temperature=temperature,
        )

        logger.info(
            "LLMClient initialized | provider=%s | model=%s",
            self._provider_instance.provider_name,
            self._provider_instance.get_model_name(),
        )

    # ── Evaluate Answer ───────────────────────────────────────────────────────

    def evaluate(self, context: dict) -> dict:
        """
        ارزیابی پاسخ کاربر — Structured Output.
        توسط EvaluationService صدا زده میشه.
        """
        from .prompts import build_evaluation_prompt
        from .schemas import EvaluationResult

        prompt = build_evaluation_prompt(
            question_text=context["question_text"],
            reference_answer=context["reference_answer"],
            evaluation_criteria=context.get("evaluation_criteria", {}),
            user_answer=context["user_answer"],
            follow_up_answer=context.get("follow_up_answer", ""),
            seniority_level=context.get("seniority_level", "mid_level"),
            target_position=context.get("target_position", ""),
        )

        llm = self._provider_instance.get_chat_model(temperature=0.1)
        structured_llm = llm.with_structured_output(EvaluationResult)

        logger.debug(
            "Evaluating answer | provider=%s",
            self._provider_instance.provider_name,
        )

        result: EvaluationResult = structured_llm.invoke(prompt)
        return result.model_dump()

    # ── Generate Report Summary ───────────────────────────────────────────────

    def generate_report_summary(self, session_data: dict) -> dict:
        """
        تولید گزارش نهایی — Structured Output.
        توسط ReportService صدا زده میشه.
        """
        from .prompts import build_report_prompt
        from .schemas import FinalReport

        prompt = build_report_prompt(session_data=session_data)

        llm = self._provider_instance.get_chat_model(temperature=0.2)
        structured_llm = llm.with_structured_output(FinalReport)

        logger.info(
            "Generating report | provider=%s | session=%s",
            self._provider_instance.provider_name,
            session_data.get("session_uuid"),
        )

        result: FinalReport = structured_llm.invoke(prompt)
        return result.model_dump()

    # ── Decide Next Action ────────────────────────────────────────────────────

    def decide_next_action(
        self,
        session_context: dict,
        conversation_history: list[dict],
        current_question: dict,
        user_answer: str,
    ) -> dict:
        """
        تصمیم agent — از InterviewConductService صدا زده میشه.
        به agent.py delegate میکنه.
        """
        from .agent import get_agent
        agent = get_agent()

        return agent.decide_next_action(
            session_context=session_context,
            conversation_history=conversation_history,
            current_question=current_question,
            user_answer=user_answer,
        )

    # ── Class Methods (Convenience) ───────────────────────────────────────────

    @classmethod
    def _get_default(cls) -> "LLMClient":
        if not hasattr(cls, "_default_instance"):
            with _lock:
                if not hasattr(cls, "_default_instance"):
                    cls._default_instance = cls()
        return cls._default_instance

    # Shortcut class methods — بدون نیاز به instantiate کردن
    @classmethod
    def evaluate_default(cls, context: dict) -> dict:
        return cls._get_default().evaluate(context)

    @classmethod
    def generate_default_report_summary(cls, session_data: dict) -> dict:
        return cls._get_default().generate_report_summary(session_data)


# =============================================================================
#  Settings Helper
# =============================================================================

def get_provider_from_settings() -> str:
    """
    از settings تشخیص میده کدوم provider رو استفاده کنه.

    Settings مورد انتظار:
        LLM_PROVIDER = "openai"        # production
        LLM_PROVIDER = "anthropic"     # production alternative
        LLM_PROVIDER = "openrouter"    # testing / dev
        LLM_PROVIDER = "ollama"        # local dev
    """
    from django.conf import settings
    return getattr(settings, "LLM_PROVIDER", LLMProvider.OPENAI)
