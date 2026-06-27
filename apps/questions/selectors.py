import random

from django.db.models import QuerySet

from apps.questions.models import Question


def question_list(
    *, is_active: bool = True, category_slug: str = None, seniority_level: str = None
) -> QuerySet[Question]:
    """
    سلکتور پایه و بهینه برای واکشی و فیلتر کردن سوالات مصاحبه.

    * دغدغه پرفورمنس: از prefetch_related برای لود پیش‌فرض دسته‌بندی‌ها (روابط ManyToMany)
      استفاده شده تا بعداً در سریالایزر با فاجعه N+1 Query مواجه نشویم.
    * دغدغه ارشدیت: آرگومان‌ها با (*,) قفل شده‌اند تا صراحت ورود دیتا تضمین شود.
    """
    # بهینه‌سازی لایه دیتابیس برای روابط ManyToMany
    qs = Question.objects.prefetch_related("categories").filter(is_active=is_active)

    if category_slug:
        # فیلتر مستقیم و بدون افزونگی روی اسلاگ دسته‌بندی
        qs = qs.filter(categories__slug=category_slug)

    if seniority_level:
        qs = qs.filter(seniority_level=seniority_level)

    # استفاده از distinct برای جلوگیری از رکوردهای تکراری ناشی از Join با لایه دسته‌بندی‌ها
    return qs.distinct().order_by("-created_at")


def get_random_interview_set(
    *, category_slug: str = None, seniority_level: str = None, limit: int = 5
) -> list[Question]:
    """
    یک سلکتور هوشمند برای چیدن سناریوی مصاحبه رندوم.

    نکته معماری: متد order_by('?') در دیتابیس‌های انترپرایز مثل PostgreSQL کل جدول را
    در حافظه موقت کپی و رندوم می‌کند که یک کابوس برای پرفورمنس است. اینجا ابتدا
    فقط IDها را بیرون کشیده، در لایه پایتون رندوم می‌کنیم و سپس سوالات فیزیکی را می‌خوانیم.
    """
    # بازیافت منطق فیلترینگ از سلکتور قبلی (پیروی از اصل DRY)
    base_qs = question_list(
        category_slug=category_slug, seniority_level=seniority_level
    )

    # واکشی فوق‌العاده سبک و بهینه فقط برای لایه IDها
    question_ids = list(base_qs.values_list("id", flat=True))

    if not question_ids:
        return []

    # نمونه‌برداری تصادفی و ایمن در سطح Memory پایتون
    sampled_ids = random.sample(question_ids, min(len(question_ids), limit))

    # واکشی نهایی رکوردهای گلچین‌شده همراه با بهینه‌سازی لایه روابط
    return list(
        Question.objects.prefetch_related("categories").filter(id__in=sampled_ids)
    )
