# apps/core/llm/agent.py
# =============================================================================
# Interview Agent — LangChain Tool Calling + Structured Output
# =============================================================================

import logging
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

logger = logging.getLogger(__name__)


# =============================================================================
#  Tools — ابزارهایی که Agent میتونه صدا بزنه
# =============================================================================

@tool
def trigger_next_question() -> dict:
    """
    وقتی کاربر پاسخ کاملی داده و آماده سوال بعدیه این ابزار رو صدا بزن.
    فقط وقتی پاسخ کافی و قابل قبول بود استفاده کن.
    """
    return {"action": "next_question"}


@tool
def request_follow_up(follow_up_question: str) -> dict:
    """
    وقتی پاسخ کاربر ناقص بود یا نکته جالبی داشت که باید بیشتر بررسی بشه.
    یه سوال تعقیبی مشخص و هدفمند بپرس.

    Args:
        follow_up_question: سوال تعقیبی که میخوای بپرسی
    """
    return {
        "action"           : "follow_up",
        "follow_up_question": follow_up_question,
    }


@tool
def finalize_interview() -> dict:
    """
    وقتی همه سوالات تموم شده یا مصاحبه باید خاتمه پیدا کنه این ابزار رو صدا بزن.
    """
    return {"action": "wrap_up"}


# =============================================================================
#  Interview Agent
# =============================================================================

