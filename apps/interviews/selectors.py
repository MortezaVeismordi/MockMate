# apps/interviews/selectors.py
# =============================================================================
# Interview Selectors — Read-Only Queries
# =============================================================================

import logging
from typing import Optional
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Max, Min, Prefetch, Q, QuerySet, Sum

from .models import InterviewMessage, InterviewSession, SessionQuestion, UserAnswer

logger = logging.getLogger(__name__)
User = get_user_model()


# =============================================================================
#  Session Selectors
# =============================================================================


class SessionSelector:
    @staticmethod
    def get_by_uuid(uuid: UUID) -> Optional[InterviewSession]:
        """
        گرفتن session با UUID — برای URL امن
        """
        try:
            return (
                InterviewSession.objects.select_related("user")
                .prefetch_related(
                    Prefetch(
                        "session_questions",
                        queryset=SessionQuestion.objects.select_related(
                            "question"
                        ).order_by("order"),
                    )
                )
                .get(uuid=uuid)
            )
        except InterviewSession.DoesNotExist:
            logger.debug("Session not found | uuid=%s", uuid)
            return None

    @staticmethod
    def get_by_id(session_id: int) -> Optional[InterviewSession]:
        try:
            return InterviewSession.objects.select_related("user").get(pk=session_id)
        except InterviewSession.DoesNotExist:
            return None

    @staticmethod
    def get_active_session(user) -> Optional[InterviewSession]:
        """
        آخرین session فعال کاربر
        فقط یه session فعال در هر لحظه مجاز است
        """
        return (
            InterviewSession.objects.filter(
                user=user,
                status__in=[
                    InterviewSession.Status.INTRO,
                    InterviewSession.Status.QUESTIONING,
                    InterviewSession.Status.DRILLING,
                ],
            )
            .select_related("user")
            .order_by("-created_at")
            .first()
        )

    @staticmethod
    def has_active_session(user) -> bool:
        return InterviewSession.objects.filter(
            user=user,
            status__in=[
                InterviewSession.Status.INTRO,
                InterviewSession.Status.QUESTIONING,
                InterviewSession.Status.DRILLING,
            ],
        ).exists()

    @staticmethod
    def get_user_sessions(
        user,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> QuerySet:
        """
        تاریخچه مصاحبه‌های کاربر با آمار خلاصه
        """
        qs = (
            InterviewSession.objects.filter(user=user)
            .annotate(
                answers_count=Count("answers", distinct=True),
                avg_score=Avg("answers__score"),
            )
            .order_by("-created_at")
        )

        if status:
            qs = qs.filter(status=status)

        return qs[:limit]

    @staticmethod
    def get_completed_sessions(user) -> QuerySet:
        return (
            InterviewSession.objects.filter(
                user=user, status=InterviewSession.Status.COMPLETED
            )
            .annotate(avg_score=Avg("answers__score"))
            .order_by("-completed_at")
        )

    @staticmethod
    def get_current_question(session: InterviewSession) -> Optional[SessionQuestion]:
        """
        سوال فعلی بر اساس current_question_index
        """
        return (
            SessionQuestion.objects.filter(
                session=session,
                order=session.current_question_index,
            )
            .select_related("question", "question__categories" if False else "question")
            .first()
        )

    @staticmethod
    def get_next_pending_question(
        session: InterviewSession,
    ) -> Optional[SessionQuestion]:
        """
        اولین سوال pending بعد از سوال فعلی
        """
        return (
            SessionQuestion.objects.filter(
                session=session,
                status=SessionQuestion.QuestionStatus.PENDING,
                order__gt=session.current_question_index,
            )
            .select_related("question")
            .order_by("order")
            .first()
        )

    @staticmethod
    def get_session_questions(session: InterviewSession) -> QuerySet:
        return (
            SessionQuestion.objects.filter(session=session)
            .select_related("question")
            .prefetch_related("question__categories")
            .order_by("order")
        )


# =============================================================================
#  Message Selectors
# =============================================================================


class MessageSelector:
    @staticmethod
    def get_conversation_history(
        session: InterviewSession,
        limit: Optional[int] = None,
        exclude_system: bool = False,
    ) -> QuerySet:
        """
        تاریخچه مکالمه برای ارسال به LLM
        ترتیب: قدیمی‌ترین اول (برای context صحیح)
        """
        qs = (
            InterviewMessage.objects.filter(session=session)
            .select_related("related_question__question")
            .order_by("turn_number")
        )

        if exclude_system:
            qs = qs.exclude(role=InterviewMessage.Role.SYSTEM)

        if limit:
            # آخرین N پیام + همه system messages
            system_msgs = qs.filter(role=InterviewMessage.Role.SYSTEM)
            recent_msgs = qs.exclude(role=InterviewMessage.Role.SYSTEM).order_by(
                "-turn_number"
            )[:limit]

            # ترکیب و مرتب‌سازی
            ids = list(system_msgs.values_list("id", flat=True)) + list(
                recent_msgs.values_list("id", flat=True)
            )
            qs = InterviewMessage.objects.filter(id__in=ids).order_by("turn_number")

        return qs

    @staticmethod
    def get_llm_messages(
        session: InterviewSession,
        last_n: int = 20,
    ) -> list[dict]:
        """
        تبدیل history به فرمت LangChain/OpenAI
        [{"role": "user", "content": "..."}, ...]

        فقط role های user و assistant — system جداگانه handle میشه
        """
        messages = InterviewMessage.objects.filter(
            session=session,
            role__in=[
                InterviewMessage.Role.USER,
                InterviewMessage.Role.ASSISTANT,
            ],
        ).order_by("-turn_number")[:last_n]

        # برعکس کن تا قدیمی‌ترین اول باشه
        return [
            {"role": msg.role, "content": msg.content}
            for msg in reversed(list(messages))
        ]

    @staticmethod
    def get_last_turn_number(session: InterviewSession) -> int:
        result = InterviewMessage.objects.filter(session=session).aggregate(
            max_turn=Max("turn_number")
        )
        return result["max_turn"] or 0

    @staticmethod
    def get_messages_by_type(
        session: InterviewSession,
        message_type: str,
    ) -> QuerySet:
        return InterviewMessage.objects.filter(
            session=session, message_type=message_type
        ).order_by("turn_number")


# =============================================================================
#  Answer Selectors
# =============================================================================


class AnswerSelector:
    @staticmethod
    def get_by_session_question(
        session: InterviewSession,
        session_question: SessionQuestion,
    ) -> Optional[UserAnswer]:
        try:
            return UserAnswer.objects.get(
                session=session,
                question=session_question.question,
            )
        except UserAnswer.DoesNotExist:
            return None

    @staticmethod
    def get_session_answers(
        session: InterviewSession,
        status: Optional[str] = None,
    ) -> QuerySet:
        """
        همه پاسخ‌های یه session — برای گزارش نهایی
        """
        qs = (
            UserAnswer.objects.filter(session=session)
            .select_related("question")
            .prefetch_related("question__categories")
            .order_by("created_at")
        )

        if status:
            qs = qs.filter(status=status)

        return qs

    @staticmethod
    def get_pending_evaluations(limit: int = 50) -> QuerySet:
        """
        پاسخ‌های منتظر ارزیابی — برای Celery worker
        """
        return (
            UserAnswer.objects.filter(status=UserAnswer.Status.PENDING)
            .select_related("question", "session", "user")
            .order_by("created_at")
        )[:limit]

    @staticmethod
    def get_failed_evaluations(limit: int = 20) -> QuerySet:
        """
        پاسخ‌هایی که ارزیابیشون fail شده — برای retry
        """
        return (
            UserAnswer.objects.filter(status=UserAnswer.Status.FAILED)
            .select_related("question", "session", "user")
            .order_by("created_at")
        )[:limit]

    @staticmethod
    def has_answered_question(
        session: InterviewSession,
        question_id: int,
    ) -> bool:
        return UserAnswer.objects.filter(
            session=session,
            question_id=question_id,
        ).exists()


# =============================================================================
#  Stats Selectors
# =============================================================================


class InterviewStatsSelector:
    @staticmethod
    def get_session_stats(session: InterviewSession) -> dict:
        """
        آمار کامل یه session — برای گزارش نهایی و کارنامه
        """
        answers = UserAnswer.objects.filter(
            session=session,
            status=UserAnswer.Status.GRADED,
        )

        aggregation = answers.aggregate(
            total_answered=Count("id"),
            avg_score=Avg("score"),
            max_score=Max("score"),
            min_score=Min("score"),
            total_duration=Sum("answer_duration"),
            passed_count=Count("id", filter=Q(score__gte=60)),
            follow_up_count=Count("id", filter=Q(follow_up_asked=True)),
        )

        # breakdown بر اساس نوع سوال
        type_breakdown = (
            answers.values("question__question_type")
            .annotate(
                count=Count("id"),
                avg=Avg("score"),
            )
            .order_by("question__question_type")
        )

        total = aggregation["total_answered"] or 1

        return {
            "total_questions": session.total_questions,
            "total_answered": aggregation["total_answered"] or 0,
            "avg_score": round(aggregation["avg_score"] or 0, 1),
            "max_score": aggregation["max_score"] or 0,
            "min_score": aggregation["min_score"] or 0,
            "passed_count": aggregation["passed_count"] or 0,
            "pass_rate": round((aggregation["passed_count"] or 0) / total * 100, 1),
            "follow_up_rate": round(
                (aggregation["follow_up_count"] or 0) / total * 100, 1
            ),
            "total_duration_min": round((aggregation["total_duration"] or 0) / 60, 1),
            "type_breakdown": list(type_breakdown),
        }

    @staticmethod
    def get_user_overall_stats(user) -> dict:
        """
        آمار کلی کاربر از همه مصاحبه‌هاش
        """
        sessions = InterviewSession.objects.filter(
            user=user,
            status=InterviewSession.Status.COMPLETED,
        )

        aggregation = sessions.aggregate(
            total_sessions=Count("id"),
            avg_final_score=Avg("final_score"),
            best_score=Max("final_score"),
        )

        answers = UserAnswer.objects.filter(
            session__user=user,
            status=UserAnswer.Status.GRADED,
        )

        answer_stats = answers.aggregate(
            total_answers=Count("id"),
            overall_avg=Avg("score"),
        )

        # سوالاتی که بیشتر غلط جواب داده
        weak_topics = (
            answers.filter(score__lt=60)
            .values("question__question_type")
            .annotate(fail_count=Count("id"))
            .order_by("-fail_count")
        )[:5]

        return {
            "total_sessions": aggregation["total_sessions"] or 0,
            "avg_final_score": round(aggregation["avg_final_score"] or 0, 1),
            "best_score": aggregation["best_score"] or 0,
            "total_answers": answer_stats["total_answers"] or 0,
            "overall_avg": round(answer_stats["overall_avg"] or 0, 1),
            "weak_topics": list(weak_topics),
        }

    @staticmethod
    def get_score_trend(user, last_n: int = 10) -> list[dict]:
        """
        روند نمرات کاربر در مصاحبه‌های اخیر
        برای نمایش در داشبورد
        """
        return list(
            InterviewSession.objects.filter(
                user=user,
                status=InterviewSession.Status.COMPLETED,
                final_score__isnull=False,
            )
            .order_by("-completed_at")
            .values(
                "uuid",
                "target_position",
                "final_score",
                "completed_at",
            )
        )[:last_n]
