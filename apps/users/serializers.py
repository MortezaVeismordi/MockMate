import logging
from datetime import timedelta

from django.contrib.auth import get_user_model ,authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.validators import RegexValidator
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import OTPCode

logger = logging.getLogger(__name__)
User = get_user_model()


# ═══════════════════════════════════════════════════════════════════
#  Validators
# ═══════════════════════════════════════════════════════════════════

phone_validator = RegexValidator(
    regex=r"^09[0-9]{9}$",
    message=_("شماره موبایل باید با فرمت 09XXXXXXXXX و ۱۱ رقم باشد"),
)

otp_code_validator = RegexValidator(
    regex=r"^\d{6}$",
    message=_("کد OTP باید دقیقاً ۶ رقم عددی باشد"),
)


# ═══════════════════════════════════════════════════════════════════
#  Mixins
# ═══════════════════════════════════════════════════════════════════

class PhoneNormalizerMixin:
    """نرمال‌سازی شماره تلفن ایرانی."""

    def validate_phone_number(self, value: str) -> str:
        value = value.strip()

        if value.startswith("+98"):
            value = "0" + value[3:]
        elif value.startswith("98") and len(value) == 12:
            value = "0" + value[2:]

        phone_validator(value)
        return value


class TokenGeneratorMixin:
    """تولید JWT توکن."""

    @staticmethod
    def get_tokens_for_user(user) -> dict:
        refresh = RefreshToken.for_user(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class AvatarURLMixin:
    """تولید URL کامل آواتار."""

    def get_avatar_url(self, obj) -> str | None:
        if not obj.avatar:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.avatar.url)
        return obj.avatar.url


# ═══════════════════════════════════════════════════════════════════
#                        AUTH SERIALIZERS
# ═══════════════════════════════════════════════════════════════════


class SendOTPSerializer(PhoneNormalizerMixin, serializers.Serializer):
    """
    POST /auth/send-otp/

    Request:
        {
            "phone_number": "09123456789",
            "purpose": "login"
        }

    Response:
        {
            "message": "کد OTP ارسال شد",
            "remaining_seconds": 120,
            "is_new_user": true
        }
    """

    phone_number = serializers.CharField(
        max_length=15,
        label=_("شماره موبایل"),
        help_text=_("مثال: 09123456789"),
    )
    purpose = serializers.ChoiceField(
    choices=OTPCode.Purpose.choices,
    label=_("هدف"),
    )

    def validate(self, attrs: dict) -> dict:
        phone_number = attrs["phone_number"]
        purpose = attrs["purpose"]

        # ── هدف reset: کاربر باید وجود داشته باشه
        if purpose == OTPCode.Purpose.RESET:
            if not User.objects.filter(phone_number=phone_number).exists():
                raise serializers.ValidationError(
                    {"phone_number": _("کاربری با این شماره یافت نشد")}
                )

        # ── چک cooldown: آیا هنوز کد قبلی معتبره؟
        try:
            user = User.objects.get(phone_number=phone_number)
            latest_otp = OTPCode.objects.filter(
                user=user,
                purpose=purpose,
                is_used=False,
            ).latest("created_at")

            if latest_otp.is_valid:
                remaining = latest_otp.remaining_seconds
                if remaining > 90:  # اگه بیشتر از ۹۰ ثانیه مونده
                    raise serializers.ValidationError(
                        {
                            "phone_number": _(
                                f"کد قبلی هنوز معتبره. {remaining} ثانیه صبر کنید"
                            )
                        }
                    )
        except (User.DoesNotExist, OTPCode.DoesNotExist):
            pass

        return attrs


