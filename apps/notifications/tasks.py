# apps/notifications/tasks.py

import logging

from celery import shared_task

from django.db import transaction

logger = logging.getLogger(__name__)


# نام متد دقیقا مطابق با CELERY_TASK_ROUTES در فایل production.py شما
@shared_task(
    bind=True,
    name="apps.notifications.tasks.send_otp",  # تغییر نام برای انطباق با روتینگ شما
    max_retries=3,
    autoretry_for=(RuntimeError, Exception),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def send_otp_notification_task(self, notification_id: int):
    """
    تسک ناهمگام برای ارسال پیامک یا ایمیل کد OTP
    """
    logger.info(f"[Celery] Processing OTP notification ID: {notification_id}")

    from .models import Notification
    from .services import NotificationService

    try:
        notification = Notification.objects.get(id=notification_id)
    except Notification.DoesNotExist:
        logger.error(f"[Celery] Notification {notification_id} not found.")
        return

    if notification.status == Notification.Status.SENT:
        return

    try:
        NotificationService.send_notification(notification_id=notification_id)
    except Exception as exc:
        logger.warning(
            f"[Celery] Retry delivering notification {notification_id}. Attempt {self.request.retries}"
        )
        try:
            with transaction.atomic():
                notif_record = Notification.objects.select_for_update().get(
                    id=notification_id
                )
                notif_record.retry_count = self.request.retries + 1
                notif_record.save(update_fields=["retry_count"])
        except Exception as db_err:
            logger.error(f"Failed to update retry count: {db_err}")

        raise self.retry(exc=exc)


@shared_task(name="apps.notifications.tasks.send_welcome_sms")
def send_welcome_sms(phone_number: str, first_name: str):
    """ارسال پیامک خوش‌آمدگویی"""
    logger.info(f"[Welcome SMS] Sending to {phone_number}")
    from .models import Notification
    from .services import NotificationService

    body = f"سلام {first_name}! به MockMate خوش آمدید."
    NotificationService.create_notification(
        recipient=phone_number,
        body=body,
        notification_type=Notification.Type.SMS,
    )


@shared_task(name="apps.notifications.tasks.send_welcome_notification")
def send_welcome_notification(user_id: int):
    """ارسال نوتیفیکیشن خوش‌آمدگویی"""
    logger.info(f"[Welcome Notification] user_id={user_id}")
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
        send_welcome_sms.delay(
            phone_number=user.phone_number,
            first_name=user.first_name or "کاربر عزیز",
        )
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for welcome notification")


@shared_task(name="apps.notifications.tasks.send_profile_completed_notification")
def send_profile_completed_notification(user_id: int):
    """ارسال نوتیفیکیشن تکمیل پروفایل"""
    logger.info(f"[Profile Completed] user_id={user_id}")
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
        from .models import Notification
        from .services import NotificationService

        NotificationService.create_notification(
            recipient=user.phone_number,
            body="پروفایل شما تکمیل شد! آماده شروع مصاحبه هستید.",
            notification_type=Notification.Type.SMS,
            user=user,
        )
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for profile notification")
