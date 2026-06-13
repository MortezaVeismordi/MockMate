from django.db import models
from django.utils.translation import gettext_lazy as _


class QuestionCategory(models.Model):
    title = models.CharField(_("Title"), max_length=100, unique=True)
    slug = models.SlugField(_("Slug"), max_length=120, unique=True, db_index=True)
    description = models.TextField(_("Description"), blank=True, null=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_("Parent Category")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Question Category")
        verbose_name_plural = _("Question Categories")
        ordering = ['title']

    def __str__(self):
        if self.parent:
            return f"{self.parent.title} -> {self.title}"
        return self.title


class Question(models.Model):
    class QuestionType(models.TextChoices):
        TECHNICAL = 'technical', _('Technical / Coding')
        MULTIPLE_CHOICE = 'multiple_choice', _('Multiple Choice / Quiz')
        ARCHITECTURE = 'architecture', _('Architecture / Design Patterns')
        SYSTEM_DESIGN = 'system_design', _('System Design')
        DEVOPS = 'devops', _('DevOps / Infrastructure')
        BEHAVIORAL = 'behavioral', _('Behavioral / HR')

    class SeniorityLevel(models.TextChoices):
        INTERN = 'intern', _('Intern')
        JUNIOR = 'junior', _('Junior')
        MID_LEVEL = 'mid_level', _('Mid-Level')
        SENIOR = 'senior', _('Senior')
        LEAD = 'lead', _('Lead / Principal')

    class SourceType(models.TextChoices):
        MANUAL = 'manual', _('Manually Added')
        AI_GENERATED = 'ai_generated', _('AI Generated & Cached')
        GITHUB_IMPORT = 'github_import', _('Imported from GitHub')

    title = models.CharField(_("Title/Concept"), max_length=255, help_text=_("مفهوم کلیدی یا عنوان کوتاه سوال"))
    body = models.TextField(_("Question Body/Scenario"), help_text=_("صورت کامل سوال یا سناریوی مطرح شده"))
    
    # فیلدهای مدیریت زمان و قالب‌های اجرایی
    estimated_time = models.PositiveIntegerField(_("Estimated Time (Seconds)"), default=120, help_text=_("زمان پیشنهادی برای پاسخ به این سوال"))
    code_template = models.TextField(_("Code Template"), blank=True, null=True, help_text=_("قالب کد اولیه برای سوالات کدنویسی"))

    question_type = models.CharField(_("Question Type"), max_length=30, choices=QuestionType.choices, default=QuestionType.TECHNICAL, db_index=True)
    seniority_level = models.CharField(_("Seniority Level"), max_length=20, choices=SeniorityLevel.choices, default=SeniorityLevel.MID_LEVEL, db_index=True)
    categories = models.ManyToManyField(QuestionCategory, related_name='questions', verbose_name=_("Categories / Skills"))
    
    reference_answer = models.TextField(_("Reference Answer"), help_text=_("پاسخ ایده‌آل و نکات کلیدی برای راهنمایی تصحیح هوش مصنوعی"))
    ai_evaluation_criteria = models.JSONField(_("AI Evaluation Criteria"), default=dict, blank=True, help_text=_("کلیدواژه‌های اجباری و وزن نمره‌دهی"))
    
    is_active = models.BooleanField(_("Is Active"), default=True, db_index=True)
    source = models.CharField(_("Source"), max_length=20, choices=SourceType.choices, default=SourceType.MANUAL)
    source_url = models.URLField(_("Source URL"), blank=True, null=True, max_length=500)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Question")
        verbose_name_plural = _("Questions")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['question_type', 'seniority_level', 'is_active']),
        ]

    def __str__(self):
        return f"[{self.get_seniority_level_display()}] {self.title}"


class QuestionOption(models.Model):
    """
    گزینه‌های سوال (مخصوص سوالات تستی یا چند گزینه‌ای)
    """
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options', verbose_name=_("Question"))
    text = models.CharField(_("Option Text"), max_length=500)
    is_correct = models.BooleanField(_("Is Correct Option"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Question Option")
        verbose_name_plural = _("Question Options")


class QuestionAttachment(models.Model):
    """
    پیوست‌های جانبی سوال مثل سناریوهای متنی سنگین، فایلهای تنظیمات کانتینر یا تصاویر معماری
    """
    class AttachmentType(models.TextChoices):
        IMAGE = 'image', _('Diagram / Image')
        CODE_FILE = 'code_file', _('Configuration / Source Code File')
        DOCUMENT = 'document', _('Supplementary Document')

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='attachments', verbose_name=_("Question"))
    file = models.FileField(_("Attachment File"), upload_to='questions/attachments/')
    attachment_type = models.CharField(_("Attachment Type"), max_length=20, choices=AttachmentType.choices, default=AttachmentType.CODE_FILE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Question Attachment")
        verbose_name_plural = _("Question Attachments")