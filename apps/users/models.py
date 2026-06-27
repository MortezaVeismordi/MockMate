import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import CustomUserManager

# ─────────────────────────────────────────────
#  Validators
# ─────────────────────────────────────────────

phone_regex = RegexValidator(
    regex=r"^09[0-9]{9}$",
    message=_("شماره تلفن باید با فرمت 09XXXXXXXXX باشد"),
)


# ─────────────────────────────────────────────
#  Custom User
# ─────────────────────────────────────────────


class CustomUser(AbstractBaseUser, PermissionsMixin):
    class ExperienceLevel(models.TextChoices):
        JUNIOR = "junior", _("جونیور")
        MID_LEVEL = "mid_level", _("میدلول")
        SENIOR = "senior", _("سنیور")
        LEAD = "lead", _("لید")

    # ── فیلدهای اصلی ──────────────────────────
    phone_number = models.CharField(
        max_length=50,
        unique=True,
        validators=[phone_regex],
        verbose_name=_("شماره تلفن"),
        db_index=True,
    )
    email = models.EmailField(
        blank=True,
        null=True,
        unique=True,
        verbose_name=_("ایمیل"),
    )

    # ── اطلاعات شخصی ──────────────────────────
    first_name = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("نام"),
    )
    last_name = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("نام خانوادگی"),
    )
    avatar = models.ImageField(
        upload_to="avatars/%Y/%m/",
        blank=True,
        null=True,
        verbose_name=_("تصویر پروفایل"),
    )

    # ── اطلاعات حرفه‌ای (برای مصاحبه) ─────────
    job_title = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("عنوان شغلی"),
    )
    experience_level = models.CharField(
        max_length=20,
        choices=ExperienceLevel.choices,
        blank=True,
        verbose_name=_("سطح تجربه"),
    )
    years_of_experience = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name=_("سال‌های تجربه"),
    )
    skills = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("مهارت‌ها"),
        help_text=_('مثال: ["Python", "Django", "Docker"]'),
    )
    bio = models.TextField(
        blank=True,
        verbose_name=_("بیوگرافی"),
    )

    # ── وضعیت حساب ────────────────────────────
    is_active = models.BooleanField(
        default=False,  # بعد از تایید OTP فعال میشه
        verbose_name=_("فعال"),
    )
    is_staff = models.BooleanField(
        default=False,
        verbose_name=_("کارمند"),
    )
    is_phone_verified = models.BooleanField(
        default=False,
        verbose_name=_("تلفن تایید شده"),
    )
    is_banned = models.BooleanField(
        default=False,
        verbose_name=_("مسدود شده"),
        db_index=True,
    )

    # ── تاریخ‌ها ───────────────────────────────
    date_joined = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("تاریخ عضویت"),
    )
    last_login_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("آخرین IP ورود"),
    )

    objects = CustomUserManager()

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("کاربر")
        verbose_name_plural = _("کاربران")
        db_table = "users"

    def __str__(self):
        return self.full_name or self.phone_number

    # ── Properties ────────────────────────────
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_profile_complete(self) -> bool:
        return bool(
            self.first_name
            and self.last_name
            and self.job_title
            and self.experience_level
        )


# ─────────────────────────────────────────────
#  OTP Code
# ─────────────────────────────────────────────


