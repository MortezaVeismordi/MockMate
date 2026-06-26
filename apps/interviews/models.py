# apps/interviews/models.py
# =============================================================================
# Interview Models — AI Interviewer
# =============================================================================

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.questions.models import Question

# ─────────────────────────────────────────────────────────────────────────────
#  Interview Session
# ─────────────────────────────────────────────────────────────────────────────

class InterviewSession(models.Model):

    class Status(models.TextChoices):
        SETUP       = "setup",       _("در حال تنظیم")
        INTRO       = "intro",       _("معارفه")
        QUESTIONING = "questioning", _("در حال سوال")
        DRILLING    = "drilling",    _("سوال تعقیبی")
        WRAP_UP     = "wrap_up",     _("جمع‌بندی")
        COMPLETED   = "completed",   _("تکمیل شده")
        ABANDONED   = "abandoned",   _("رها شده")

    class SeniorityLevel(models.TextChoices):
        INTERN    = "intern",    _("کارآموز")
        JUNIOR    = "junior",    _("جونیور")
        MID_LEVEL = "mid_level", _("میدلول")
        SENIOR    = "senior",    _("سنیور")
        LEAD      = "lead",      _("لید")

    # ── شناسه یکتا (برای URL امن) ─────────────────────────────────────────
    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name=_("شناسه یکتا"),
    )

    # ── روابط ────────────────────────────────────────────────────────────────
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="interview_sessions",
        verbose_name=_("کاربر"),
    )
    selected_questions = models.ManyToManyField(
        Question,
        through="SessionQuestion",
        related_name="sessions",
        verbose_name=_("سوالات انتخابی"),
        blank=True,
    )

    # ── تنظیمات مصاحبه (از Onboarding) ───────────────────────────────────
    target_position = models.CharField(
        max_length=150,
        verbose_name=_("موقعیت شغلی هدف"),
        help_text=_("مثال: Senior Django Developer"),
    )
    seniority_level = models.CharField(
        max_length=20,
        choices=SeniorityLevel.choices,
        default=SeniorityLevel.MID_LEVEL,
        verbose_name=_("سطح ارشدیت"),
    )
    job_description = models.TextField(
        blank=True,
        verbose_name=_("متن آگهی استخدام"),
        help_text=_("اختیاری — برای شخصی‌سازی مصاحبه"),
    )
    focus_topics = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("موضوعات تمرکز"),
        help_text=_('مثال: ["Django", "PostgreSQL", "Docker"]'),
    )

    # ── State Machine ─────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SETUP,
        db_index=True,
        verbose_name=_("وضعیت"),
    )
    current_question_index = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("ایندکس سوال فعلی"),
    )
    total_questions = models.PositiveSmallIntegerField(
        default=10,
        verbose_name=_("تعداد کل سوالات"),
    )

    # ── نتیجه نهایی ──────────────────────────────────────────────────────
    final_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("نمره نهایی"),
    )
    final_report = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("گزارش نهایی"),
        help_text=_("گزارش کامل مصاحبه به فرمت JSON"),
    )
    summary = models.TextField(
        blank=True,
        verbose_name=_("خلاصه مصاحبه"),
    )

    # ── زمان‌بندی ────────────────────────────────────────────────────────
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("زمان شروع"),
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("زمان پایان"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("زمان ایجاد"),
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("زمان بروزرسانی"))

    class Meta:
        verbose_name        = _("جلسه مصاحبه")
        verbose_name_plural = _("جلسات مصاحبه")
        db_table            = "interview_sessions"
        ordering            = ["-created_at"]
        indexes             = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user} | {self.target_position} | {self.get_status_display()}"

    # ── Properties ───────────────────────────────────────────────────────
    @property
    def duration_minutes(self) -> int | None:
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() / 60)
        return None

    @property
    def is_active(self) -> bool:
        return self.status in (
            self.Status.INTRO,
            self.Status.QUESTIONING,
            self.Status.DRILLING,
            self.Status.WRAP_UP,
        )

    @property
    def progress_percentage(self) -> float:
        if self.total_questions == 0:
            return 0
        return round((self.current_question_index / self.total_questions) * 100, 1)

    # ── Methods ───────────────────────────────────────────────────────────
    VALID_TRANSITIONS = {
    Status.SETUP:       [Status.INTRO, Status.ABANDONED],
    Status.INTRO:       [Status.QUESTIONING, Status.ABANDONED],
    Status.QUESTIONING: [Status.DRILLING, Status.WRAP_UP, Status.ABANDONED],
    Status.DRILLING:    [Status.QUESTIONING, Status.WRAP_UP, Status.ABANDONED],
    Status.WRAP_UP:     [Status.COMPLETED, Status.ABANDONED],
    Status.COMPLETED:   [],
    Status.ABANDONED:   [],
}

    def transition_to(self, new_status: str) -> None:
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValueError(f"Invalid transition from {self.status} to {new_status}")
        if new_status == self.Status.INTRO and not self.started_at:
            self.started_at = timezone.now()
        elif new_status == self.Status.COMPLETED:
            self.completed_at = timezone.now()
        self.status = new_status
        update_fields = ["status"]
        if new_status == self.Status.INTRO:
            update_fields.append("started_at")
        elif new_status == self.Status.COMPLETED:
            update_fields.append("completed_at")
        self.save(update_fields=update_fields)


