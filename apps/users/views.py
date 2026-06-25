import logging

from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.views import APIView
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.throttling import AnonRateThrottle
from rest_framework.parsers import MultiPartParser, FormParser

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_simplejwt.tokens import RefreshToken
from .response import APIResponse
from .services import OTPService
from .models import OTPCode
from .serializers import (
    # Auth
    SendOTPSerializer,
    ResendOTPSerializer,
    VerifyOTPSerializer,
    RefreshTokenSerializer,
    LogoutSerializer,
    LoginWithPasswordSerializer,
    SetPasswordSerializer,
    # Profile
    UserMeSerializer,
    CompleteProfileSerializer,
    AvatarSerializer,
    DeleteAccountSerializer,
    # Admin
    AdminUserListSerializer,
    AdminUserDetailSerializer,
    AdminSoftDeleteSerializer,
    AdminSuspendSerializer,
    AdminUnsuspendSerializer,
    AdminBanSerializer,
    OTPHistorySerializer,
    AdminStatsSerializer,
)
from .selectors import UserSelector, StatsSelector


logger = logging.getLogger(__name__)
User = get_user_model()


# ═══════════════════════════════════════════════════════════════
#  Throttles
# ═══════════════════════════════════════════════════════════════

class OTPSendThrottle(AnonRateThrottle):
    rate = "5/min"


class OTPVerifyThrottle(AnonRateThrottle):
    rate = "10/min"


class AuthThrottle(AnonRateThrottle):
    rate = "20/min"


# ═══════════════════════════════════════════════════════════════
#  Mixins
# ═══════════════════════════════════════════════════════════════

class GetClientIPMixin:
    """استخراج IP واقعی کاربر (پشتیبانی از Reverse Proxy)."""

    def get_client_ip(self) -> str:
        x_forwarded = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR", "")


class GetUserOrNotFoundMixin:
    """
    پیدا کردن کاربر از pk.
    اگه نبود APIResponse.not_found برمیگردونه.
    """

    def get_user_or_404(self, pk: int):
        try:
            return User.objects.prefetch_related("otp_codes").get(pk=pk)
        except User.DoesNotExist:
            return None

    def get_user_response_or_404(self, pk: int):
        """
        Returns: (user, None) یا (None, Response)
        """
        user = self.get_user_or_404(pk)
        if user is None:
            return None, APIResponse.not_found(message=_("کاربر یافت نشد"))
        return user, None


# ═══════════════════════════════════════════════════════════════
#                       AUTH VIEWS
# ═══════════════════════════════════════════════════════════════


