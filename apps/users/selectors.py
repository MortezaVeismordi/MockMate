import logging
from datetime import timedelta
from typing import Optional

from django.contrib.auth import get_user_model
from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Count,
    F,
    Q,
    QuerySet,
    Value,
    When,
)
from django.db.models.functions import Concat
from django.utils import timezone

from .models import OTPCode

logger = logging.getLogger(__name__)
User = get_user_model()


# ═══════════════════════════════════════════════════════════════
#                     USER SELECTORS
# ═══════════════════════════════════════════════════════════════


class UserSelector:
    """
    تمام کوئری‌های مربوط به User.
    هیچ write operation ای انجام نمیده.
    """

    # ──────────────────────────────────────────
    #  Single User Queries
    # ──────────────────────────────────────────

    @staticmethod
    def get_by_id(user_id: int) -> Optional[User]:
        """دریافت کاربر با ID."""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    @staticmethod
    def get_by_phone(phone_number: str) -> Optional[User]:
        """دریافت کاربر با شماره تلفن."""
        try:
            return User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return None

    @staticmethod
    def get_by_email(email: str) -> Optional[User]:
        """دریافت کاربر با ایمیل."""
        try:
            return User.objects.get(email=email.lower())
        except User.DoesNotExist:
            return None

    @staticmethod
    def get_by_id_with_relations(user_id: int) -> Optional[User]:
        """
        دریافت کاربر با ID به همراه تمام رابطه‌ها.
        مناسب برای Admin Detail View.
        """
        try:
            return User.objects.prefetch_related("otp_codes", "groups", "user_permissions").get(pk=user_id)
        except User.DoesNotExist:
            return None

    # ──────────────────────────────────────────
    #  Existence Checks
    # ──────────────────────────────────────────

    @staticmethod
    def phone_exists(phone_number: str) -> bool:
        """آیا این شماره تلفن قبلاً ثبت شده؟"""
        return User.objects.filter(phone_number=phone_number).exists()

    @staticmethod
    def email_exists(email: str, exclude_user_id: int = None) -> bool:
        """آیا این ایمیل قبلاً ثبت شده؟"""
        qs = User.objects.filter(email=email.lower())
        if exclude_user_id:
            qs = qs.exclude(pk=exclude_user_id)
        return qs.exists()

    @staticmethod
    def is_active(user_id: int) -> bool:
        """آیا کاربر فعال است؟"""
        return User.objects.filter(pk=user_id, is_active=True).exists()

    @staticmethod
    def is_banned(phone_number: str) -> bool:
        return User.objects.filter(
            phone_number=phone_number,
            is_banned=True,
        ).exists()

    @staticmethod
    def get_banned_users() -> QuerySet:
        return User.objects.filter(is_banned=True).order_by("-date_joined")

    @staticmethod
    def is_profile_complete(user_id: int) -> bool:
        """آیا پروفایل کاربر کامله؟"""
        return User.objects.filter(
            pk=user_id,
            first_name__gt="",
            last_name__gt="",
            job_title__gt="",
            experience_level__gt="",
        ).exists()

    # ──────────────────────────────────────────
    #  List Queries (Admin)
    # ──────────────────────────────────────────

    @staticmethod
    def get_all_users() -> QuerySet:
        """
        لیست همه کاربران با annotate های لازم.
        مناسب برای Admin List View.
        """
        return (
            User.objects.annotate(
                _otp_count=Count("otp_codes"),
                _full_name=Case(
                    When(
                        Q(first_name__gt="") & Q(last_name__gt=""),
                        then=Concat(
                            F("first_name"),
                            Value(" "),
                            F("last_name"),
                            output_field=CharField(),
                        ),
                    ),
                    default=F("phone_number"),
                    output_field=CharField(),
                ),
                _is_profile_complete=Case(
                    When(
                        Q(first_name__gt="") & Q(last_name__gt="") & Q(job_title__gt="") & Q(experience_level__gt=""),
                        then=Value(True),
                    ),
                    default=Value(False),
                    output_field=BooleanField(),
                ),
            )
            .only(
                "id",
                "phone_number",
                "email",
                "first_name",
                "last_name",
                "avatar",
                "job_title",
                "experience_level",
                "is_active",
                "is_staff",
                "is_phone_verified",
                "date_joined",
                "last_login",
            )
            .order_by("-date_joined")
        )

    @staticmethod
    def get_active_users() -> QuerySet:
        """کاربران فعال."""
        return UserSelector.get_all_users().filter(is_active=True)

    @staticmethod
    def get_inactive_users() -> QuerySet:
        """کاربران غیرفعال."""
        return UserSelector.get_all_users().filter(is_active=False)

    @staticmethod
    def get_verified_users() -> QuerySet:
        """کاربرانی که شماره‌شون تایید شده."""
        return UserSelector.get_all_users().filter(is_phone_verified=True)

    @staticmethod
    def get_users_with_complete_profile() -> QuerySet:
        """کاربرانی که پروفایل‌شون کامله."""
        return UserSelector.get_all_users().filter(_is_profile_complete=True)

    @staticmethod
    def get_users_with_incomplete_profile() -> QuerySet:
        """کاربرانی که پروفایل‌شون ناقصه."""
        return UserSelector.get_all_users().filter(_is_profile_complete=False, is_active=True)

    # ──────────────────────────────────────────
    #  Filtered Queries
    # ──────────────────────────────────────────

    @staticmethod
    def get_users_by_experience(level: str) -> QuerySet:
        """فیلتر بر اساس سطح تجربه."""
        return UserSelector.get_active_users().filter(experience_level=level)

    @staticmethod
    def get_users_by_skill(skill: str) -> QuerySet:
        """
        کاربرانی که یک مهارت خاص دارن.
        skills فیلد JSONField هست.
        """
        return UserSelector.get_active_users().filter(skills__contains=[skill])

    @staticmethod
    def search_users(query: str) -> QuerySet:
        """جستجو در نام، شماره، ایمیل و عنوان شغلی."""
        if not query or len(query) < 2:
            return User.objects.none()

        return UserSelector.get_all_users().filter(
            Q(phone_number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(job_title__icontains=query)
        )

    # ──────────────────────────────────────────
    #  Time-based Queries
    # ──────────────────────────────────────────

    @staticmethod
    def get_new_users_since(since: timezone) -> QuerySet:
        """کاربران ثبت‌نام‌شده از یک تاریخ مشخص."""
        return UserSelector.get_all_users().filter(date_joined__gte=since)

    @staticmethod
    def get_new_users_today() -> QuerySet:
        """کاربران ثبت‌نام‌شده امروز."""
        today = timezone.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return UserSelector.get_new_users_since(today)

    @staticmethod
    def get_new_users_this_week() -> QuerySet:
        """کاربران ثبت‌نام‌شده این هفته."""
        now = timezone.now()
        week_start = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ) - timedelta(days=now.weekday())
        return UserSelector.get_new_users_since(week_start)

    @staticmethod
    def get_new_users_this_month() -> QuerySet:
        """کاربران ثبت‌نام‌شده این ماه."""
        month_start = timezone.now().replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return UserSelector.get_new_users_since(month_start)

    @staticmethod
    def get_inactive_since(days: int) -> QuerySet:
        """
        کاربرانی که مدت مشخصی لاگین نکردن.
        مناسب برای ارسال نوتیفیکیشن بازگشت.
        """
        threshold = timezone.now() - timedelta(days=days)
        return UserSelector.get_active_users().filter(Q(last_login__lt=threshold) | Q(last_login__isnull=True))

    @staticmethod
    def get_recently_active(hours: int = 24) -> QuerySet:
        """کاربرانی که اخیراً فعال بودن."""
        since = timezone.now() - timedelta(hours=hours)
        return UserSelector.get_active_users().filter(last_login__gte=since)


