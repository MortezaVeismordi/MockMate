# apps/interviews/services.py
# =============================================================================
# Interview Services — Business Logic
# =============================================================================

import logging
import random
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.questions.models import Question

from .models import InterviewMessage, InterviewSession, SessionQuestion, UserAnswer
from .selectors import (
    AnswerSelector,
    InterviewStatsSelector,
    MessageSelector,
    SessionSelector,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# =============================================================================
#  Interview Setup Service
#  مسئول: ساختن session + انتخاب هوشمند سوالات
# =============================================================================


class InterviewSetupService:
    @staticmethod
    @transaction.atomic
    def create_session(
        user,
        target_position: str,
        seniority_level: str,
        job_description: str = "",
        focus_topics: list = None,
        total_questions: int = 10,
    ) -> InterviewSession:
        """
        ساختن یه session جدید.
        اگه session فعال داشته باشه، خطا میده.
        """
        # چک session فعال
        if SessionSelector.has_active_session(user):
            raise ValueError(
                _("شما یک مصاحبه فعال دارید. ابتدا آن را به پایان برسانید.")
            )

        session = InterviewSession.objects.create(
            user=user,
            target_position=target_position,
            seniority_level=seniority_level,
            job_description=job_description,
            focus_topics=focus_topics or [],
            total_questions=total_questions,
            status=InterviewSession.Status.SETUP,
        )

        logger.info(
            "Interview session created | user=%s | position=%s | session=%s",
            user.pk,
            target_position,
            session.uuid,
        )

        # انتخاب سوالات
        questions = InterviewSetupService._select_questions(
            seniority_level=seniority_level,
            focus_topics=focus_topics or [],
            total=total_questions,
        )

        if not questions:
            raise ValueError(_("سوال مناسبی برای این سطح و موضوع یافت نشد."))

        # ثبت سوالات در session
        InterviewSetupService._assign_questions(session, questions)

        logger.info(
            "Questions assigned | session=%s | count=%d",
            session.uuid,
            len(questions),
        )

        return session

    @staticmethod
    def _select_questions(
        seniority_level: str,
        focus_topics: list,
        total: int,
    ) -> list[Question]:
        """
        انتخاب هوشمند سوالات از بانک:
        - فیلتر بر اساس سطح و موضوع
        - توزیع متعادل بین انواع سوال
        - رندوم برای تنوع
        """
        base_qs = Question.objects.filter(
            is_active=True,
            seniority_level=seniority_level,
        ).prefetch_related("categories")

        # فیلتر موضوعی اگه topic داریم
        if focus_topics:
            base_qs = base_qs.filter(categories__slug__in=focus_topics).distinct()

        # توزیع بر اساس نوع سوال
        distribution = InterviewSetupService._get_question_distribution(total)
        selected = []

        for question_type, count in distribution.items():
            type_qs = list(base_qs.filter(question_type=question_type))
            if type_qs:
                picked = random.sample(type_qs, min(count, len(type_qs)))
                selected.extend(picked)

        # اگه کمتر از total داریم، بقیه رو از کل pool بگیر
        if len(selected) < total:
            existing_ids = {q.pk for q in selected}
            remaining_qs = list(base_qs.exclude(pk__in=existing_ids))
            needed = total - len(selected)
            if remaining_qs:
                extra = random.sample(remaining_qs, min(needed, len(remaining_qs)))
                selected.extend(extra)

        # shuffle نهایی
        random.shuffle(selected)
        return selected[:total]

    @staticmethod
    def _get_question_distribution(total: int) -> dict:
        raw = {
            Question.QuestionType.TECHNICAL: total * 0.40,
            Question.QuestionType.SYSTEM_DESIGN: total * 0.20,
            Question.QuestionType.ARCHITECTURE: total * 0.15,
            Question.QuestionType.BEHAVIORAL: total * 0.15,
            Question.QuestionType.DEVOPS: total * 0.10,
        }

        # تبدیل به int و تضمین جمع = total
        distribution = {k: int(v) for k, v in raw.items()}

        # کسری که گم شده رو به بزرگترین bucket اضافه کن
        deficit = total - sum(distribution.values())
        if deficit > 0:
            largest_key = max(distribution, key=distribution.get)
            distribution[largest_key] += deficit

        # تضمین حداقل ۱ برای هر نوع فقط اگه total اجازه بده
        if total >= len(distribution):
            distribution = {k: max(1, v) for k, v in distribution.items()}
            # دوباره تنظیم کن
            excess = sum(distribution.values()) - total
            if excess > 0:
                largest_key = max(distribution, key=distribution.get)
                distribution[largest_key] -= excess

        return distribution

    @staticmethod
    def _assign_questions(
        session: InterviewSession,
        questions: list[Question],
    ) -> None:
        SessionQuestion.objects.bulk_create(
            [
                SessionQuestion(
                    session=session,
                    question=q,
                    order=idx,
                    status=SessionQuestion.QuestionStatus.PENDING,
                )
                for idx, q in enumerate(questions)
            ]
        )


# =============================================================================
#  Interview Conduct Service
#  مسئول: مدیریت State Machine + پیام‌ها + tool calls
# =============================================================================


class InterviewConductService:
    # ── شروع مصاحبه ──────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def start_interview(session: InterviewSession) -> InterviewMessage:
        """
        انتقال از SETUP به INTRO
        ساختن system prompt و پیام خوش‌آمدگویی
        """
        if session.status != InterviewSession.Status.SETUP:
            raise ValueError(_("این مصاحبه قبلاً شروع شده است."))

        session.transition_to(InterviewSession.Status.INTRO)

        # ساختن system message (برای LLM context)
        system_prompt = InterviewConductService._build_system_prompt(session)
        InterviewConductService._save_message(
            session=session,
            role=InterviewMessage.Role.SYSTEM,
            message_type=InterviewMessage.MessageType.SYSTEM_EVENT,
            content=system_prompt,
        )

        # پیام خوش‌آمدگویی
        greeting = InterviewConductService._build_greeting(session)
        greeting_msg = InterviewConductService._save_message(
            session=session,
            role=InterviewMessage.Role.ASSISTANT,
            message_type=InterviewMessage.MessageType.GREETING,
            content=greeting,
        )

        logger.info("Interview started | session=%s", session.uuid)
        return greeting_msg

    # ── پرسیدن سوال ──────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def ask_next_question(session: InterviewSession) -> InterviewMessage:
        """
        پرسیدن سوال بعدی و انتقال به QUESTIONING
        """
        if session.status not in (
            InterviewSession.Status.INTRO,
            InterviewSession.Status.QUESTIONING,
        ):
            raise ValueError(_("وضعیت مصاحبه برای پرسیدن سوال مناسب نیست."))

        next_q = SessionSelector.get_next_pending_question(session)

        if not next_q:
            # سوالی نمونده — برو به wrap up
            return InterviewConductService.wrap_up(session)

        # سوال رو active کن
        next_q.status = SessionQuestion.QuestionStatus.ACTIVE
        next_q.save(update_fields=["status"])

        # ایندکس رو آپدیت کن
        session.current_question_index = next_q.order
        session.status = InterviewSession.Status.QUESTIONING
        session.save(update_fields=["current_question_index", "status"])

        # پیام سوال رو ذخیره کن
        question_msg = InterviewConductService._save_message(
            session=session,
            role=InterviewMessage.Role.ASSISTANT,
            message_type=InterviewMessage.MessageType.QUESTION,
            content=next_q.question.body,
            related_question=next_q,
            metadata={
                "question_id": next_q.question.pk,
                "question_order": next_q.order,
                "estimated_time": next_q.question.estimated_time,
            },
        )

        logger.info(
            "Question asked | session=%s | order=%d | question=%d",
            session.uuid,
            next_q.order,
            next_q.question.pk,
        )

        return question_msg

    # ── دریافت پاسخ کاربر ────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def submit_answer(
        session: InterviewSession,
        answer_text: str,
        answer_duration: Optional[int] = None,
    ) -> UserAnswer:
        """
        ثبت پاسخ کاربر و trigger کردن ارزیابی async
        """
        if session.status != InterviewSession.Status.QUESTIONING:
            raise ValueError(_("الان نوبت پاسخ دادن نیست."))

        current_q = SessionSelector.get_current_question(session)
        if not current_q:
            raise ValueError(_("سوال فعالی یافت نشد."))

        # چک تکراری نبودن پاسخ
        if AnswerSelector.has_answered_question(session, current_q.question.pk):
            raise ValueError(_("این سوال قبلاً پاسخ داده شده است."))

        # ذخیره پیام کاربر در history
        InterviewConductService._save_message(
            session=session,
            role=InterviewMessage.Role.USER,
            message_type=InterviewMessage.MessageType.USER_ANSWER,
            content=answer_text,
            related_question=current_q,
            metadata={"answer_duration": answer_duration},
        )

        # ساختن UserAnswer
        answer = UserAnswer.objects.create(
            session=session,
            user=session.user,
            question=current_q.question,
            answer_text=answer_text,
            answer_duration=answer_duration,
            status=UserAnswer.Status.PENDING,
        )

        # سوال رو answered کن
        current_q.status = SessionQuestion.QuestionStatus.ANSWERED
        current_q.save(update_fields=["status"])

        logger.info(
            "Answer submitted | session=%s | question=%d | answer=%d",
            session.uuid,
            current_q.question.pk,
            answer.pk,
        )

        # trigger ارزیابی async
        from .tasks import evaluate_answer_task

        evaluate_answer_task.delay(answer.pk)

        return answer

    # ── سوال تعقیبی ──────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def ask_follow_up(
        session: InterviewSession,
        follow_up_content: str,
    ) -> InterviewMessage:
        """
        LLM تصمیم گرفته follow-up بپرسه
        وضعیت میره به DRILLING
        """
        if session.status not in (
            InterviewSession.Status.QUESTIONING,
            InterviewSession.Status.DRILLING,
        ):
            raise ValueError(_("وضعیت مصاحبه برای سوال تعقیبی مناسب نیست."))

        session.transition_to(InterviewSession.Status.DRILLING)

        current_q = SessionSelector.get_current_question(session)

        follow_up_msg = InterviewConductService._save_message(
            session=session,
            role=InterviewMessage.Role.ASSISTANT,
            message_type=InterviewMessage.MessageType.FOLLOW_UP,
            content=follow_up_content,
            related_question=current_q,
        )

        # mark کردن answer که follow_up داشته
        if current_q:
            UserAnswer.objects.filter(
                session=session,
                question=current_q.question,
            ).update(follow_up_asked=True)

        logger.info(
            "Follow-up asked | session=%s | question=%d",
            session.uuid,
            current_q.question.pk if current_q else 0,
        )

        return follow_up_msg

    # ── پاسخ follow-up ────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def submit_follow_up_answer(
        session: InterviewSession,
        answer_text: str,
    ) -> None:
        """
        ذخیره پاسخ سوال تعقیبی و برگشت به QUESTIONING
        """
        if session.status != InterviewSession.Status.DRILLING:
            raise ValueError(_("الان در فاز سوال تعقیبی نیستیم."))

        current_q = SessionSelector.get_current_question(session)

        # ذخیره در history
        InterviewConductService._save_message(
            session=session,
            role=InterviewMessage.Role.USER,
            message_type=InterviewMessage.MessageType.USER_ANSWER,
            content=answer_text,
            related_question=current_q,
        )

        # ذخیره در UserAnswer
        if current_q:
            UserAnswer.objects.filter(
                session=session,
                question=current_q.question,
            ).update(follow_up_answer=answer_text)

        # برگشت به QUESTIONING
        session.transition_to(InterviewSession.Status.QUESTIONING)

    # ── جمع‌بندی و پایان ─────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def wrap_up(session: InterviewSession) -> InterviewMessage:
        """
        انتقال به WRAP_UP و ارسال پیام پایانی
        """
        session.transition_to(InterviewSession.Status.WRAP_UP)

        wrap_up_msg = InterviewConductService._save_message(
            session=session,
            role=InterviewMessage.Role.ASSISTANT,
            message_type=InterviewMessage.MessageType.WRAP_UP,
            content=InterviewConductService._build_wrap_up_message(session),
        )

        # trigger گزارش نهایی async
        from .tasks import generate_report_task

        generate_report_task.apply_async(
            args=[session.pk],
            countdown=5,  # ۵ ثانیه صبر میکنه تا همه evaluate‌ها تموم بشن
        )

        logger.info("Interview wrap up | session=%s", session.uuid)
        return wrap_up_msg

    # ── Helper Methods ────────────────────────────────────────────────────────

    @staticmethod
    def _save_message(
        session: InterviewSession,
        role: str,
        message_type: str,
        content: str,
        related_question: Optional[SessionQuestion] = None,
        metadata: Optional[dict] = None,
    ) -> InterviewMessage:
        turn = MessageSelector.get_last_turn_number(session) + 1
        return InterviewMessage.objects.create(
            session=session,
            role=role,
            message_type=message_type,
            content=content,
            turn_number=turn,
            related_question=related_question,
            metadata=metadata or {},
        )

    @staticmethod
    def _build_system_prompt(session: InterviewSession) -> str:
        """
        System prompt کامل برای LLM
        Context Injection از پروفایل کاربر و تنظیمات session
        """
        base_prompt = f"""تو یک مصاحبه‌کننده فنی ارشد هستی.
کاربر برای پوزیشن «{session.target_position}» در سطح «{session.get_seniority_level_display()}» مصاحبه می‌دهد.
تعداد سوالات: {session.total_questions}
"""
        if session.job_description:
            base_prompt += f"\nشرح شغل:\n{session.job_description}\n"

        if session.focus_topics:
            topics = "، ".join(session.focus_topics)
            base_prompt += f"\nموضوعات تمرکز: {topics}\n"

        base_prompt += """
دستورالعمل‌ها:
- در فاز INTRO خودت را معرفی کن و سوال فنی نپرس
- در فاز QUESTIONING سوالات را یکی‌یکی بپرس
- اگر پاسخ ناقص بود، follow-up بپرس (ابزار request_follow_up)
- بعد از اتمام سوالات، مصاحبه را جمع‌بندی کن (ابزار finalize_interview)
- لحن حرفه‌ای و محترمانه داشته باش
"""
        return base_prompt

    @staticmethod
    def _build_greeting(session: InterviewSession) -> str:
        return (
            f"سلام! خوش آمدید.\n"
            f"من امروز مصاحبه شما را برای پوزیشن «{session.target_position}» "
            f"انجام می‌دهم.\n"
            f"این جلسه شامل {session.total_questions} سوال است.\n"
            f"هر زمان آماده بودید بگویید تا شروع کنیم."
        )

    @staticmethod
    def _build_wrap_up_message(session: InterviewSession) -> str:
        return (
            "مصاحبه به پایان رسید.\n"
            "از وقتی که گذاشتید متشکرم.\n"
            "نتایج ارزیابی به زودی آماده خواهد شد."
        )


