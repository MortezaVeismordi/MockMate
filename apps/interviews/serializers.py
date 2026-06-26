# apps/interviews/serializers.py
# =============================================================================
# Interview Serializers
# =============================================================================

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import (
    InterviewMessage,
    InterviewSession,
    SessionQuestion,
    UserAnswer,
)

# =============================================================================
#  Question Serializers (nested)
# =============================================================================

class SessionQuestionBriefSerializer(serializers.ModelSerializer):
    """
    نمایش مختصر سوال داخل session — بدون reference_answer
    """
    question_type_display    = serializers.CharField(
        source="question.get_question_type_display",
        read_only=True,
    )
    seniority_level_display  = serializers.CharField(
        source="question.get_seniority_level_display",
        read_only=True,
    )
    categories = serializers.StringRelatedField(
        source="question.categories",
        many=True,
        read_only=True,
    )

    class Meta:
        model  = SessionQuestion
        fields = [
            "order",
            "status",
            "question_type_display",
            "seniority_level_display",
            "categories",
        ]


class SessionQuestionDetailSerializer(serializers.ModelSerializer):
    """
    نمایش کامل سوال فعلی — برای نمایش به کاربر
    reference_answer و criteria مخفی هستن
    """
    id             = serializers.IntegerField(source="question.id", read_only=True)
    title          = serializers.CharField(source="question.title",          read_only=True)
    body           = serializers.CharField(source="question.body",           read_only=True)
    estimated_time = serializers.IntegerField(source="question.estimated_time", read_only=True)
    code_template  = serializers.CharField(
        source="question.code_template",
        read_only=True,
        allow_null=True,
    )
    question_type  = serializers.CharField(source="question.question_type",  read_only=True)
    categories     = serializers.StringRelatedField(
        source="question.categories",
        many=True,
        read_only=True,
    )

    class Meta:
        model  = SessionQuestion
        fields = [
            "id",
            "order",
            "status",
            "title",
            "body",
            "estimated_time",
            "code_template",
            "question_type",
            "categories",
        ]


# =============================================================================
#  Session Serializers
# =============================================================================

class InterviewSessionCreateSerializer(serializers.Serializer):
    """
    ورودی ساختن session جدید — Onboarding wizard
    """
    target_position = serializers.CharField(
        max_length=150,
        error_messages={"required": _("موقعیت شغلی الزامی است.")},
    )
    seniority_level = serializers.ChoiceField(
        choices=InterviewSession.SeniorityLevel.choices,
        error_messages={"required": _("سطح ارشدیت الزامی است.")},
    )
    job_description = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=5000,
    )
    focus_topics = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list,
        max_length=10,
    )
    total_questions = serializers.IntegerField(
        required=False,
        default=10,
        min_value=5,
        max_value=20,
    )

    def validate_focus_topics(self, value: list) -> list:
        """چک میکنه topics معتبر هستن"""
        from apps.questions.models import QuestionCategory
        if value:
            valid_slugs = set(
                QuestionCategory.objects
                .filter(slug__in=value)
                .values_list("slug", flat=True)
            )
            invalid = set(value) - valid_slugs
            if invalid:
                raise serializers.ValidationError(
                    _(f"موضوعات نامعتبر: {', '.join(invalid)}")
                )
        return value