class ResendOTPSerializer(PhoneNormalizerMixin, serializers.Serializer):
    """
    POST /auth/resend-otp/

    Request:
        {
            "phone_number": "09123456789",
            "purpose": "login"
        }

    Response:
        {
            "message": "کد OTP مجدداً ارسال شد",
            "remaining_seconds": 120,
            "daily_remaining": 3
        }
    """

    phone_number = serializers.CharField(
        max_length=15,
        label=_("شماره موبایل"),
    )
    purpose = serializers.ChoiceField(
        choices=OTPCode.Purpose.choices,
        default=OTPCode.Purpose.LOGIN,
        label=_("هدف"),
    )

    def validate(self, attrs: dict) -> dict:
        phone_number = attrs["phone_number"]

        # ── کاربر باید وجود داشته باشه (قبلاً send-otp زده)
        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {"phone_number": _("ابتدا باید درخواست ارسال OTP بدید")}
            )

        # ── چک cooldown: حداقل ۶۰ ثانیه بین هر resend
        try:
            latest_otp = OTPCode.objects.filter(
                user=user,
                purpose=attrs["purpose"],
            ).latest("created_at")

            elapsed = (timezone.now() - latest_otp.created_at).total_seconds()
            min_interval = 60  # حداقل ۶۰ ثانیه
            if elapsed < min_interval:
                wait = int(min_interval - elapsed)
                raise serializers.ValidationError(
                    {"phone_number": _(f"{wait} ثانیه تا ارسال مجدد صبر کنید")}
                )
        except OTPCode.DoesNotExist:
            raise serializers.ValidationError(
                {"phone_number": _("ابتدا باید درخواست ارسال OTP بدید")}
            )

        # ── چک سقف روزانه
        daily_count = OTPCode.get_daily_resend_count(user)
        if daily_count >= OTPCode.MAX_RESEND_PER_DAY:
            raise serializers.ValidationError(
                {
                    "phone_number": _(
                        "تعداد درخواست OTP امروز به حد مجاز رسیده. فردا تلاش کنید"
                    )
                }
            )

        attrs["_user"] = user
        attrs["_daily_remaining"] = OTPCode.MAX_RESEND_PER_DAY - daily_count - 1
        return attrs


class VerifyOTPSerializer(
    PhoneNormalizerMixin, TokenGeneratorMixin, serializers.Serializer
):
    """
    POST /auth/verify-otp/

    Request:
        {
            "phone_number": "09123456789",
            "code": "123456",
            "purpose": "login"
        }

    Response:
        {
            "tokens": {"access": "...", "refresh": "..."},
            "user": {...},
            "is_new_user": true,
            "is_profile_complete": false
        }
    """

    phone_number = serializers.CharField(
        max_length=15,
        label=_("شماره موبایل"),
    )
    code = serializers.CharField(
        max_length=6,
        min_length=6,
        validators=[otp_code_validator],
        label=_("کد OTP"),
    )
    purpose = serializers.ChoiceField(
        choices=OTPCode.Purpose.choices,
        default=OTPCode.Purpose.LOGIN,
        label=_("هدف"),
    )

    def validate(self, attrs: dict) -> dict:
        from .services import OTPService

        result = OTPService.verify_otp(
            phone_number=attrs["phone_number"],
            code=attrs["code"],
            purpose=attrs["purpose"],
        )

        if not result["success"]:
            raise serializers.ValidationError({"code": result["message"]})

        self._verified_user = result["user"]
        self._is_new_user = result.get("is_new_user", False)
        return attrs

    def to_representation(self, validated_data) -> dict:
        user = self._verified_user
        return {
            "tokens": self.get_tokens_for_user(user),
            "user": UserPublicSerializer(user, context=self.context).data,
            "is_new_user": self._is_new_user,
            "is_profile_complete": user.is_profile_complete,
        }


class RefreshTokenSerializer(serializers.Serializer):
    """
    POST /auth/refresh-token/

    Request:
        {"refresh": "eyJ..."}

    Response:
        {"access": "eyJ...", "refresh": "eyJ..."}
    """

    refresh = serializers.CharField(
        label=_("توکن رفرش"),
    )

    def validate_refresh(self, value: str) -> str:
        try:
            self._token = RefreshToken(value)
        except Exception:
            raise serializers.ValidationError(
                _("توکن نامعتبر یا منقضی شده است")
            )
        return value

    def to_representation(self, validated_data) -> dict:
    # blacklist کردن token قدیمی
        self._token.blacklist()
        # ساختن token کاملاً جدید برای همون user
        from apps.users.models import CustomUser
        user_id = self._token.payload.get("user_id")
        user = CustomUser.objects.get(phone_number=user_id)
        new_token = RefreshToken.for_user(user)
        return {
            "access": str(new_token.access_token),
            "refresh": str(new_token),
        }


class LogoutSerializer(serializers.Serializer):
    """
    POST /auth/logout/

    Request:
        {"refresh_token": "eyJ..."}
    """

    refresh_token = serializers.CharField(
        label=_("توکن رفرش"),
    )

    def validate_refresh_token(self, value: str) -> str:
        try:
            self._token = RefreshToken(value)
        except Exception:
            raise serializers.ValidationError(
                _("توکن نامعتبر یا منقضی شده است")
            )
        return value

    def save(self) -> None:
        try:
            self._token.blacklist()
        except Exception as exc:
            logger.error("Logout blacklist error: %s", exc)
            raise serializers.ValidationError(
                _("خطا در خروج از سیستم")
            )


# ═══════════════════════════════════════════════════════════════════
#                      PROFILE SERIALIZERS
# ═══════════════════════════════════════════════════════════════════