# ═══════════════════════════════════════════════════════════════
#                      OTP SELECTORS
# ═══════════════════════════════════════════════════════════════


class OTPSelector:
    """
    تمام کوئری‌های مربوط به OTPCode.
    فقط SELECT — بدون تغییر در دیتابیس.
    """

    # ──────────────────────────────────────────
    #  Single OTP Queries
    # ──────────────────────────────────────────

    @staticmethod
    def get_latest_active_otp(
        user,
        purpose: str = OTPCode.Purpose.LOGIN,
    ) -> Optional[OTPCode]:
        """آخرین OTP فعال (استفاده‌نشده و منقضی‌نشده)."""
        try:
            otp = OTPCode.objects.filter(
                user=user,
                purpose=purpose,
                is_used=False,
            ).latest("created_at")
            if otp.is_valid:
                return otp
            return None
        except OTPCode.DoesNotExist:
            return None

    @staticmethod
    def get_latest_otp(
        user,
        purpose: str = OTPCode.Purpose.LOGIN,
    ) -> Optional[OTPCode]:
        """آخرین OTP (فعال یا غیرفعال)."""
        try:
            return OTPCode.objects.filter(user=user, purpose=purpose).latest("created_at")
        except OTPCode.DoesNotExist:
            return None

    # ──────────────────────────────────────────
    #  OTP Status Checks
    # ──────────────────────────────────────────

    @staticmethod
    def has_active_otp(
        user,
        purpose: str = OTPCode.Purpose.LOGIN,
    ) -> bool:
        """آیا کاربر OTP فعال داره؟"""
        return OTPSelector.get_latest_active_otp(user, purpose) is not None

    @staticmethod
    def get_remaining_seconds(
        user,
        purpose: str = OTPCode.Purpose.LOGIN,
    ) -> int:
        """ثانیه‌های باقی‌مانده از آخرین OTP فعال."""
        otp = OTPSelector.get_latest_active_otp(user, purpose)
        if otp:
            return otp.remaining_seconds
        return 0

    @staticmethod
    def can_resend(
        user,
        purpose: str = OTPCode.Purpose.LOGIN,
        min_interval_seconds: int = 60,
    ) -> tuple[bool, int]:
        """
        آیا مجاز به ارسال مجدد هست؟
        Returns: (can_resend, wait_seconds)
        """
        latest = OTPSelector.get_latest_otp(user, purpose)
        if not latest:
            return True, 0

        elapsed = (timezone.now() - latest.created_at).total_seconds()
        if elapsed < min_interval_seconds:
            wait = int(min_interval_seconds - elapsed)
            return False, wait

        return True, 0

    @staticmethod
    def get_daily_count(user) -> int:
        """تعداد OTP ارسال‌شده در ۲۴ ساعت اخیر."""
        since = timezone.now() - timedelta(hours=24)
        return OTPCode.objects.filter(
            user=user,
            created_at__gte=since,
        ).count()

    @staticmethod
    def get_daily_remaining(user) -> int:
        """تعداد باقی‌مانده ارسال OTP امروز."""
        count = OTPSelector.get_daily_count(user)
        return max(0, OTPCode.MAX_RESEND_PER_DAY - count)

    @staticmethod
    def is_daily_limit_reached(user) -> bool:
        """آیا سقف روزانه رسیده؟"""
        return OTPSelector.get_daily_remaining(user) <= 0

    # ──────────────────────────────────────────
    #  OTP History (Admin)
    # ──────────────────────────────────────────

    @staticmethod
    def get_user_otp_history(
        user_id: int,
        limit: int = None,
    ) -> QuerySet:
        """تاریخچه OTP یک کاربر."""
        qs = OTPCode.objects.filter(user_id=user_id).select_related("user").order_by("-created_at")
        if limit:
            qs = qs[:limit]
        return qs

    @staticmethod
    def get_recent_otp_history(
        user_id: int,
        count: int = 5,
    ) -> QuerySet:
        """آخرین N تا OTP یک کاربر."""
        return OTPSelector.get_user_otp_history(user_id, limit=count)

    @staticmethod
    def get_all_otps() -> QuerySet:
        """همه OTPها — برای ادمین."""
        return OTPCode.objects.select_related("user").order_by("-created_at")

    @staticmethod
    def get_failed_otps(hours: int = 24) -> QuerySet:
        """OTPهایی که تلاش ناموفق داشتن (مشکوک به brute force)."""
        since = timezone.now() - timedelta(hours=hours)
        return (
            OTPCode.objects.filter(
                created_at__gte=since,
                failed_attempts__gt=0,
            )
            .select_related("user")
            .order_by("-failed_attempts")
        )

    @staticmethod
    def get_suspicious_ips(
        threshold: int = 10,
        hours: int = 24,
    ) -> QuerySet:
        """
        IPهایی که بیش از حد مشخصی OTP درخواست کردن.
        مناسب برای تشخیص abuse.
        """
        since = timezone.now() - timedelta(hours=hours)
        return (
            OTPCode.objects.filter(
                created_at__gte=since,
                ip_address__isnull=False,
            )
            .values("ip_address")
            .annotate(count=Count("id"))
            .filter(count__gte=threshold)
            .order_by("-count")
        )


