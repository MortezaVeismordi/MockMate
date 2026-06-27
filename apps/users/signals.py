import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import Signal, receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .selectors import UserSelector

logger = logging.getLogger(__name__)

User = get_user_model()


# ─────────────────────────────────────────────────────────────────
#  Custom Signals
# ─────────────────────────────────────────────────────────────────

# وقتی کاربر برای اولین بار OTP رو تایید میکنه
user_phone_verified = Signal()
# providing_args: ["user", "timestamp"]

# وقتی کاربر پروفایلش رو کامل میکنه
user_profile_completed = Signal()
# providing_args: ["user"]

# وقتی کاربر بعد از مدتی برمیگرده (re-login)
user_returned = Signal()
# providing_args: ["user", "days_absent"]


# ─────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────


def _get_changed_fields(instance) -> set:
    """
    فیلدهایی که نسبت به دیتابیس تغییر کردن رو برمیگردونه.
    اگه آبجکت جدیده (هنوز save نشده)، ست خالی برمیگردونه.
    """
    if not instance.pk:
        return set()

    try:
        old = instance.__class__.objects.get(pk=instance.pk)
    except instance.__class__.DoesNotExist:
        return set()

    changed = set()
    for field in instance._meta.fields:
        field_name = field.name
        if getattr(old, field_name) != getattr(instance, field_name):
            changed.add(field_name)

    return changed


def _is_profile_now_complete(old_instance, new_instance) -> bool:
    """
    آیا پروفایل در این save از ناقص به کامل تبدیل شد؟
    """
    was_complete = bool(
        old_instance.first_name
        and old_instance.last_name
        and old_instance.job_title
        and old_instance.experience_level
    )
    return not was_complete and new_instance.is_profile_complete


# ─────────────────────────────────────────────────────────────────
#  pre_save  →  تغییرات رو قبل از ذخیره ثبت میکنیم
# ─────────────────────────────────────────────────────────────────


@receiver(pre_save, sender=User)
def capture_user_state_before_save(sender, instance, **kwargs):
    """
    وضعیت قبلی کاربر رو روی instance ذخیره میکنیم
    تا در post_save بتونیم مقایسه کنیم.
    این الگو رو _snapshot_ مینامیم.
    """
    if not instance.pk:
        # کاربر جدیده - هیچ وضعیت قبلی‌ای نداریم
        instance._pre_save_snapshot = None
        return

    try:
        instance._pre_save_snapshot = UserSelector.get_by_id(instance.pk)
    except User.DoesNotExist:
        instance._pre_save_snapshot = None


# ─────────────────────────────────────────────────────────────────
#  post_save  →  بعد از ذخیره واکنش نشون میدیم
# ─────────────────────────────────────────────────────────────────


@receiver(post_save, sender=User)
def handle_user_created(sender, instance, created, **kwargs):
    """
    فقط برای کاربر تازه‌ساخته‌شده اجرا میشه.
    """
    if not created:
        return

    logger.info(
        "New user registered | phone=%s | pk=%s",
        instance.phone_number,
        instance.pk,
    )

    # اینجا میتونی UserProfile یا هر مدل وابسته دیگه‌ای بسازی
    # مثلاً:
    # UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def handle_phone_verification(sender, instance, created, **kwargs):
    """
    وقتی is_phone_verified از False به True تغییر میکنه،
    custom signal ارسال میکنیم.
    """
    if created:
        return

    snapshot = getattr(instance, "_pre_save_snapshot", None)
    if snapshot is None:
        return

    was_verified = snapshot.is_phone_verified
    is_now_verified = instance.is_phone_verified

    if not was_verified and is_now_verified:
        logger.info(
            "Phone verified | phone=%s | pk=%s",
            instance.phone_number,
            instance.pk,
        )

        user_phone_verified.send(
            sender=User,
            user=instance,
            timestamp=timezone.now(),
        )


@receiver(post_save, sender=User)
def handle_profile_completion(sender, instance, created, **kwargs):
    """
    وقتی کاربر پروفایلش رو کامل میکنه، signal میده.
    """
    if created:
        return

    snapshot = getattr(instance, "_pre_save_snapshot", None)
    if snapshot is None:
        return

    if _is_profile_now_complete(snapshot, instance):
        logger.info(
            "Profile completed | phone=%s | pk=%s",
            instance.phone_number,
            instance.pk,
        )

        user_profile_completed.send(
            sender=User,
            user=instance,
        )