class UserPublicSerializer(AvatarURLMixin, serializers.ModelSerializer):
    """
    اطلاعات عمومی کاربر — read only.
    استفاده در response بعد از verify-otp و جاهای دیگه.
    """

    full_name = serializers.CharField(read_only=True)
    is_profile_complete = serializers.BooleanField(read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "phone_number",
            "full_name",
            "first_name",
            "last_name",
            "avatar_url",
            "job_title",
            "experience_level",
            "is_profile_complete",
            "is_phone_verified",
            "date_joined",
        )
        read_only_fields = fields


class UserMeSerializer(AvatarURLMixin, serializers.ModelSerializer):
    """
    GET  /me/   →  پروفایل کامل
    PATCH /me/  →  ویرایش partial

    Read-only fields: id, phone_number, full_name, avatar_url, ...
    Writable fields:  first_name, last_name, email, bio, job_title,
                      experience_level, years_of_experience, skills
    """

    full_name = serializers.CharField(read_only=True)
    is_profile_complete = serializers.BooleanField(read_only=True)
    avatar_url = serializers.SerializerMethodField()
    interview_count = serializers.SerializerMethodField()
    skills = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        allow_empty=True,
        max_length=30,
        label=_("مهارت‌ها"),
    )

    class Meta:
        model = User
        fields = (
            "id",
            "phone_number",
            "email",
            "full_name",
            "first_name",
            "last_name",
            "avatar_url",
            "bio",
            "job_title",
            "experience_level",
            "years_of_experience",
            "skills",
            "is_active",
            "is_profile_complete",
            "is_phone_verified",
            "interview_count",
            "date_joined",
            "last_login",
        )
        read_only_fields = (
            "id",
            "phone_number",
            "full_name",
            "avatar_url",
            "is_active",
            "is_profile_complete",
            "is_phone_verified",
            "interview_count",
            "date_joined",
            "last_login",
        )

    # ── Field Validations ──────────────────────────

    def validate_email(self, value: str) -> str:
        if not value:
            return value

        value = value.lower().strip()
        qs = User.objects.filter(email=value)

        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                _("این ایمیل قبلاً ثبت شده است")
            )
        return value

    def validate_first_name(self, value: str) -> str:
        value = value.strip()
        if value and len(value) < 2:
            raise serializers.ValidationError(
                _("نام باید حداقل ۲ کاراکتر باشد")
            )
        return value

    def validate_last_name(self, value: str) -> str:
        value = value.strip()
        if value and len(value) < 2:
            raise serializers.ValidationError(
                _("نام خانوادگی باید حداقل ۲ کاراکتر باشد")
            )
        return value

    def validate_years_of_experience(self, value: int) -> int:
        if value is not None and (value < 0 or value > 50):
            raise serializers.ValidationError(
                _("سال‌های تجربه باید بین ۰ تا ۵۰ باشد")
            )
        return value

    def validate_skills(self, value: list) -> list:
        cleaned = list({skill.strip() for skill in value if skill.strip()})
        if len(cleaned) > 30:
            raise serializers.ValidationError(
                _("حداکثر ۳۰ مهارت مجاز است")
            )
        return sorted(cleaned)

    def validate_bio(self, value: str) -> str:
        value = value.strip()
        if len(value) > 500:
            raise serializers.ValidationError(
                _("بیوگرافی نباید بیشتر از ۵۰۰ کاراکتر باشد")
            )
        return value

    # ── Cross-field Validation ─────────────────────

    def validate(self, attrs: dict) -> dict:
        exp_level = attrs.get(
            "experience_level",
            getattr(self.instance, "experience_level", None),
        )
        years = attrs.get(
            "years_of_experience",
            getattr(self.instance, "years_of_experience", None),
        )

        if exp_level and years is None:
            raise serializers.ValidationError(
                {
                    "years_of_experience": _(
                        "با انتخاب سطح تجربه، سال‌های تجربه هم الزامی است"
                    )
                }
            )

        # سازگاری سطح با سال تجربه
        if exp_level and years is not None:
            level_year_map = {
                User.ExperienceLevel.JUNIOR: (0, 2),
                User.ExperienceLevel.MID_LEVEL: (2, 5),
                User.ExperienceLevel.SENIOR: (5, 12),
                User.ExperienceLevel.LEAD: (8, 50),
            }
            min_y, max_y = level_year_map.get(exp_level, (0, 50))
            if not (min_y <= years <= max_y):
                raise serializers.ValidationError(
                    {
                        "years_of_experience": _(
                            f"برای سطح {exp_level}، تجربه باید بین "
                            f"{min_y} تا {max_y} سال باشد"
                        )
                    }
                )

        return attrs

    # ── Computed Fields ────────────────────────────

    def get_interview_count(self, obj) -> int:
        if hasattr(obj, "_interview_count"):
            return obj._interview_count
        # lazy fallback
        return getattr(obj, "interview_sessions", obj.__class__.objects.none()).count()

    # ── Update ─────────────────────────────────────

    def update(self, instance, validated_data: dict):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save(update_fields=list(validated_data.keys()))

        logger.info(
            "Profile updated | pk=%s | fields=%s",
            instance.pk,
            list(validated_data.keys()),
        )
        return instance