class SendOTPView(GetClientIPMixin, GenericAPIView):
    """
    POST /api/v1/users/auth/send-otp/

    ── Request ──────────────────────────────
    {
        "phone_number": "09123456789",
        "purpose": "login"
    }

    ── Response 200 ─────────────────────────
    {
        "success": true,
        "message": "کد OTP ارسال شد",
        "data": {
            "is_new_user": true,
            "remaining_seconds": 120
        }
    }
    """

    serializer_class = SendOTPSerializer
    permission_classes = [AllowAny]
    throttle_classes = [OTPSendThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data["phone_number"]
        purpose = serializer.validated_data["purpose"]
        ip = self.get_client_ip()

        result = OTPService.send_otp(
            phone_number=phone,
            purpose=purpose,
            ip_address=ip,
        )

        if not result["success"]:
            return APIResponse.error(message=result["message"])

        logger.info(
            "OTP sent | phone=%s | purpose=%s | ip=%s",
            phone, purpose, ip,
        )

        return APIResponse.success(
            message=str(result["message"]),
            data={
                "is_new_user": result.get("is_new_user", False),
                "remaining_seconds": result.get("remaining_seconds", 120),
            },
        )


class ResendOTPView(GetClientIPMixin, GenericAPIView):
    """
    POST /api/v1/users/auth/resend-otp/

    ── Request ──────────────────────────────
    {
        "phone_number": "09123456789",
        "purpose": "login"
    }

    ── Response 200 ─────────────────────────
    {
        "success": true,
        "message": "کد OTP مجدداً ارسال شد",
        "data": {
            "remaining_seconds": 120,
            "daily_remaining": 3
        }
    }
    """

    serializer_class = ResendOTPSerializer
    permission_classes = [AllowAny]
    throttle_classes = [OTPSendThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data["phone_number"]
        purpose = serializer.validated_data["purpose"]
        ip = self.get_client_ip()

        result = OTPService.send_otp(
            phone_number=phone,
            purpose=purpose,
            ip_address=ip,
        )

        if not result["success"]:
            return APIResponse.error(message=result["message"])

        logger.info("OTP resent | phone=%s | ip=%s", phone, ip)

        return APIResponse.success(
            message=_("کد OTP مجدداً ارسال شد"),
            data={
                "remaining_seconds": result.get("remaining_seconds", 120),
                "daily_remaining": serializer.validated_data.get(
                    "_daily_remaining"
                ),
            },
        )


class VerifyOTPView(GetClientIPMixin, GenericAPIView):
    """
    POST /api/v1/users/auth/verify-otp/

    ── Request ──────────────────────────────
    {
        "phone_number": "09123456789",
        "code": "123456",
        "purpose": "login"
    }

    ── Response 200 ─────────────────────────
    {
        "success": true,
        "message": "ورود موفقیت‌آمیز بود",
        "data": {
            "tokens": {
                "access": "eyJ...",
                "refresh": "eyJ..."
            },
            "user": { ... },
            "is_new_user": false,
            "is_profile_complete": true
        }
    }
    """

    serializer_class = VerifyOTPSerializer
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer._verified_user
        ip = self.get_client_ip()

        # ── ثبت IP آخرین ورود ─────────────────
        user.last_login_ip = ip
        user.save(update_fields=["last_login_ip"])

        logger.info(
            "OTP verified | phone=%s | pk=%s | ip=%s",
            user.phone_number, user.pk, ip,
        )

        return APIResponse.success(
            message=_("ورود موفقیت‌آمیز بود"),
            data=serializer.to_representation(serializer.validated_data),
        )


class RefreshTokenView(GenericAPIView):
    """
    POST /api/v1/users/auth/refresh-token/

    ── Request ──────────────────────────────
    {"refresh": "eyJ..."}

    ── Response 200 ─────────────────────────
    {
        "success": true,
        "message": "توکن با موفقیت تمدید شد",
        "data": {
            "access": "eyJ...",
            "refresh": "eyJ..."
        }
    }
    """

    serializer_class = RefreshTokenSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return APIResponse.success(
            message=_("توکن با موفقیت تمدید شد"),
            data=serializer.to_representation(serializer.validated_data),
        )


class LogoutView(GenericAPIView):
    """
    POST /api/v1/users/auth/logout/

    ── Request ──────────────────────────────
    {"refresh_token": "eyJ..."}

    ── Response 204 ─────────────────────────
    {
        "success": true,
        "message": "با موفقیت خارج شدید"
    }
    """

    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        logger.info(
            "User logged out | pk=%s | phone=%s",
            request.user.pk,
            request.user.phone_number,
        )

        return APIResponse.no_content(message=_("با موفقیت خارج شدید"))


# ═══════════════════════════════════════════════════════════════
#                      PROFILE VIEWS
# ═══════════════════════════════════════════════════════════════


class UserMeView(APIView):
    """
    GET   /api/v1/users/me/   →  دریافت پروفایل کامل
    PATCH /api/v1/users/me/   →  ویرایش partial پروفایل

    ── GET Response 200 ─────────────────────
    {
        "success": true,
        "message": "پروفایل کاربر",
        "data": {
            "id": 1,
            "phone_number": "09123456789",
            "full_name": "علی رضایی",
            ...
        }
    }

    ── PATCH Request ────────────────────────
    {"first_name": "علی", "job_title": "Senior Backend Developer"}

    ── PATCH Response 200 ───────────────────
    {
        "success": true,
        "message": "پروفایل با موفقیت بروزرسانی شد",
        "data": { ... }
    }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserMeSerializer(
            request.user,
            context={"request": request},
        )

        return APIResponse.success(
            message=_("پروفایل کاربر"),
            data=serializer.data,
        )

    def patch(self, request):
        serializer = UserMeSerializer(
            instance=request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        logger.info(
            "Profile updated | pk=%s | fields=%s",
            request.user.pk,
            list(request.data.keys()),
        )

        return APIResponse.success(
            message=_("پروفایل با موفقیت بروزرسانی شد"),
            data=serializer.data,
        )


class DeleteAccountView(GenericAPIView):
    """
    DELETE /api/v1/users/me/delete/

    Soft Delete: کاربر غیرفعال + شماره ماسک میشه.
    باید ابتدا OTP با purpose=reset گرفته باشه.

    ── Request ──────────────────────────────
    {"code": "123456"}

    ── Response 204 ─────────────────────────
    {
        "success": true,
        "message": "حساب شما با موفقیت حذف شد"
    }
    """

    serializer_class = DeleteAccountSerializer
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        logger.warning(
            "Account self-deleted | pk=%s | phone=%s",
            request.user.pk,
            request.user.phone_number,
        )

        return APIResponse.no_content(
            message=_("حساب شما با موفقیت حذف شد"),
        )


class AvatarView(APIView):
    """
    PUT    /api/v1/users/me/avatar/   →  آپلود یا جایگزینی
    DELETE /api/v1/users/me/avatar/   →  حذف آواتار

    ── PUT Request ──────────────────────────
    Content-Type: multipart/form-data
    avatar: (binary file)

    ── PUT Response 200 ─────────────────────
    {
        "success": true,
        "message": "آواتار با موفقیت آپلود شد",
        "data": {
            "avatar_url": "https://example.com/media/avatars/..."
        }
    }

    ── DELETE Response 204 ──────────────────
    {
        "success": true,
        "message": "آواتار با موفقیت حذف شد"
    }
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def put(self, request):
        serializer = AvatarSerializer(
            instance=request.user,
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        logger.info("Avatar uploaded | pk=%s", user.pk)

        return APIResponse.success(
            message=_("آواتار با موفقیت آپلود شد"),
            data={
                "avatar_url": request.build_absolute_uri(user.avatar.url),
            },
        )

    def delete(self, request):
        user = request.user

        if not user.avatar:
            return APIResponse.not_found(
                message=_("آواتاری برای حذف وجود ندارد"),
            )

        # حذف فایل فیزیکی
        storage = user.avatar.storage
        if storage.exists(user.avatar.name):
            storage.delete(user.avatar.name)

        user.avatar = None
        user.save(update_fields=["avatar"])

        logger.info("Avatar deleted | pk=%s", user.pk)

        return APIResponse.no_content(
            message=_("آواتار با موفقیت حذف شد"),
        )


class CompleteProfileView(GenericAPIView):
    """
    POST /api/v1/users/me/complete-profile/

    تکمیل پروفایل برای شروع اولین مصاحبه.
    فقط یکبار قابل استفاده. بعدش PATCH /me/ .

    ── Request ──────────────────────────────
    {
        "first_name": "علی",
        "last_name": "رضایی",
        "job_title": "Backend Developer",
        "experience_level": "mid_level",
        "years_of_experience": 3,
        "skills": ["Python", "Django", "Docker"]
    }

    ── Response 200 ─────────────────────────
    {
        "success": true,
        "message": "پروفایل با موفقیت تکمیل شد",
        "data": { ... full profile ... }
    }
    """

    serializer_class = CompleteProfileSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(
            instance=request.user,
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        logger.info(
            "Profile completed | pk=%s | job=%s | level=%s",
            user.pk,
            user.job_title,
            user.experience_level,
        )

        return APIResponse.success(
            message=_("پروفایل با موفقیت تکمیل شد"),
            data=UserMeSerializer(
                user,
                context={"request": request},
            ).data,
        )


# ═══════════════════════════════════════════════════════════════
#                       ADMIN VIEWS
# ═══════════════════════════════════════════════════════════════


class AdminUserListView(ListAPIView):
    """
    GET /api/v1/users/admin/users/

    Query Params:
        ?search=ali
        ?is_active=true
        ?experience_level=senior
        ?ordering=-date_joined
        ?page=2

    ── Response 200 ─────────────────────────
    {
        "success": true,
        "message": "لیست کاربران",
        "data": {
            "count": 150,
            "next": "...?page=3",
            "previous": "...?page=1",
            "results": [ ... ]
        }
    }
    """

    serializer_class = AdminUserListSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    filterset_fields = {
        "is_active": ["exact"],
        "is_staff": ["exact"],
        "is_phone_verified": ["exact"],
        "experience_level": ["exact", "in"],
        "date_joined": ["gte", "lte", "date"],
        "last_login": ["gte", "lte", "isnull"],
    }
    search_fields = [
        "phone_number",
        "first_name",
        "last_name",
        "email",
        "job_title",
    ]
    ordering_fields = [
        "date_joined",
        "last_login",
        "first_name",
        "phone_number",
    ]
    ordering = ["-date_joined"]

    def get_queryset(self):
        return UserSelector.get_all_users()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)

        return APIResponse.success(
            message=_("لیست کاربران"),
            data={
                "count": response.data.get("count", 0),
                "next": response.data.get("next"),
                "previous": response.data.get("previous"),
                "results": response.data.get("results", []),
            },
        )


class AdminUserDetailView(GetUserOrNotFoundMixin, APIView):
    """
    GET    /api/v1/users/admin/users/<id>/   →  جزئیات کامل
    PATCH  /api/v1/users/admin/users/<id>/   →  ویرایش توسط ادمین
    DELETE /api/v1/users/admin/users/<id>/   →  Soft Delete

    ── DELETE Request ───────────────────────
    {"reason": "درخواست کاربر"}

    ── DELETE Response 204 ──────────────────
    {"success": true, "message": "حساب کاربر حذف شد"}
    """

    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        user, error_response = self.get_user_response_or_404(pk)
        if error_response:
            return error_response

        serializer = AdminUserDetailSerializer(
            user,
            context={"request": request},
        )

        return APIResponse.success(
            message=_("جزئیات کاربر"),
            data=serializer.data,
        )

    def patch(self, request, pk):
        user, error_response = self.get_user_response_or_404(pk)
        if error_response:
            return error_response

        serializer = AdminUserDetailSerializer(
            instance=user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        logger.info(
            "Admin updated user | pk=%s | by=%s | fields=%s",
            pk, request.user.pk, list(request.data.keys()),
        )

        return APIResponse.success(
            message=_("کاربر با موفقیت ویرایش شد"),
            data=serializer.data,
        )

    def delete(self, request, pk):
        user, error_response = self.get_user_response_or_404(pk)
        if error_response:
            return error_response

        serializer = AdminSoftDeleteSerializer(
            data=request.data,
            context={
                "request": request,
                "user_to_delete": user,
            },
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return APIResponse.no_content(
            message=_("حساب کاربر با موفقیت حذف شد"),
        )


class AdminSuspendUserView(GetUserOrNotFoundMixin, GenericAPIView):
    """
    POST /api/v1/users/admin/users/<id>/suspend/

    ── Request ──────────────────────────────
    {
        "reason": "رفتار نامناسب",
        "duration_hours": 24
    }

    ── Response 200 ─────────────────────────
    {
        "success": true,
        "message": "کاربر به مدت 24 ساعت تعلیق شد",
        "data": {
            "user_id": 5,
            "duration_hours": 24
        }
    }
    """

    serializer_class = AdminSuspendSerializer
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        user, error_response = self.get_user_response_or_404(pk)
        if error_response:
            return error_response

        serializer = self.get_serializer(
            data=request.data,
            context={
                "request": request,
                "user_to_suspend": user,
            },
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        hours = serializer.validated_data["duration_hours"]

        return APIResponse.success(
            message=_(f"کاربر به مدت {hours} ساعت تعلیق شد"),
            data={
                "user_id": user.pk,
                "duration_hours": hours,
            },
        )


class AdminUnsuspendUserView(GetUserOrNotFoundMixin, GenericAPIView):
    """
    POST /api/v1/users/admin/users/<id>/unsuspend/

    ── Request ──────────────────────────────
    {"reason": "بررسی مجدد شد"}   ← اختیاری

    ── Response 200 ─────────────────────────
    {
        "success": true,
        "message": "تعلیق کاربر رفع شد",
        "data": {"user_id": 5}
    }
    """

    serializer_class = AdminUnsuspendSerializer
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        user, error_response = self.get_user_response_or_404(pk)
        if error_response:
            return error_response

        serializer = self.get_serializer(
            data=request.data,
            context={
                "request": request,
                "user_to_unsuspend": user,
            },
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return APIResponse.success(
            message=_("تعلیق کاربر رفع شد"),
            data={"user_id": user.pk},
        )


class AdminBanUserView(GetUserOrNotFoundMixin, GenericAPIView):
    """
    POST /api/v1/users/admin/users/<id>/ban/

    بن دائمی: غیرفعال + ماسک شماره + unusable password.

    ── Request ──────────────────────────────
    {"reason": "اسپم مکرر"}

    ── Response 200 ─────────────────────────
    {
        "success": true,
        "message": "کاربر به صورت دائمی بن شد",
        "data": {"user_id": 5}
    }
    """

    serializer_class = AdminBanSerializer
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        user, error_response = self.get_user_response_or_404(pk)
        if error_response:
            return error_response

        serializer = self.get_serializer(
            data=request.data,
            context={
                "request": request,
                "user_to_ban": user,
            },
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return APIResponse.success(
            message=_("کاربر به صورت دائمی بن شد"),
            data={"user_id": user.pk},
        )


class AdminOTPHistoryView(ListAPIView):
    """
    GET /api/v1/users/admin/otp-history/<user_id>/

    Query Params:
        ?purpose=login
        ?is_used=true
        ?created_at__gte=2024-01-01
        ?ordering=-created_at

    ── Response 200 ─────────────────────────
    {
        "success": true,
        "message": "تاریخچه OTP",
        "data": {
            "count": 25,
            "next": null,
            "previous": null,
            "results": [
                {
                    "id": 1,
                    "phone_number": "09123456789",
                    "code": "123456",
                    "purpose": "login",
                    "status": "used",
                    "failed_attempts": 0,
                    "remaining_seconds": 0,
                    "ip_address": "1.2.3.4",
                    "created_at": "2024-...",
                    "used_at": "2024-..."
                }
            ]
        }
    }
    """

    serializer_class = OTPHistorySerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, OrderingFilter]

    filterset_fields = {
        "purpose": ["exact"],
        "is_used": ["exact"],
        "created_at": ["gte", "lte", "date"],
    }
    ordering_fields = ["created_at", "used_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            OTPCode.objects
            .filter(user_id=self.kwargs["user_id"])
            .select_related("user")
        )

    def list(self, request, *args, **kwargs):
        # ── چک وجود کاربر قبل از کوئری ────────
        user_id = self.kwargs["user_id"]
        if not User.objects.filter(pk=user_id).exists():
            return APIResponse.not_found(
                message=_("کاربر یافت نشد"),
            )

        response = super().list(request, *args, **kwargs)

        return APIResponse.success(
            message=_("تاریخچه OTP"),
            data={
                "count": response.data.get("count", 0),
                "next": response.data.get("next"),
                "previous": response.data.get("previous"),
                "results": response.data.get("results", []),
            },
        )


class AdminStatsView(APIView):
    """
    GET /api/v1/users/admin/stats/

    ── Response 200 ─────────────────────────
    {
        "success": true,
        "message": "آمار کاربران",
        "data": {
            "total_users": 1500,
            "active_users": 1200,
            "inactive_users": 300,
            "verified_users": 1100,
            "complete_profiles": 900,
            "staff_users": 5,
            "banned_users": 10,
            "new_today": 25,
            "new_this_week": 150,
            "new_this_month": 500,
            "experience_breakdown": {
                "junior": 300,
                "mid_level": 400,
                "senior": 200,
                "lead": 50,
                "not_set": 250
            },
            "otp_stats": {
                "total_sent": 5000,
                "total_used": 4200,
                "success_rate": 84.0,
                "today_sent": 120,
                "today_used": 95
            }
        }
    }
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        stats = StatsSelector.get_full_stats()      
        serializer = AdminStatsSerializer(stats)
        return APIResponse.success(
            message=_("آمار کاربران"),
            data=serializer.data,
        )
        
        
class LoginWithPasswordView(GenericAPIView):
    """
    POST /api/v1/users/auth/login-password/
    ورود کاربران با استفاده از شماره موبایل و رمز عبور
    """
    permission_classes = [AllowAny]
    serializer_class = LoginWithPasswordSerializer
    throttle_classes = [AnonRateThrottle] # برای جلوگیری از حملات حدس رمز عبور

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        
        # تولید توکن‌های JWT (دقیقاً همگام با منطق پروژه شما)
        refresh = RefreshToken.for_user(user)
        
        data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                "id": user.id,
                "phone_number": user.phone_number,
                "first_name": user.first_name,
                "last_name": user.last_name,
            }
        }
        
        # به‌روزرسانی زمان آخرین ورود کاربر
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        return APIResponse.success(
            data=data,
            message=_("ورود با موفقیت انجام شد")
        )
        
        
        
class SetPasswordView(GenericAPIView):
    """
    POST /api/v1/users/profile/set-password/
    تعیین رمز عبور برای بار اول یا تغییر آن برای کاربران لاگین شده
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SetPasswordSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        user = request.user
        new_password = serializer.validated_data['new_password']
        
        # هش کردن و ذخیره رمز عبور جدید
        user.set_password(new_password)
        user.save(update_fields=['password'])
        
        logger.info(f"User {user.id} successfully updated/set their password.")
        
        return APIResponse.success(
            message=_("رمز عبور با موفقیت ثبت و به‌روزرسانی شد")
        )