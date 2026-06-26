from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    """
    سیستم جامع مدیریت و لاگ نوتیفیکیشن‌ها (SMS, Email, In-App).
    این مدل مستقیماً با کانتینر Celery و لایه سرویس در ارتباط است.
    """

    class Type(models.TextChoices):
        SMS    = "sms",    _("پیامک")
        EMAIL  = "email",  _("ایمیل")
        IN_APP = "in_app", _("درون‌برنامه‌ای / پاپ‌آپ")

    class Status(models.TextChoices):
        PENDING = "pending", _("در انتظار ارسال")
        SENT    = "sent",    _("ارسال شده")
        FAILED  = "failed",  _("ناموفق")

    # ── ارتباطات ──────────────────────────────
    # برای پیامک‌های OTP قبل از ثبت‌نام کامل یا سناریوهای عمومی، کاربر می‌تواند null باشد.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
        verbose_name=_("کاربر"),
        db_index=True,
    )

    # ── فیلدهای اصلی ──────────────────────────
    notification_type = models.CharField(
        max_length=10,
        choices=Type.choices,
        default=Type.SMS,
        verbose_name=_("نوع اعلان"),
        db_index=True,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_("وضعیت"),
        db_index=True,
    )

    # آدرس گیرنده: شماره تلفن (09XXXXXXXXX) یا ایمیل کاربر
    recipient = models.CharField(
        max_length=255,
        verbose_name=_("گیرنده"),
        help_text=_("شماره تلفن یا آدرس ایمیل"),
    )

    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("عنوان"),
        help_text=_("بیشتر برای ایمیل و اعلان‌های درون‌برنامه‌ای"),
    )
    body = models.TextField(
        verbose_name=_("متن پیام"),
    )

    # ── جزییات فنی و دیباگ (مخصوص لایه Service و Celery) ──────
    # ذخیره شناسه منحصربه‌فرد پیام در پنل واسط (مثل کاوه‌نگار) برای پیگیری‌های بعدی
    provider_message_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("شناسه پیگیری پرووایدر"),
    )
    # ذخیره متن دقیق خطای API یا سوکت در صورت Fail شدن تسک Celery
    error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("متن خطا"),
    )
    # ثبت تعداد دفعاتی که Celery این تسک را مجدداً تلاش (Retry) کرده است
    retry_count = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("تعداد تلاش مجدد"),
    )

    # ── وضعیت اعلان‌های درون‌برنامه‌ای (In-App) ──
    is_read = models.BooleanField(
        default=False,
        verbose_name=_("خوانده شده"),
        db_index=True,
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("زمان خوانده شدن"),
    )

    # ── تاریخ‌ها ───────────────────────────────
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("زمان ایجاد"),
        db_index=True,
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("زمان ارسال واقعی"),
    )

    class Meta:
        verbose_name = _("اعلان")
        verbose_name_plural = _("اعلان‌ها")
        db_table = "notifications"
        ordering = ["-created_at"]
        # ایندکس‌های ترکیبی هوشمند برای بهینه‌سازی کوئری‌های فرانت و ادمین
        indexes = [
            models.Index(fields=["user", "is_read", "notification_type"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_notification_type_display()} | {self.recipient} | {self.get_status_display()}"

    # ── متدهای کمکی معماری (Domain Logic) ──────
    def mark_as_sent(self, provider_id: str = None) -> None:
        """تغییر وضعیت اعلان به ارسال شده موفق"""
        self.status = self.Status.SENT
        self.provider_message_id = provider_id
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "provider_message_id", "sent_at"])

    def mark_as_failed(self, error: str) -> None:
        """ثبت وضعیت شکست و ذخیره لاگ خطا"""
        self.status = self.Status.FAILED
        self.error_message = error
        self.save(update_fields=["status", "error_message"])

    def mark_as_read(self) -> None:
        """خوانده شدن نوتیفیکیشن درون‌برنامه‌ای توسط کاربر"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])