class CompleteProfileSerializer(serializers.ModelSerializer):
    """
    POST /me/complete-profile/

    فقط فیلدهای حیاتی برای شروع اولین مصاحبه.
    بعد از تکمیل، سیگنال user_profile_completed ارسال میشه.

    Request:
        {
            "first_name": "علی",
            "last_name": "رضایی",
            "job_title": "Backend Developer",
            "experience_level": "mid_level",
            "years_of_experience": 3,
            "skills": ["Python", "Django", "Docker"]
        }
    """

    skills = serializers.ListField(
        child=serializers.CharField(max_length=50),
        min_length=1,
        max_length=30,
        label=_("مهارت‌ها"),
    )

    first_name = serializers.CharField(required=True, max_length=50)
    last_name = serializers.CharField(required=True, max_length=50)
    job_title = serializers.CharField(required=True, max_length=100)
    experience_level = serializers.ChoiceField(
        required=True,
        choices=User.ExperienceLevel.choices,
    )
    
    
    
    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "job_title",
            "experience_level",
            "years_of_experience",
            "skills",
        )

    # ── Validations ────────────────────────────────

    def validate_first_name(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError(
                _("نام باید حداقل ۲ کاراکتر باشد")
            )
        return value

    def validate_last_name(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError(
                _("نام خانوادگی باید حداقل ۲ کاراکتر باشد")
            )
        return value

    def validate_years_of_experience(self, value: int) -> int:
        if value < 0 or value > 50:
            raise serializers.ValidationError(
                _("سال‌های تجربه باید بین ۰ تا ۵۰ باشد")
            )
        return value

    def validate_skills(self, value: list) -> list:
        cleaned = list({s.strip() for s in value if s.strip()})
        if not cleaned:
            raise serializers.ValidationError(
                _("حداقل یک مهارت الزامی است")
            )
        return sorted(cleaned)

    def validate(self, attrs: dict) -> dict:
        # اگه پروفایل قبلاً کامل شده، اجازه نده
        if self.instance and self.instance.is_profile_complete:
            raise serializers.ValidationError(
                _("پروفایل شما قبلاً تکمیل شده. از ویرایش پروفایل استفاده کنید")
            )
        return attrs

    def update(self, instance, validated_data: dict):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save(update_fields=list(validated_data.keys()))

        logger.info(
            "Profile completed | pk=%s | job=%s | level=%s",
            instance.pk,
            instance.job_title,
            instance.experience_level,
        )
        return instance


class AvatarSerializer(serializers.ModelSerializer):
    """
    PUT    /me/avatar/  →  آپلود یا جایگزینی
    DELETE /me/avatar/  →  حذف (در view هندل میشه)
    """

    MAX_SIZE_MB = 2
    ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"]

    avatar = serializers.ImageField(
        label=_("تصویر پروفایل"),
    )

    class Meta:
        model = User
        fields = ("avatar",)

    def validate_avatar(self, image):
        max_bytes = self.MAX_SIZE_MB * 1024 * 1024
        if image.size > max_bytes:
            raise serializers.ValidationError(
                _(f"حجم تصویر نباید بیشتر از {self.MAX_SIZE_MB} مگابایت باشد")
            )

        if image.content_type not in self.ALLOWED_TYPES:
            raise serializers.ValidationError(
                _("فرمت تصویر باید JPEG، PNG یا WebP باشد")
            )

        # چک ابعاد تصویر
        from PIL import Image as PILImage

        try:
            img = PILImage.open(image)
            width, height = img.size
            if width > 2000 or height > 2000:
                raise serializers.ValidationError(
                    _("ابعاد تصویر نباید بیشتر از 2000x2000 پیکسل باشد")
                )
            if width < 100 or height < 100:
                raise serializers.ValidationError(
                    _("ابعاد تصویر نباید کمتر از 100x100 پیکسل باشد")
                )
        except Exception as exc:
            if "ابعاد" in str(exc):
                raise
            raise serializers.ValidationError(
                _("فایل آپلود شده یک تصویر معتبر نیست")
            )

        # برگردوندن pointer به ابتدا
        image.seek(0)
        return image

    def update(self, instance, validated_data: dict):
        # حذف آواتار قبلی
        if instance.avatar:
            storage = instance.avatar.storage
            if storage.exists(instance.avatar.name):
                storage.delete(instance.avatar.name)

        instance.avatar = validated_data["avatar"]
        instance.save(update_fields=["avatar"])

        logger.info("Avatar updated | pk=%s", instance.pk)
        return instance


class DeleteAccountSerializer(serializers.Serializer):
    """
    DELETE /me/

    Soft delete: کاربر غیرفعال میشه + شماره‌تلفن ماسک میشه.

    Request:
        {"code": "123456"}
    """

    code = serializers.CharField(
        max_length=6,
        min_length=6,
        validators=[otp_code_validator],
        label=_("کد تایید"),
        help_text=_("ابتدا از send-otp با purpose=reset کد بگیرید"),
    )

    def validate(self, attrs: dict) -> dict:
        user = self.context["request"].user
        from .services import OTPService
        
        result = OTPService.verify_otp_for_action(
            user=user,
            code=attrs["code"],
            purpose=OTPCode.Purpose.RESET,
        )
        if not result["success"]:
            raise serializers.ValidationError({"code": result["message"]})


        return attrs

    def save(self) -> None:
        user = self.context["request"].user

        # ── Soft Delete ─────────────────────────────
        user.is_active = False
        user.is_phone_verified = False

        # ماسک کردن شماره برای آزاد شدن شماره
        user.phone_number = f"deleted_{user.pk}_{user.phone_number}"

        if user.email:
            user.email = f"deleted_{user.pk}_{user.email}"

        # پاک کردن اطلاعات حساس
        user.first_name = ""
        user.last_name = ""
        user.bio = ""
        user.skills = []
        user.set_unusable_password()

        # حذف آواتار
        if user.avatar:
            storage = user.avatar.storage
            if storage.exists(user.avatar.name):
                storage.delete(user.avatar.name)
            user.avatar = None

        user.save()

        logger.warning("Account soft-deleted | pk=%s", user.pk)


# ═══════════════════════════════════════════════════════════════════
#                      ADMIN SERIALIZERS
# ═══════════════════════════════════════════════════════════════════


class AdminUserListSerializer(AvatarURLMixin, serializers.ModelSerializer):
    """
    GET /admin/users/
    لیست خلاصه با فیلتر و جستجو.
    """

    full_name = serializers.CharField(read_only=True)
    is_profile_complete = serializers.BooleanField(read_only=True)
    avatar_url = serializers.SerializerMethodField()
    otp_count = serializers.SerializerMethodField()
    interview_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "phone_number",
            "email",
            "full_name",
            "avatar_url",
            "job_title",
            "experience_level",
            "is_active",
            "is_staff",
            "is_phone_verified",
            "is_profile_complete",
            "otp_count",
            "interview_count",
            "date_joined",
            "last_login",
        )
        read_only_fields = fields

    def get_otp_count(self, obj) -> int:
        if hasattr(obj, "_otp_count"):
            return obj._otp_count
        return obj.otp_codes.count()

    def get_interview_count(self, obj) -> int:
        if hasattr(obj, "_interview_count"):
            return obj._interview_count
        return getattr(
            obj, "interview_sessions", obj.__class__.objects.none()
        ).count()


class AdminUserDetailSerializer(AvatarURLMixin, serializers.ModelSerializer):
    """
    GET   /admin/users/<id>/   →  جزئیات کامل
    PATCH /admin/users/<id>/   →  ویرایش توسط ادمین
    """

    full_name = serializers.CharField(read_only=True)
    is_profile_complete = serializers.BooleanField(read_only=True)
    avatar_url = serializers.SerializerMethodField()
    otp_summary = serializers.SerializerMethodField()
    interview_summary = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "phone_number",
            "email",
            "full_name",
            "first_name",
            "last_name",
            "avatar_url",
            "bio",
            "job_title",
            "experience_level",
            "years_of_experience",
            "skills",
            "is_active",
            "is_staff",
            "is_superuser",
            "is_phone_verified",
            "is_profile_complete",
            "last_login_ip",
            "date_joined",
            "last_login",
            "otp_summary",
            "interview_summary",
        )
        read_only_fields = (
            "id",
            "phone_number",
            "full_name",
            "avatar_url",
            "is_profile_complete",
            "last_login_ip",
            "date_joined",
            "last_login",
            "otp_summary",
            "interview_summary",
        )

    def validate(self, attrs: dict) -> dict:
        # ادمین نمیتونه خودش رو غیرفعال کنه
        request_user = self.context["request"].user
        if self.instance and self.instance.pk == request_user.pk:
            if "is_active" in attrs and not attrs["is_active"]:
                raise serializers.ValidationError(
                    {"is_active": _("نمیتوانید حساب خودتان را غیرفعال کنید")}
                )
            if "is_staff" in attrs and not attrs["is_staff"]:
                raise serializers.ValidationError(
                    {"is_staff": _("نمیتوانید دسترسی ادمین خودتان را بردارید")}
                )
        return attrs

    def get_otp_summary(self, obj) -> dict:
        otps = obj.otp_codes.all()
        total = otps.count()
        last_24h = otps.filter(
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
        return {
            "total": total,
            "last_24h": last_24h,
        }

    def get_interview_summary(self, obj) -> dict:
        sessions = getattr(
            obj, "interview_sessions", obj.__class__.objects.none()
        )
        if hasattr(sessions, "count"):
            total = sessions.count()
        else:
            total = 0
        return {
            "total": total,
        }


class AdminSoftDeleteSerializer(serializers.Serializer):
    """
    DELETE /admin/users/<id>/
    Soft delete توسط ادمین — بدون نیاز به OTP.
    """

    reason = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        label=_("دلیل حذف"),
    )

    def validate(self, attrs: dict) -> dict:
        user = self.context["user_to_delete"]

        if user.is_superuser:
            raise serializers.ValidationError(
                _("حساب سوپریوزر قابل حذف نیست")
            )

        request_user = self.context["request"].user
        if user.pk == request_user.pk:
            raise serializers.ValidationError(
                _("نمیتوانید حساب خودتان را حذف کنید")
            )

        return attrs

    def save(self) -> None:
        user = self.context["user_to_delete"]
        reason = self.validated_data.get("reason", "")

        user.is_active = False
        user.phone_number = f"deleted_{user.pk}_{user.phone_number}"
        if user.email:
            user.email = f"deleted_{user.pk}_{user.email}"
        user.set_unusable_password()
        user.save()

        logger.warning(
            "Admin soft-deleted user | pk=%s | by=%s | reason=%s",
            user.pk,
            self.context["request"].user.pk,
            reason,
        )