# ─────────────────────────────────────────────────────────────────────────────
#  Session Question (Through Model)
#  ترتیب و وضعیت هر سوال داخل session
# ─────────────────────────────────────────────────────────────────────────────

class SessionQuestion(models.Model):

    class QuestionStatus(models.TextChoices):
        PENDING   = "pending",   _("در انتظار")
        ACTIVE    = "active",    _("فعال")
        ANSWERED  = "answered",  _("پاسخ داده شده")
        SKIPPED   = "skipped",   _("رد شده")

    session  = models.ForeignKey(
        InterviewSession,
        on_delete=models.CASCADE,
        related_name="session_questions",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,   # سوال حذف نمیشه اگه در session باشه
        related_name="session_entries",
    )
    order    = models.PositiveSmallIntegerField(
        verbose_name=_("ترتیب"),
    )
    status   = models.CharField(
        max_length=20,
        choices=QuestionStatus.choices,
        default=QuestionStatus.PENDING,
        verbose_name=_("وضعیت"),
    )

    class Meta:
        verbose_name        = _("سوال جلسه")
        verbose_name_plural = _("سوالات جلسه")
        db_table            = "session_questions"
        ordering            = ["order"]
        unique_together     = [("session", "question"), ("session", "order")]

    def __str__(self):
        return f"Session {self.session_id} | Q{self.order}: {self.question}"


# ─────────────────────────────────────────────────────────────────────────────
#  Interview Message
#  تاریخچه کامل مکالمه (برای LLM context)
# ─────────────────────────────────────────────────────────────────────────────

class InterviewMessage(models.Model):

    class Role(models.TextChoices):
        SYSTEM    = "system",    _("سیستم")
        ASSISTANT = "assistant", _("مصاحبه‌کننده")
        USER      = "user",      _("کاربر")

    class MessageType(models.TextChoices):
        GREETING     = "greeting",     _("خوش‌آمدگویی")
        QUESTION     = "question",     _("سوال اصلی")
        FOLLOW_UP    = "follow_up",    _("سوال تعقیبی")
        USER_ANSWER  = "user_answer",  _("پاسخ کاربر")
        FEEDBACK     = "feedback",     _("بازخورد")
        TRANSITION   = "transition",   _("انتقال بین سوالات")
        WRAP_UP      = "wrap_up",      _("جمع‌بندی")
        SYSTEM_EVENT = "system_event", _("رویداد سیستمی")

    session      = models.ForeignKey(
        InterviewSession,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name=_("جلسه"),
    )
    role         = models.CharField(
        max_length=20,
        choices=Role.choices,
        verbose_name=_("نقش"),
    )
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.USER_ANSWER,
        verbose_name=_("نوع پیام"),
    )
    content      = models.TextField(
        verbose_name=_("محتوا"),
    )
    turn_number  = models.PositiveSmallIntegerField(
        verbose_name=_("شماره نوبت"),
    )

    # ── ارتباط با سوال (برای پیام‌های مرتبط با سوال خاص) ─────────────────
    related_question = models.ForeignKey(
        SessionQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
        verbose_name=_("سوال مرتبط"),
    )

    # ── متادیتای اضافی (tool calls و غیره) ───────────────────────────────
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("متادیتا"),
        help_text=_("tool calls، token usage و اطلاعات اضافی"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("زمان ایجاد"),
        db_index=True,
    )

    class Meta:
        verbose_name        = _("پیام مصاحبه")
        verbose_name_plural = _("پیام‌های مصاحبه")
        db_table            = "interview_messages"
        ordering            = ["turn_number"]
        indexes             = [
            models.Index(fields=["session", "turn_number"]),
            models.Index(fields=["session", "role"]),
        ]

    def __str__(self):
        return f"[{self.get_role_display()}] Turn {self.turn_number} | {self.content[:50]}"