# =============================================================================
#  Evaluation Service
#  مسئول: ارزیابی پاسخ کاربر با LLM
# =============================================================================


class EvaluationService:
    @staticmethod
    def evaluate_answer(answer: UserAnswer) -> UserAnswer:
        """
        ارزیابی یه پاسخ با LLM و ذخیره نتیجه
        این متد توسط Celery task صدا زده میشه
        """
        if answer.status == UserAnswer.Status.GRADED:
            logger.warning("Answer already graded | answer=%d", answer.pk)
            return answer

        try:
            # ساختن context package
            context = EvaluationService._build_evaluation_context(answer)

            # صدا زدن LLM
            from apps.core.llm.client import LLMClient

            result = LLMClient.evaluate_default(context)

            # ذخیره نتیجه
            EvaluationService._save_evaluation(answer, result)

            logger.info(
                "Answer evaluated | answer=%d | score=%s",
                answer.pk,
                answer.score,
            )

        except Exception as exc:
            logger.error(
                "Evaluation failed | answer=%d | error=%s",
                answer.pk,
                str(exc),
                exc_info=True,
            )
            answer.status = UserAnswer.Status.FAILED
            answer.error_log = str(exc)
            answer.save(update_fields=["status", "error_log"])
            raise

        return answer

    @staticmethod
    def _build_evaluation_context(answer: UserAnswer) -> dict:
        """
        ساختن Context Package کامل برای LLM
        سوال + پاسخ کاربر + reference answer + criteria
        """
        question = answer.question
        return {
            "question_text": question.body,
            "reference_answer": question.reference_answer,
            "evaluation_criteria": question.ai_evaluation_criteria,
            "user_answer": answer.answer_text,
            "follow_up_answer": answer.follow_up_answer,
            "seniority_level": answer.session.seniority_level,
            "target_position": answer.session.target_position,
        }

    @staticmethod
    def _save_evaluation(answer: UserAnswer, result: dict) -> None:
        """
        ذخیره نتیجه structured output از LLM
        """
        answer.status = UserAnswer.Status.GRADED
        answer.score = result.get("score", 0)
        answer.technical_accuracy = result.get("technical_accuracy", "")
        answer.strengths = result.get("strengths", [])
        answer.weaknesses = result.get("weaknesses", [])
        answer.missing_keywords = result.get("missing_keywords", [])
        answer.feedback = result.get("feedback", "")
        answer.suggested_follow_up = result.get("suggested_follow_up", "")
        answer.raw_evaluation = result
        answer.evaluated_at = timezone.now()

        answer.save(
            update_fields=[
                "status",
                "score",
                "technical_accuracy",
                "strengths",
                "weaknesses",
                "missing_keywords",
                "feedback",
                "suggested_follow_up",
                "raw_evaluation",
                "evaluated_at",
            ]
        )


