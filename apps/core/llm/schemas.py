# apps/core/llm/schemas.py
# =============================================================================
# LLM Structured Output Schemas — Pydantic Models
# =============================================================================

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# =============================================================================
#  Evaluation Result
#  خروجی ارزیابی هر پاسخ کاربر
# =============================================================================


class EvaluationResult(BaseModel):
    """
    ساختار خروجی ارزیابی هر پاسخ.
    LLM مجبوره دقیقاً این فرمت رو برگردونه.
    """

    score: int = Field(
        ge=0,
        le=100,
        description=(
            "نمره کلی پاسخ از ۰ تا ۱۰۰. "
            "راهنما: "
            "۰-۳۰: پاسخ ضعیف یا اشتباه، "
            "۳۱-۵۹: پاسخ ناقص، "
            "۶۰-۷۹: پاسخ قابل قبول، "
            "۸۰-۸۹: پاسخ خوب، "
            "۹۰-۱۰۰: پاسخ عالی و کامل."
        ),
    )

    technical_accuracy: str = Field(
        min_length=20,
        max_length=500,
        description=(
            "تحلیل دقت فنی پاسخ به زبان فارسی. "
            "توضیح بده که کاربر مفهوم رو درست فهمیده یا نه "
            "و چقدر با پاسخ مرجع همخوانی داره."
        ),
    )

    strengths: list[str] = Field(
        min_length=1,
        max_length=5,
        description=(
            "لیست نقاط قوت پاسخ به زبان فارسی. "
            "هر آیتم یه جمله کوتاه و مشخص باشه. "
            "حداقل یه نقطه قوت حتی برای پاسخ‌های ضعیف پیدا کن."
        ),
    )

    weaknesses: list[str] = Field(
        default_factory=list,
        max_length=5,
        description=(
            "لیست نقاط ضعف یا موارد جامانده به زبان فارسی. "
            "اگه پاسخ کامل بود میتونه خالی باشه. "
            "هر آیتم مشخص و قابل بهبود باشه."
        ),
    )

    missing_keywords: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "کلیدواژه‌های فنی مهمی که کاربر اشاره نکرد. "
            "فقط کلیدواژه‌های واقعاً مهم رو بنویس. "
            "مثال: ['OOMKilled', 'connection pooling', 'index scan']"
        ),
    )

    feedback: str = Field(
        min_length=30,
        max_length=800,
        description=(
            "بازخورد تشریحی و سازنده به زبان فارسی. "
            "لحن مثبت و تشویقی داشته باش. "
            "نکات قابل بهبود رو با مثال توضیح بده. "
            "از 'شما' برای مخاطب قرار دادن کاربر استفاده کن."
        ),
    )

    suggested_follow_up: str = Field(
        default="",
        max_length=300,
        description=(
            "سوال تعقیبی پیشنهادی برای عمیق‌تر کردن بررسی. "
            "اگه نیازی نیست خالی بذار. "
            "سوال باید مشخص و مرتبط با پاسخ کاربر باشه."
        ),
    )

    confidence_level: Literal["low", "medium", "high"] = Field(
        default="medium",
        description=(
            "سطح اطمینان تو از ارزیابی. "
            "low: پاسخ مبهم بود، "
            "medium: ارزیابی معقول، "
            "high: پاسخ واضح و قابل ارزیابی دقیق بود."
        ),
    )

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("strengths")
    @classmethod
    def strengths_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("حداقل یه نقطه قوت باید وجود داشته باشه.")
        return v

    @field_validator("strengths", "weaknesses", "missing_keywords")
    @classmethod
    def items_not_blank(cls, v: list) -> list:
        cleaned = [item.strip() for item in v if item.strip()]
        return cleaned

    @model_validator(mode="after")
    def high_score_needs_few_weaknesses(self) -> "EvaluationResult":
        """پاسخ عالی نباید ضعف زیاد داشته باشه"""
        if self.score >= 90 and len(self.weaknesses) > 2:
            self.weaknesses = self.weaknesses[:2]
        return self

    @model_validator(mode="after")
    def low_score_needs_weaknesses(self) -> "EvaluationResult":
        """پاسخ ضعیف باید حداقل یه ضعف داشته باشه"""
        if self.score < 40 and not self.weaknesses:
            raise ValueError("پاسخ با نمره زیر ۴۰ باید حداقل یه نقطه ضعف داشته باشه.")
        return self


# =============================================================================
#  Agent Decision
#  تصمیم agent بعد از هر پاسخ کاربر
# =============================================================================


class AgentDecision(BaseModel):
    """
    تصمیم agent برای ادامه مصاحبه.
    برای logging، audit trail و debugging استفاده میشه.
    """

    action: Literal["next_question", "follow_up", "wrap_up"] = Field(
        description=(
            "تصمیم بعدی: "
            "next_question: پاسخ کافی بود، سوال بعدی, "
            "follow_up: نیاز به بررسی بیشتر داره, "
            "wrap_up: مصاحبه تموم شده."
        ),
    )

    follow_up_question: Optional[str] = Field(
        default=None,
        max_length=300,
        description=(
            "سوال تعقیبی — فقط وقتی action=follow_up باشه. " "سوال باید مشخص، کوتاه و مستقیماً مرتبط با پاسخ کاربر باشه."
        ),
    )

    reasoning: str = Field(
        min_length=10,
        max_length=300,
        description=("دلیل این تصمیم به زبان فارسی. " "کوتاه و واضح توضیح بده چرا این action رو انتخاب کردی."),
    )

    # ── Validators ────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def follow_up_required_when_action_is_follow_up(self) -> "AgentDecision":
        if self.action == "follow_up" and not self.follow_up_question:
            raise ValueError("وقتی action=follow_up هست باید follow_up_question مشخص باشه.")
        if self.action != "follow_up" and self.follow_up_question:
            self.follow_up_question = None
        return self