class AdminSuspendSerializer(serializers.Serializer):
    """
    POST /admin/users/<id>/suspend/
    """

    reason = serializers.CharField(
        max_length=500,
        label=_("دلیل تعلیق"),
    )
    duration_hours = serializers.IntegerField(
        min_value=1,
        max_value=8760,  # حداکثر ۱ سال
        default=24,
        label=_("مدت تعلیق (ساعت)"),
    )

    def validate(self, attrs: dict) -> dict:
        user = self.context["user_to_suspend"]

        if not user.is_active:
            raise serializers.ValidationError(
                _("کاربر از قبل غیرفعال است")
            )
        if user.is_superuser:
            raise serializers.ValidationError(
                _("سوپریوزر قابل تعلیق نیست")
            )
        if user.pk == self.context["request"].user.pk:
            raise serializers.ValidationError(
                _("نمیتوانید خودتان را تعلیق کنید")
            )

        return attrs

    def save(self) -> None:
        user = self.context["user_to_suspend"]
        reason = self.validated_data["reason"]
        duration = self.validated_data["duration_hours"]

        user.is_active = False
        user.save(update_fields=["is_active"])

        logger.warning(
            "User suspended | pk=%s | by=%s | hours=%d | reason=%s",
            user.pk,
            self.context["request"].user.pk,
            duration,
            reason,
        )

        # Task برای رفع تعلیق خودکار
        try:
            from apps.notifications.tasks import auto_unsuspend_user
            auto_unsuspend_user.apply_async(
                args=[user.pk],
                countdown=duration * 3600,
            )
        except Exception as exc:
            logger.error("Failed to schedule unsuspend: %s", exc)