# ═══════════════════════════════════════════════════════════════
#                    STATS SELECTORS
# ═══════════════════════════════════════════════════════════════


class StatsSelector:
    """
    کوئری‌های آماری — بهینه‌شده با aggregate.
    """

    @staticmethod
    def get_user_counts() -> dict:
        """آمار تعداد کاربران در یک کوئری."""
        now = timezone.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today - timedelta(days=now.weekday())
        month_start = today.replace(day=1)

        return User.objects.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(is_active=True)),
            inactive=Count("id", filter=Q(is_active=False)),
            verified=Count("id", filter=Q(is_phone_verified=True)),
            staff=Count("id", filter=Q(is_staff=True)),
            banned=Count(
                "id",
                filter=Q(is_banned=True),
            ),
            complete_profile=Count(
                "id",
                filter=Q(
                    first_name__gt="",
                    last_name__gt="",
                    job_title__gt="",
                    experience_level__gt="",
                ),
            ),
            new_today=Count(
                "id",
                filter=Q(date_joined__gte=today),
            ),
            new_this_week=Count(
                "id",
                filter=Q(date_joined__gte=week_start),
            ),
            new_this_month=Count(
                "id",
                filter=Q(date_joined__gte=month_start),
            ),
        )

    @staticmethod
    def get_experience_breakdown() -> dict:
        """توزیع سطح تجربه کاربران فعال."""
        breakdown = {}
        for value, label in User.ExperienceLevel.choices:
            breakdown[value] = User.objects.filter(
                experience_level=value,
                is_active=True,
            ).count()

        breakdown["not_set"] = User.objects.filter(
            experience_level="",
            is_active=True,
        ).count()

        return breakdown

    @staticmethod
    def get_otp_stats() -> dict:
        """آمار OTP در یک کوئری."""
        today = timezone.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        agg = OTPCode.objects.aggregate(
            total=Count("id"),
            used=Count("id", filter=Q(is_used=True)),
            today_sent=Count("id", filter=Q(created_at__gte=today)),
            today_used=Count(
                "id",
                filter=Q(created_at__gte=today, is_used=True),
            ),
            total_failed=Count(
                "id",
                filter=Q(failed_attempts__gt=0),
            ),
        )

        total = agg["total"] or 1
        used = agg["used"] or 0

        return {
            "total_sent": agg["total"],
            "total_used": used,
            "success_rate": round((used / total) * 100, 1),
            "today_sent": agg["today_sent"],
            "today_used": agg["today_used"],
            "total_failed_attempts": agg["total_failed"],
        }

    @staticmethod
    def get_full_stats() -> dict:
        """همه آمارها یکجا."""
        user_counts = StatsSelector.get_user_counts()

        return {
            "total_users": user_counts["total"],
            "active_users": user_counts["active"],
            "inactive_users": user_counts["inactive"],
            "verified_users": user_counts["verified"],
            "complete_profiles": user_counts["complete_profile"],
            "staff_users": user_counts["staff"],
            "banned_users": user_counts["banned"],
            "new_today": user_counts["new_today"],
            "new_this_week": user_counts["new_this_week"],
            "new_this_month": user_counts["new_this_month"],
            "experience_breakdown": StatsSelector.get_experience_breakdown(),
            "otp_stats": StatsSelector.get_otp_stats(),
        }