class OTPCode(models.Model):
    # ── تنظیمات ───────────────────────────────
    EXPIRE_MINUTES = getattr(settings, "OTP_EXPIRE_MINUTES", 2)
    CODE_LENGTH = getattr(settings, "OTP_CODE_LENGTH", 6)
    MAX_ATTEMPTS = getattr(settings, "OTP_MAX_ATTEMPTS", 3)
    MAX_RESEND_PER_DAY = getattr(settings, "OTP_MAX_RESEND_PER_DAY", 5)

    class Purpose(models.TextChoices):
        REGISTER = "register", _("ثبت‌نام")
        LOGIN = "login", _("ورود")
        RESET = "reset", _("بازیابی رمز")

    # ── فیلدها ────────────────────────────────
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="otp_codes",
        verbose_name=_("کاربر"),
    )
    code = models.CharField(
        max_length=6,
        verbose_name=_("کد OTP"),
    )
    purpose = models.CharField(
        max_length=20,
        choices=Purpose.choices,
        default=Purpose.LOGIN,
        verbose_name=_("هدف"),
    )
    is_used = models.BooleanField(
        default=False,
        verbose_name=_("استفاده شده"),
    )
    failed_attempts = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("تلاش‌های ناموفق"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("زمان ایجاد"),
    )
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("زمان استفاده"),
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("آدرس IP"),
    )

    class Meta:
        verbose_name = _("کد OTP")
        verbose_name_plural = _("کدهای OTP")
        db_table = "otp_codes"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_used", "created_at"]),
            models.Index(fields=["user", "purpose"]),
        ]

    def __str__(self):
        return f"{self.user.phone_number} | {self.purpose} | {self.code}"

    # ── Static Methods ─────────────────────────
    @staticmethod
    def generate_code(length: int = 6) -> str:
        """تولید کد عددی تصادفی"""
        return "".join([str(secrets.randbelow(10)) for _ in range(length)])

    # ── Properties ────────────────────────────
    @property
    def expire_at(self):
        return self.created_at + timedelta(minutes=self.EXPIRE_MINUTES)

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expire_at

    @property
    def is_max_attempts_reached(self) -> bool:
        return self.failed_attempts >= self.MAX_ATTEMPTS

    @property
    def is_valid(self) -> bool:
        return (
            not self.is_used
            and not self.is_expired
            and not self.is_max_attempts_reached
        )

    @property
    def remaining_seconds(self) -> int:
        """ثانیه‌های باقی‌مانده تا انقضا"""
        delta = self.expire_at - timezone.now()
        return max(0, int(delta.total_seconds()))

    # ── Class Methods ──────────────────────────
    @classmethod
    def get_daily_resend_count(cls, user) -> int:
        """تعداد ارسال در ۲۴ ساعت گذشته"""
        since = timezone.now() - timedelta(hours=24)
        return cls.objects.filter(
            user=user,
            created_at__gte=since,
        ).count()

    @classmethod
    def invalidate_previous(cls, user, purpose: str) -> None:
        """غیرمعتبر کردن کدهای قبلی همین هدف"""
        cls.objects.filter(
            user=user,
            purpose=purpose,
            is_used=False,
        ).update(is_used=True)

    @classmethod
    def create_otp(
        cls,
        user,
        purpose: str = "login",
        ip_address: str = None,
    ) -> "OTPCode":
        """
        ایجاد OTP جدید
        - کدهای قبلی همین هدف رو غیرمعتبر میکنه
        - چک میکنه روزانه بیشتر از حد مجاز نباشه
        """
        # چک تعداد روزانه
        daily_count = cls.get_daily_resend_count(user)
        if daily_count >= cls.MAX_RESEND_PER_DAY:
            raise ValueError(
                _("تعداد درخواست OTP امروز به حد مجاز رسیده. فردا دوباره تلاش کنید")
            )

        # غیرمعتبر کردن کدهای قبلی
        cls.invalidate_previous(user, purpose)

        # ساخت کد جدید
        otp = cls.objects.create(
            user=user,
            code=cls.generate_code(cls.CODE_LENGTH),
            purpose=purpose,
            ip_address=ip_address,
        )
        return otp

    @classmethod
    def verify_otp(
        cls,
        user,
        code: str,
        purpose: str = "login",
    ) -> tuple[bool, str]:
        """
        تایید کد OTP
        Returns: (success: bool, message: str)
        """
        try:
            otp = cls.objects.filter(
                user=user,
                purpose=purpose,
                is_used=False,
            ).latest("created_at")

        except cls.DoesNotExist:
            return False, _("کد OTP یافت نشد. لطفاً مجدداً درخواست کنید")

        # چک انقضا
        if otp.is_expired:
            return False, _("کد OTP منقضی شده است")

        # چک تعداد تلاش
        if otp.is_max_attempts_reached:
            return False, _("تعداد تلاش‌های مجاز به پایان رسید")

        # چک کد
        if otp.code != code:
            otp.failed_attempts += 1
            otp.save(update_fields=["failed_attempts"])

            remaining = cls.MAX_ATTEMPTS - otp.failed_attempts
            return False, _(f"کد اشتباه است. {remaining} تلاش باقی‌مانده")

        # ── موفق ──────────────────────────────
        otp.is_used = True
        otp.used_at = timezone.now()
        otp.save(update_fields=["is_used", "used_at"])

        return True, _("کد OTP با موفقیت تایید شد")