# =============================================================================
#  Report Service
#  مسئول: تولید گزارش نهایی مصاحبه
# =============================================================================


class ReportService:
    @staticmethod
    @transaction.atomic
    def generate_final_report(session: InterviewSession) -> InterviewSession:
        """
        تولید گزارش نهایی بعد از اتمام همه ارزیابی‌ها
        """
        # چک که همه پاسخ‌ها evaluate شدن
        pending_count = UserAnswer.objects.filter(
            session=session,
            status=UserAnswer.Status.PENDING,
        ).count()

        if pending_count > 0:
            logger.warning(
                "Report generation: %d answers still pending | session=%s",
                pending_count,
                session.uuid,
            )

        # جمع‌آوری آمار
        stats = InterviewStatsSelector.get_session_stats(session)

        # تولید گزارش با LLM
        try:
            from apps.core.llm.client import LLMClient

            ai_summary = LLMClient.generate_report_summary(
                session_data={
                    "target_position": session.target_position,
                    "seniority_level": session.seniority_level,
                    "stats": stats,
                    "answers": ReportService._get_answers_summary(session),
                }
            )
        except Exception as exc:
            logger.error(
                "Report LLM generation failed | session=%s | error=%s",
                session.uuid,
                str(exc),
            )
            ai_summary = ""

        # ذخیره گزارش نهایی
        session.final_score = stats["avg_score"]
        session.final_report = {
            "stats": stats,
            "ai_summary": ai_summary,
            "generated_at": timezone.now().isoformat(),
        }
        session.summary = ai_summary
        session.transition_to(InterviewSession.Status.COMPLETED)

        logger.info(
            "Final report generated | session=%s | score=%.1f",
            session.uuid,
            session.final_score,
        )

        return session

    @staticmethod
    def _get_answers_summary(session: InterviewSession) -> list[dict]:
        """
        خلاصه پاسخ‌ها برای prompt گزارش نهایی
        """
        answers = AnswerSelector.get_session_answers(
            session,
            status=UserAnswer.Status.GRADED,
        )
        return [
            {
                "question": a.question.title,
                "score": a.score,
                "strengths": a.strengths,
                "weaknesses": a.weaknesses,
            }
            for a in answers
        ]