@receiver(post_save, sender=User)
def handle_account_activated(sender, instance, created, **kwargs):
    """
    وقتی حساب کاربر فعال میشه (is_active: False → True).
    """
    if created:
        return

    snapshot = getattr(instance, "_pre_save_snapshot", None)
    if snapshot is None:
        return

    was_active = snapshot.is_active
    is_now_active = instance.is_active

    if not was_active and is_now_active:
        logger.info(
            "Account activated | phone=%s | pk=%s",
            instance.phone_number,
            instance.pk,
        )

        # ارسال پیام خوش‌آمدگویی از طریق Celery
        _send_welcome_notification(instance)


@receiver(post_save, sender=User)
def handle_account_deactivated(sender, instance, created, **kwargs):
    """
    وقتی حساب کاربر غیرفعال میشه (is_active: True → False).
    """
    if created:
        return

    snapshot = getattr(instance, "_pre_save_snapshot", None)
    if snapshot is None:
        return

    was_active = snapshot.is_active
    is_now_active = instance.is_active

    if was_active and not is_now_active:
        logger.warning(
            "Account deactivated | phone=%s | pk=%s",
            instance.phone_number,
            instance.pk,
        )


# ─────────────────────────────────────────────────────────────────
#  post_delete
# ─────────────────────────────────────────────────────────────────


@receiver(post_delete, sender=User)
def handle_user_deleted(sender, instance, **kwargs):
    """
    بعد از حذف کاربر، فایل‌های مرتبط رو پاک میکنیم.
    """
    logger.warning(
        "User deleted | phone=%s | pk=%s",
        instance.phone_number,
        instance.pk,
    )

    _cleanup_user_avatar(instance)


# ─────────────────────────────────────────────────────────────────
#  Custom Signal Receivers
# ─────────────────────────────────────────────────────────────────


@receiver(user_phone_verified)
def on_phone_verified_send_welcome_sms(sender, user, timestamp, **kwargs):
    """
    بعد از تایید شماره، پیام تبریک ارسال کن.
    """
    try:
        from apps.notifications.tasks import send_welcome_sms

        send_welcome_sms.delay(
            phone_number=user.phone_number,
            first_name=user.first_name or _("کاربر عزیز"),
        )
    except Exception as exc:
        logger.error(
            "Failed to send welcome SMS | phone=%s | error=%s",
            user.phone_number,
            exc,
        )


@receiver(user_profile_completed)
def on_profile_completed(sender, user, **kwargs):
    """
    بعد از تکمیل پروفایل، کاربر رو برای شروع مصاحبه آماده کن.
    """
    logger.info(
        "User profile completed - ready for interview | phone=%s",
        user.phone_number,
    )

    try:
        from apps.notifications.tasks import \
            send_profile_completed_notification

        send_profile_completed_notification.delay(user_id=user.pk)
    except Exception as exc:
        logger.error(
            "Failed to send profile completion notification | pk=%s | error=%s",
            user.pk,
            exc,
        )


# ─────────────────────────────────────────────────────────────────
#  Private Helpers
# ─────────────────────────────────────────────────────────────────


def _send_welcome_notification(user) -> None:
    """ارسال نوتیف خوش‌آمدگویی از طریق Celery."""
    try:
        from apps.notifications.tasks import send_welcome_notification

        send_welcome_notification.delay(user_id=user.pk)
    except Exception as exc:
        logger.error(
            "Failed to queue welcome notification | pk=%s | error=%s",
            user.pk,
            exc,
        )


def _cleanup_user_avatar(user) -> None:
    """پاک‌سازی آواتار کاربر حذف‌شده از storage."""
    if not user.avatar:
        return

    try:
        storage = user.avatar.storage
        if storage.exists(user.avatar.name):
            storage.delete(user.avatar.name)
            logger.info(
                "Avatar deleted | phone=%s | path=%s",
                user.phone_number,
                user.avatar.name,
            )
    except Exception as exc:
        logger.error(
            "Failed to delete avatar | phone=%s | error=%s",
            user.phone_number,
            exc,
        )