class InterviewAgent:
    """
    Agent هوشمند مصاحبه با قابلیت‌های:
    - تصمیم‌گیری بعد از هر پاسخ (next / follow_up / wrap_up)
    - ارزیابی structured با Pydantic
    - تولید گزارش نهایی
    - Context Injection کامل
    """

    def __init__(self):
        from django.conf import settings

        self._llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.3,       # کمی خلاقیت ولی mostly deterministic
            api_key=settings.OPENAI_API_KEY,
        )

        # LLM با tools برای تصمیم‌گیری
        self._tools = [
            trigger_next_question,
            request_follow_up,
            finalize_interview,
        ]
        self._llm_with_tools = self._llm.bind_tools(self._tools)

        # LLM با structured output برای ارزیابی
        from .schemas import EvaluationResult
        self._llm_evaluator = self._llm.with_structured_output(EvaluationResult)

        # LLM با structured output برای گزارش
        from .schemas import FinalReport
        self._llm_reporter = self._llm.with_structured_output(FinalReport)

    # ── تصمیم‌گیری بعد از پاسخ کاربر ────────────────────────────────────────

    def decide_next_action(
        self,
        session_context: dict,
        conversation_history: list[dict],
        current_question: dict,
        user_answer: str,
    ) -> dict:
        """
        بعد از هر پاسخ کاربر تصمیم میگیره:
        - next_question  ← پاسخ کافی بود، بریم سوال بعدی
        - follow_up      ← نیاز به بررسی بیشتر داره
        - wrap_up        ← مصاحبه تموم شده

        Returns:
            {
                "action": "next_question" | "follow_up" | "wrap_up",
                "follow_up_question": str | None,
                "reasoning": str,
            }
        """
        from .prompts import build_conductor_prompt

        system_prompt = build_conductor_prompt(
            session_context=session_context,
            current_question=current_question,
            questions_remaining=session_context.get("questions_remaining", 0),
        )

        messages = self._build_messages(
            system_prompt=system_prompt,
            history=conversation_history,
            last_user_message=user_answer,
        )

        logger.debug(
            "Deciding next action | session=%s | question_index=%d",
            session_context.get("session_uuid"),
            session_context.get("current_question_index", 0),
        )

        try:
            response = self._llm_with_tools.invoke(messages)

            # اگه tool call داشت
            if response.tool_calls:
                tool_call = response.tool_calls[0]
                tool_name = tool_call["name"]
                tool_args = tool_call.get("args", {})

                if tool_name == "trigger_next_question":
                    return {
                        "action"            : "next_question",
                        "follow_up_question": None,
                        "reasoning"         : "پاسخ کافی بود.",
                    }
                elif tool_name == "request_follow_up":
                    return {
                        "action"            : "follow_up",
                        "follow_up_question": tool_args.get("follow_up_question", ""),
                        "reasoning"         : "پاسخ ناقص بود.",
                    }
                elif tool_name == "finalize_interview":
                    return {
                        "action"            : "wrap_up",
                        "follow_up_question": None,
                        "reasoning"         : "مصاحبه تموم شد.",
                    }

            # اگه tool call نداشت — default به next_question
            logger.warning(
                "No tool call from agent, defaulting to next_question | session=%s",
                session_context.get("session_uuid"),
            )
            return {
                "action"            : "next_question",
                "follow_up_question": None,
                "reasoning"         : "default",
            }

        except Exception as exc:
            logger.error(
                "Agent decision failed | session=%s | error=%s",
                session_context.get("session_uuid"), str(exc),
                exc_info=True,
            )
            # fail-safe — برو سوال بعدی
            return {
                "action"            : "next_question",
                "follow_up_question": None,
                "reasoning"         : f"error: {str(exc)}",
            }

    # ── ارزیابی پاسخ ─────────────────────────────────────────────────────────

    def evaluate_answer(
        self,
        question_text: str,
        reference_answer: str,
        evaluation_criteria: dict,
        user_answer: str,
        follow_up_answer: str,
        session_context: dict,
    ) -> dict:
        """
        ارزیابی structured پاسخ کاربر با Pydantic schema.
        از Few-Shot Prompting برای calibration استفاده میکنه.

        Returns: dict معادل EvaluationResult
        """
        from .prompts import build_evaluation_prompt
        from .schemas import EvaluationResult

        prompt = build_evaluation_prompt(
            question_text=question_text,
            reference_answer=reference_answer,
            evaluation_criteria=evaluation_criteria,
            user_answer=user_answer,
            follow_up_answer=follow_up_answer,
            seniority_level=session_context.get("seniority_level", "mid_level"),
            target_position=session_context.get("target_position", ""),
        )

        logger.debug(
            "Evaluating answer | session=%s",
            session_context.get("session_uuid"),
        )

        try:
            result: EvaluationResult = self._llm_evaluator.invoke(prompt)
            return result.model_dump()

        except Exception as exc:
            logger.error(
                "Evaluation failed | session=%s | error=%s",
                session_context.get("session_uuid"), str(exc),
                exc_info=True,
            )
            raise

    # ── تولید گزارش نهایی ────────────────────────────────────────────────────

    def generate_report(
        self,
        session_data: dict,
    ) -> dict:
        """
        تولید گزارش نهایی مصاحبه با تحلیل کامل.

        Returns: dict معادل FinalReport
        """
        from .prompts import build_report_prompt
        from .schemas import FinalReport

        prompt = build_report_prompt(session_data=session_data)

        logger.info(
            "Generating final report | session=%s",
            session_data.get("session_uuid"),
        )

        try:
            result: FinalReport = self._llm_reporter.invoke(prompt)
            return result.model_dump()

        except Exception as exc:
            logger.error(
                "Report generation failed | session=%s | error=%s",
                session_data.get("session_uuid"), str(exc),
                exc_info=True,
            )
            raise

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_messages(
        system_prompt: str,
        history: list[dict],
        last_user_message: str,
    ) -> list:
        """
        ساختن لیست پیام‌ها برای LLM از history + پیام جدید
        """
        messages = [SystemMessage(content=system_prompt)]

        for msg in history:
            role    = msg.get("role")
            content = msg.get("content", "")

            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

        messages.append(HumanMessage(content=last_user_message))
        return messages


# =============================================================================
#  Singleton — یه instance برای کل app
# =============================================================================

_agent_instance: Optional[InterviewAgent] = None


def get_agent() -> InterviewAgent:
    """
    Singleton factory — از این توی services استفاده کن.

    مثال:
        from apps.core.llm.agent import get_agent
        agent = get_agent()
        decision = agent.decide_next_action(...)
    """
    global _agent_instance

    if _agent_instance is None:
        _agent_instance = InterviewAgent()
        logger.info("InterviewAgent initialized")

    return _agent_instance