class AdminUnsuspendSerializer(serializers.Serializer):
    """
    POST /admin/users/<id>/unsuspend/
    """

    reason = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        label=_("دلیل رفع تعلیق"),
    )

    def validate(self, attrs: dict) -> dict:
        user = self.context["user_to_unsuspend"]

        if user.is_active:
            raise serializers.ValidationError(
                _("کاربر در حال حاضر فعال است")
            )

        return attrs

    def save(self) -> None:
        user = self.context["user_to_unsuspend"]

        user.is_active = True
        user.save(update_fields=["is_active"])

        logger.info(
            "User unsuspended | pk=%s | by=%s",
            user.pk,
            self.context["request"].user.pk,
        )


class AdminBanSerializer(serializers.Serializer):
    """
    POST /admin/users/<id>/ban/
    بن دائمی: غیرفعال + set_unusable_password + ماسک شماره
    """

    reason = serializers.CharField(
        max_length=500,
        label=_("دلیل بن"),
    )

    def validate(self, attrs: dict) -> dict:
        user = self.context["user_to_ban"]

        if user.is_superuser:
            raise serializers.ValidationError(
                _("سوپریوزر قابل بن شدن نیست")
            )
        if user.pk == self.context["request"].user.pk:
            raise serializers.ValidationError(
                _("نمیتوانید خودتان را بن کنید")
            )
        # چک نکنه دوباره بن بشه
        if user.phone_number.startswith("banned_"):
            raise serializers.ValidationError(
                _("این کاربر قبلاً بن شده است")
            )

        return attrs

    def save(self) -> None:
        user = self.context["user_to_ban"]
        reason = self.validated_data["reason"]

        user.is_active = False
        user.is_phone_verified = False
        user.phone_number = f"banned_{user.pk}_{user.phone_number}"
        if user.email:
            user.email = f"banned_{user.pk}_{user.email}"
        user.set_unusable_password()
        user.save()

        logger.warning(
            "User BANNED | pk=%s | by=%s | reason=%s",
            user.pk,
            self.context["request"].user.pk,
            reason,
        )


