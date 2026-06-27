from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (Question, QuestionAttachment, QuestionCategory,
                     QuestionOption)


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 3
    fields = ("text", "is_correct")


class QuestionAttachmentInline(admin.StackedInline):
    model = QuestionAttachment
    extra = 1
    fields = ("file", "attachment_type")


@admin.register(QuestionCategory)
class QuestionCategoryAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "parent", "created_at")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    list_filter = ("parent",)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "question_type",
        "seniority_level",
        "estimated_time",
        "source",
        "is_active",
    )
    list_filter = (
        "question_type",
        "seniority_level",
        "source",
        "is_active",
        "categories",
    )
    search_fields = ("title", "body", "reference_answer")
    filter_horizontal = ("categories",)

    inlines = [QuestionOptionInline, QuestionAttachmentInline]

    fieldsets = (
        (
            _("General Information"),
            {"fields": ("title", "body", "estimated_time", "code_template")},
        ),
        (
            _("Classification & Rules"),
            {"fields": ("question_type", "seniority_level", "categories")},
        ),
        (
            _("AI & Evaluation Engine"),
            {
                "fields": ("reference_answer", "ai_evaluation_criteria"),
                "description": _(
                    "اطلاعات این بخش مستقیماً به پرامپت هوش مصنوعی برای ارزیابی پاسخ کاربر تزریق می‌شود."
                ),
            },
        ),
        (
            _("System Metadata"),
            {
                "fields": ("is_active", "source", "source_url"),
                "classes": ("collapse",),
            },
        ),
    )