class InterviewSessionListSerializer(serializers.ModelSerializer):
    """
    لیست مصاحبه‌های کاربر — کارت‌های داشبورد
    """
    status_display          = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    seniority_level_display = serializers.CharField(
        source="get_seniority_level_display",
        read_only=True,
    )
    duration_minutes        = serializers.IntegerField(read_only=True)
    progress_percentage     = serializers.FloatField(read_only=True)
    avg_score               = serializers.FloatField(
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model  = InterviewSession
        fields = [
            "uuid",
            "target_position",
            "seniority_level",
            "seniority_level_display",
            "status",
            "status_display",
            "final_score",
            "avg_score",
            "progress_percentage",
            "duration_minutes",
            "created_at",
            "completed_at",
        ]


class InterviewSessionDetailSerializer(serializers.ModelSerializer):
    """
    جزئیات کامل یه session — صفحه مصاحبه
    """
    status_display          = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    seniority_level_display = serializers.CharField(
        source="get_seniority_level_display",
        read_only=True,
    )
    duration_minutes        = serializers.IntegerField(read_only=True)
    progress_percentage     = serializers.FloatField(read_only=True)
    is_active               = serializers.BooleanField(read_only=True)
    current_question        = serializers.SerializerMethodField()

    class Meta:
        model  = InterviewSession
        fields = [
            "uuid",
            "target_position",
            "seniority_level",
            "seniority_level_display",
            "focus_topics",
            "status",
            "status_display",
            "is_active",
            "current_question_index",
            "total_questions",
            "progress_percentage",
            "final_score",
            "duration_minutes",
            "started_at",
            "completed_at",
            "created_at",
            "current_question",
        ]

    def get_current_question(self, obj: InterviewSession):
        from .selectors import SessionSelector
        sq = SessionSelector.get_current_question(obj)
        if sq:
            return SessionQuestionDetailSerializer(sq).data
        return None


# =============================================================================
#  Message Serializers
# =============================================================================

class InterviewMessageSerializer(serializers.ModelSerializer):
    """
    نمایش پیام‌های مکالمه — برای UI چت
    """
    role_display         = serializers.CharField(
        source="get_role_display",
        read_only=True,
    )
    message_type_display = serializers.CharField(
        source="get_message_type_display",
        read_only=True,
    )

    class Meta:
        model  = InterviewMessage
        fields = [
            "id",
            "role",
            "role_display",
            "message_type",
            "message_type_display",
            "content",
            "turn_number",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields


# =============================================================================
#  Answer Serializers
# =============================================================================

class SubmitAnswerSerializer(serializers.Serializer):
    """
    ورودی ثبت پاسخ کاربر
    """
    answer_text     = serializers.CharField(
        min_length=10,
        max_length=5000,
        error_messages={
            "min_length": _("پاسخ حداقل ۱۰ کاراکتر باید داشته باشد."),
            "required"  : _("متن پاسخ الزامی است."),
        },
    )
    answer_duration = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
        max_value=3600,
    )


class SubmitFollowUpSerializer(serializers.Serializer):
    """
    ورودی پاسخ سوال تعقیبی
    """
    answer_text = serializers.CharField(
        min_length=5,
        max_length=5000,
    )


class UserAnswerEvaluationSerializer(serializers.ModelSerializer):
    """
    نمایش نتیجه ارزیابی — بعد از graded شدن
    """
    status_display  = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    question_title  = serializers.CharField(
        source="question.title",
        read_only=True,
    )
    question_type   = serializers.CharField(
        source="question.question_type",
        read_only=True,
    )
    is_evaluated    = serializers.BooleanField(read_only=True)
    passed          = serializers.BooleanField(read_only=True)

    class Meta:
        model  = UserAnswer
        fields = [
            "id",
            "question_title",
            "question_type",
            "answer_text",
            "answer_duration",
            "status",
            "status_display",
            "is_evaluated",
            "passed",
            "score",
            "technical_accuracy",
            "strengths",
            "weaknesses",
            "missing_keywords",
            "feedback",
            "follow_up_asked",
            "suggested_follow_up",
            "evaluated_at",
            "created_at",
        ]
        read_only_fields = fields


# =============================================================================
#  Report Serializers
# =============================================================================

class InterviewReportSerializer(serializers.ModelSerializer):
    """
    گزارش کامل نهایی مصاحبه — صفحه کارنامه
    """
    seniority_level_display = serializers.CharField(
        source="get_seniority_level_display",
        read_only=True,
    )
    duration_minutes        = serializers.IntegerField(read_only=True)
    answers                 = serializers.SerializerMethodField()
    stats                   = serializers.SerializerMethodField()

    class Meta:
        model  = InterviewSession
        fields = [
            "uuid",
            "target_position",
            "seniority_level",
            "seniority_level_display",
            "focus_topics",
            "final_score",
            "summary",
            "final_report",
            "duration_minutes",
            "total_questions",
            "started_at",
            "completed_at",
            "answers",
            "stats",
        ]

    def get_answers(self, obj: InterviewSession):
        from .selectors import AnswerSelector
        answers = AnswerSelector.get_session_answers(obj)
        return UserAnswerEvaluationSerializer(answers, many=True).data

    def get_stats(self, obj: InterviewSession):
        from .selectors import InterviewStatsSelector
        return InterviewStatsSelector.get_session_stats(obj)