# =============================================================================
#  Final Report
#  گزارش نهایی مصاحبه
# =============================================================================


class SkillAssessment(BaseModel):
    """ارزیابی یه مهارت خاص"""

    skill_name: str = Field(
        description="نام مهارت یا حوزه فنی — به فارسی یا انگلیسی",
    )
    level: Literal["weak", "developing", "proficient", "strong", "expert"] = Field(
        description=(
            "سطح مهارت: "
            "weak: ضعیف، "
            "developing: در حال پیشرفت، "
            "proficient: قابل قبول، "
            "strong: قوی، "
            "expert: متخصص."
        ),
    )
    evidence: str = Field(
        max_length=200,
        description="شواهدی از مصاحبه که این سطح رو نشون میده.",
    )


class FinalReport(BaseModel):
    """
    گزارش تحلیلی کامل مصاحبه.
    بعد از اتمام همه سوالات تولید میشه.
    """

    overall_assessment: str = Field(
        min_length=100,
        max_length=1000,
        description=(
            "ارزیابی کلی و جامع از عملکرد کاربر در طول مصاحبه به زبان فارسی. "
            "لحن حرفه‌ای و سازنده داشته باش. "
            "نقاط برجسته و مهم رو ذکر کن."
        ),
    )

    technical_level: Literal["intern", "junior", "mid_level", "senior", "lead"] = Field(
        description=("سطح فنی واقعی کاربر بر اساس پاسخ‌های مصاحبه. " "ممکنه با سطح درخواستی کاربر متفاوت باشه."),
    )

    skill_breakdown: list[SkillAssessment] = Field(
        min_length=2,
        max_length=8,
        description=("تحلیل مهارت‌های مختلف کاربر. " "فقط مهارت‌هایی که در مصاحبه بررسی شدن رو بنویس."),
    )

    strongest_areas: list[str] = Field(
        min_length=1,
        max_length=5,
        description=("قوی‌ترین حوزه‌های کاربر بر اساس مصاحبه. " "مشخص و فنی باشه — مثال: 'طراحی دیتابیس و ایندکس‌گذاری'."),
    )

    improvement_areas: list[str] = Field(
        min_length=1,
        max_length=5,
        description=("حوزه‌هایی که کاربر نیاز به تقویت داره. " "سازنده و قابل اقدام باشه."),
    )

    hiring_recommendation: Literal[
        "strong_yes",  # قطعاً استخدام کن
        "yes",  # استخدام پیشنهاد میشه
        "maybe",  # بستگی به نیاز داره
        "no",  # پیشنهاد نمیشه
        "strong_no",  # قطعاً استخدام نکن
    ] = Field(
        description=("توصیه استخدام بر اساس عملکرد کلی. " "فقط بر اساس مصاحبه قضاوت کن."),
    )

    hiring_reasoning: str = Field(
        min_length=50,
        max_length=400,
        description=("دلیل توصیه استخدام به زبان فارسی. " "مشخص و مستند به پاسخ‌های مصاحبه باشه."),
    )

    study_suggestions: list[str] = Field(
        min_length=2,
        max_length=6,
        description=(
            "پیشنهادات مطالعاتی مشخص و قابل اقدام. "
            "میتونه کتاب، مفهوم، یا حوزه فنی باشه. "
            "مثال: 'مطالعه فصل Indexing کتاب DDIA'."
        ),
    )

    readiness_score: int = Field(
        ge=0,
        le=100,
        description=(
            "نمره آمادگی کلی برای پوزیشن درخواستی از ۰ تا ۱۰۰. "
            "این با میانگین نمرات فرق داره — "
            "یه کاربر میتونه نمره خوب داشته باشه ولی "
            "آمادگی کافی برای اون پوزیشن خاص نداشته باشه."
        ),
    )

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("strongest_areas", "improvement_areas", "study_suggestions")
    @classmethod
    def items_not_blank(cls, v: list) -> list:
        return [item.strip() for item in v if item.strip()]

    @model_validator(mode="after")
    def senior_recommendation_consistency(self) -> "FinalReport":
        """
        اگه technical_level خیلی پایین‌تر از پوزیشن بود،
        hiring_recommendation نباید strong_yes باشه
        """
        weak_levels = {"intern", "junior"}
        if self.technical_level in weak_levels and self.hiring_recommendation == "strong_yes":
            self.hiring_recommendation = "maybe"
        return self


# =============================================================================
#  Streaming Chunk
#  برای streaming پاسخ LLM از طریق WebSocket
# =============================================================================


class StreamingChunk(BaseModel):
    """
    هر chunk از streaming پاسخ LLM.
    از طریق WebSocket به client push میشه.
    """

    chunk_type: Literal["token", "tool_call", "done", "error"] = Field(
        description="نوع chunk",
    )
    content: str = Field(
        default="",
        description="محتوای chunk",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="اطلاعات اضافی — مثل tool_name یا error_message",
    )
