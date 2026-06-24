from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from .selectors import UserSelector, OTPSelector
from .models import OTPCode
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.db import OperationalError
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

class OTPService:
    @staticmethod
    def send_otp(phone_number, purpose, ip_address):
        # ── چک بن بودن ─────────────────────────
        if UserSelector.is_banned(phone_number):
            return {
                "success": False,
                "message": _("این شماره مسدود شده است"),
            }

        with transaction.atomic():
            # همه چک‌ها و ایجاد OTP داخل یه transaction
            user = UserSelector.get_by_phone(phone_number)
            
            if user:
                # چک cooldown با lock
                latest_otp = OTPCode.objects.select_for_update().filter(
                    user=user,
                    purpose=purpose,
                ).order_by("-created_at").first()

                if latest_otp:
                    elapsed = (timezone.now() - latest_otp.created_at).total_seconds()
                    if elapsed < 60:
                        wait = int(60 - elapsed)
                        return {
                            "success": False,
                            "message": _(f"{wait} ثانیه تا ارسال مجدد صبر کنید"),
                        }

                if OTPSelector.is_daily_limit_reached(user):
                    return {
                        "success": False,
                        "message": _("سقف ارسال روزانه پر شده"),
                    }
            else:
                user, created = User.objects.get_or_create(
                    phone_number=phone_number,
                    defaults={"is_active": False},
                )
                # چک ban برای کاربر تازه‌ساخته
                if user.is_banned:
                    return {
                        "success": False,
                        "message": _("این شماره مسدود شده است"),
                    }

            otp = OTPCode.create_otp(
                user=user,
                purpose=purpose,
                ip_address=ip_address,
            )

            sms_body = f"کد تایید شما برای ورود به پلتفرم هوش مصنوعی:\n{otp.code}\nمعتبر برای ۲ دقیقه."
            
            notification_record = Notification.objects.create(
                user=user,
                recipient=phone_number,
                body=sms_body,
                notification_type=Notification.Type.SMS,
                status=Notification.Status.PENDING
            )

        # on_commit خارج از with هست ولی بعد از commit اجرا میشه ✓
        from apps.notifications.tasks import send_otp_notification_task
        transaction.on_commit(
            lambda: send_otp_notification_task.delay(notification_id=notification_record.id)
        )

        return {
            "success": True,
            "message": _("کد OTP ارسال شد"),
            "is_new_user": not user.is_profile_complete,
        }

    @staticmethod
    def verify_otp(
        phone_number: str,
        code: str,
        purpose: str = OTPCode.Purpose.LOGIN,
    ) -> dict:
        """
        تایید OTP و فعال‌سازی کاربر
        """
        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return {"success": False, "message": _("کاربر یافت نشد")}
        except OperationalError:
            logger.error("DB connection failed", exc_info=True)
            return {"success": False, "message": _("خطای سرور")}

        success, message = OTPCode.verify_otp(
            user=user,
            code=code,
            purpose=purpose,
        )

        if not success:
            return {
                "success": False,
                "message": message,
                "user": None,
            }

        # فعال‌سازی کاربر
        update_fields = []

        if not user.is_active:
            user.is_active = True
            update_fields.append("is_active")

        if not user.is_phone_verified:
            user.is_phone_verified = True
            update_fields.append("is_phone_verified")

        if update_fields:
            user.save(update_fields=update_fields)

        return {
            "success": True,
            "message": message,
            "user": user,
            "is_new_user": not user.is_profile_complete,
        }
        
    @staticmethod
    def verify_otp_for_deletion(user, code: str) -> dict:
        """
        تایید OTP برای حذف حساب.
        از همان verify_otp داخلی استفاده میکنه ولی
        purpose رو خودش ست میکنه.
        """
        success, message = OTPCode.verify_otp(
            user=user,
            code=code,
            purpose=OTPCode.Purpose.RESET,
        )

        return {
            "success": success,
            "message": message,
        }

    @staticmethod
    def verify_otp_for_action(
        user,
        code: str,
        purpose: str = OTPCode.Purpose.RESET,
    ) -> dict:
        """
        تایید OTP برای هر اکشن حساس (حذف، تغییر شماره، ...).
        همه جا از این متد استفاده کنید.
        """
        success, message = OTPCode.verify_otp(
            user=user,
            code=code,
            purpose=purpose,
        )

        return {
            "success": success,
            "message": message,
        }