# ═══════════════════════════════════════════════════════════════════
#                      OTP HISTORY SERIALIZER
# ═══════════════════════════════════════════════════════════════════


class OTPHistorySerializer(serializers.ModelSerializer):
    """
    GET /admin/otp-history/<user_id>/
    """

    status = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)

    class Meta:
        model = OTPCode
        fields = (
            "id",
            "phone_number",
            "code",
            "purpose",
            "status",
            "failed_attempts",
            "remaining_seconds",
            "ip_address",
            "created_at",
            "used_at",
        )
        read_only_fields = fields

    def get_status(self, obj) -> str:
        if obj.is_used:
            return "used"
        if obj.is_expired:
            return "expired"
        if obj.is_max_attempts_reached:
            return "blocked"
        return "active"

    def get_remaining_seconds(self, obj) -> int:
        if not obj.is_valid:
            return 0
        return obj.remaining_seconds


# ═══════════════════════════════════════════════════════════════════
#                        STATS SERIALIZER
# ═══════════════════════════════════════════════════════════════════

# moved it to state selector for better performance and separation of concerns
class AdminStatsSerializer(serializers.Serializer):
    """
    GET /admin/stats/

    Response:
        {
            "total_users": 1500,
            "active_users": 1200,
            "verified_users": 1100,
            "complete_profiles": 900,
            "new_today": 25,
            "new_this_week": 150,
            "new_this_month": 500,
            "experience_breakdown": {...},
            "otp_stats": {...}
        }
    """

    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    inactive_users = serializers.IntegerField()
    verified_users = serializers.IntegerField()
    complete_profiles = serializers.IntegerField()
    staff_users = serializers.IntegerField()
    banned_users = serializers.IntegerField()

    new_today = serializers.IntegerField()
    new_this_week = serializers.IntegerField()
    new_this_month = serializers.IntegerField()

    experience_breakdown = serializers.DictField()
    otp_stats = serializers.DictField()

    @classmethod
    def generate_stats(cls) -> dict:
        """جمع‌آوری همه آمار در یک کوئری بهینه."""

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=now.weekday())
        month_start = today_start.replace(day=1)

        # ── User Counts (یک کوئری) ──────────────
        user_aggregation = User.objects.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(is_active=True)),
            inactive=Count("id", filter=Q(is_active=False)),
            verified=Count("id", filter=Q(is_phone_verified=True)),
            staff=Count("id", filter=Q(is_staff=True)),
            banned=Count("id", filter=Q(phone_number__startswith="banned_")),
            new_today=Count("id", filter=Q(date_joined__gte=today_start)),
            new_week=Count("id", filter=Q(date_joined__gte=week_start)),
            new_month=Count("id", filter=Q(date_joined__gte=month_start)),
            # پروفایل‌های کامل
            complete=Count(
                "id",
                filter=Q(
                    first_name__gt="",
                    last_name__gt="",
                    job_title__gt="",
                    experience_level__gt="",
                ),
            ),
        )

        # ── Experience Breakdown ────────────────
        exp_breakdown = {}
        for choice_value, choice_label in User.ExperienceLevel.choices:
            exp_breakdown[choice_value] = User.objects.filter(
                experience_level=choice_value,
                is_active=True,
            ).count()
        exp_breakdown["not_set"] = User.objects.filter(
            experience_level="",
            is_active=True,
        ).count()

        # ── OTP Stats (یک کوئری) ────────────────
        otp_aggregation = OTPCode.objects.aggregate(
            total=Count("id"),
            used=Count("id", filter=Q(is_used=True)),
            today=Count("id", filter=Q(created_at__gte=today_start)),
            today_used=Count(
                "id",
                filter=Q(created_at__gte=today_start, is_used=True),
            ),
        )

        total_otp = otp_aggregation["total"] or 1
        used_otp = otp_aggregation["used"] or 0

        otp_stats = {
            "total_sent": otp_aggregation["total"],
            "total_used": used_otp,
            "success_rate": round((used_otp / total_otp) * 100, 1),
            "today_sent": otp_aggregation["today"],
            "today_used": otp_aggregation["today_used"],
        }

        return {
            "total_users": user_aggregation["total"],
            "active_users": user_aggregation["active"],
            "inactive_users": user_aggregation["inactive"],
            "verified_users": user_aggregation["verified"],
            "complete_profiles": user_aggregation["complete"],
            "staff_users": user_aggregation["staff"],
            "banned_users": user_aggregation["banned"],
            "new_today": user_aggregation["new_today"],
            "new_this_week": user_aggregation["new_week"],
            "new_this_month": user_aggregation["new_month"],
            "experience_breakdown": exp_breakdown,
            "otp_stats": otp_stats,
        }