# ─────────────────────────────────────────────────────────────────────────────
#  User Answer + AI Evaluation
#  ترکیب مدل تو + مدل پیشنهادی من
# ─────────────────────────────────────────────────────────────────────────────

class UserAnswer(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", _("در انتظار تصحیح")
        GRADED  = "graded",  _("تصحیح شده")
        FAILED  = "failed",  _("خطا در تصحیح")

    # ── روابط ────────────────────────────────────────────────────────────
    session  = models.ForeignKey(
        InterviewSession,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name=_("جلسه"),
    )
    user     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name=_("کاربر"),
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        related_name="user_answers",
        verbose_name=_("سوال"),
    )

    # ── پاسخ کاربر ───────────────────────────────────────────────────────
    answer_text     = models.TextField(
        verbose_name=_("متن پاسخ"),
    )
    answer_duration = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("مدت زمان پاسخ (ثانیه)"),
    )
    follow_up_asked = models.BooleanField(
        default=False,
        verbose_name=_("سوال تعقیبی پرسیده شد"),
    )
    follow_up_answer = models.TextField(
        blank=True,
        verbose_name=_("پاسخ سوال تعقیبی"),
    )

    # ── نتیجه ارزیابی هوش مصنوعی ────────────────────────────────────────
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name=_("وضعیت ارزیابی"),
    )
    score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("نمره (0-100)"),
    )

    # ── جزئیات ارزیابی (همون JSON ساختاریافته‌ای که گفتی) ────────────────
    technical_accuracy = models.TextField(
        blank=True,
        verbose_name=_("دقت فنی"),
    )
    strengths          = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("نقاط قوت"),
    )
    weaknesses         = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("نقاط ضعف"),
    )
    missing_keywords   = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("کلیدواژه‌های جامانده"),
    )
    feedback           = models.TextField(
        blank=True,
        verbose_name=_("بازخورد تشریحی"),
    )
    suggested_follow_up = models.TextField(
        blank=True,
        verbose_name=_("سوال تعقیبی پیشنهادی"),
    )

    # ── raw output برای debugging ─────────────────────────────────────────
    raw_evaluation = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("خروجی خام هوش مصنوعی"),
    )
    error_log = models.TextField(
        blank=True,
        verbose_name=_("لاگ خطا"),
    )

    # ── زمان‌بندی ─────────────────────────────────────────────────────────
    created_at  = models.DateTimeField(auto_now_add=True, verbose_name=_("زمان ایجاد"))
    evaluated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("زمان ارزیابی"),
    )
    updated_at  = models.DateTimeField(auto_now=True,     verbose_name=_("زمان بروزرسانی"))

    class Meta:
        verbose_name        = _("پاسخ کاربر")
        verbose_name_plural = _("پاسخ‌های کاربران")
        db_table            = "user_answers"
        ordering            = ["-created_at"]
        unique_together     = [("session", "question")]  # هر سوال فقط یه پاسخ در هر session
        indexes             = [
            models.Index(fields=["session", "status"]),
            models.Index(fields=["user",    "status"]),
        ]

    def __str__(self):
        return f"{self.user} | Q#{self.question_id} | {self.get_status_display()}"

    @property
    def is_evaluated(self) -> bool:
        return self.status == self.Status.GRADED

    @property
    def passed(self) -> bool:
        """نمره بالای ۶۰ = قبول"""
        return bool(self.score and self.score >= 60)