class LoginWithPasswordSerializer(PhoneNormalizerMixin, serializers.Serializer):
    """اعتبارسنجی ورود کاربران با شماره موبایل و رمز عبور"""
    phone_number = serializers.CharField(validators=[phone_validator])
    password = serializers.CharField(
        write_only=True, 
        style={'input_type': 'password'},
        label=_("رمز عبور")
    )

    def validate(self, attrs):
        # نرمال‌سازی شماره تلفن با استفاده از میکسین خودتان
        phone_number = self.validate_phone_number(attrs.get('phone_number'))
        password = attrs.get('password')

        if phone_number and password:
            # جنگو در پشت صحنه از فیلد UNIQUE شما (phone_number) برای authenticate استفاده میکنه
            user = authenticate(
                request=self.context.get('request'),
                username=phone_number,
                password=password
            )

            if not user:
                raise serializers.ValidationError(_("شماره موبایل یا رمز عبور اشتباه است"))
            
            if not user.is_active:
                raise serializers.ValidationError(_("حساب کاربری شما غیرفعال شده است"))
                
            if getattr(user, 'is_banned', False):
                raise serializers.ValidationError(_("حساب کاربری شما مسدود شده است"))
        else:
            raise serializers.ValidationError(_("ارسال شماره موبایل و رمز عبور الزامی است"))

        attrs['user'] = user
        return attrs



class SetPasswordSerializer(serializers.Serializer):
    """سریالایزر برای تعیین یا تغییر رمز عبور کاربر احراز هویت شده"""
    current_password = serializers.CharField(
        style={'input_type': 'password'}, 
        required=False, 
        allow_blank=True,
        label=_("رمز عبور فعلی")
    )
    new_password = serializers.CharField(
        write_only=True, 
        style={'input_type': 'password'},
        validators=[validate_password], # استفاده از ولیدیتورهای نیتیو جنگو
        label=_("رمز عبور جدید")
    )
    confirm_password = serializers.CharField(
        write_only=True, 
        style={'input_type': 'password'},
        label=_("تکرار رمز عبور جدید")
    )

    def validate(self, attrs):
        user = self.context['request'].user
        current_password = attrs.get('current_password')
        new_password = attrs.get('new_password')
        confirm_password = attrs.get('confirm_password')

        # ۱. بررسی تطابق رمز عبور جدید و تکرار آن
        if new_password != confirm_password:
            raise serializers.ValidationError({
                "confirm_password": _("رمز عبور جدید و تکرار آن مطابقت ندارند")
            })

        # ۲. اگر کاربر از قبل رمز عبور دارد، وارد کردن رمز عبور فعلی الزامی است
        if user.has_usable_password():
            if not current_password:
                raise serializers.ValidationError({
                    "current_password": _("برای تغییر رمز عبور، وارد کردن رمز عبور فعلی الزامی است")
                })
            if not user.check_password(current_password):
                raise serializers.ValidationError({
                    "current_password": _("رمز عبور فعلی اشتباه است")
                })
        
        return attrs