import logging
from abc import ABC, abstractmethod
from typing import Optional, Type

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Notification
from .providers.base import BaseNotificationProvider, ConsoleSMSProvider
from .providers.email import ConsoleEmailProvider, SmtpEmailProvider
from .providers.sms import KavenegarSMSProvider

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
#  1. سرویس ارکستراتور اعلان‌ها (Notification Coordinator Service)
# ──────────────────────────────────────────────────────────────────────────────

class NotificationService:
    """
    سرویس اصلی مدیریت چرخه عمر اعلان‌ها در لایه بیزینس پروژه.
    این کلاس هماهنگ‌کننده دیتابیس، استراتژی‌های ارسال و تسک‌های Celery است.
    """

    @classmethod
    def create_notification(
        cls,
        recipient: str,
        body: str,
        notification_type: str = Notification.Type.SMS,
        user = None,
        title: str = ""
    ) -> Notification:
        """
        گام اول: ثبت سریع اعلان در دیتابیس لوکال و هماهنگی با Celery برای ارسال آسنکرون.
        """
        # ۱. ساخت رکورد با وضعیت pending
        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            recipient=recipient,
            title=title,
            body=body,
            status=Notification.Status.PENDING
        )

        # ۲. ارسال هماهنگ به صف Celery (تسک را در گام‌های بعدی می‌نویسیم)
        # ما فقط ID را پاس می‌دهیم تا دیتای سنگین جابجا نشود
        from .tasks import send_otp_notification_task
        send_otp_notification_task.delay(notification_id=notification.id)

        return notification

    @classmethod
    def send_notification(cls, notification_id: int, provider_class: Optional[Type[BaseNotificationProvider]] = None) -> None:
        """
        این متد درون ورکر Celery اجرا می‌شود و وظیفه ارسال واقعی و مدیریت خطا را دارد.
        """
        try:
            notification = Notification.objects.get(id=notification_id)
        except Notification.DoesNotExist:
            logger.error(f"Notification with ID {notification_id} not found in database.")
            return

        if notification.status == Notification.Status.SENT:
            logger.warning(f"Notification {notification_id} is already sent. Skipping.")
            return

        # ─── هوشمندسازی خودکار انتخاب پرووایدر در محیط لوکال ─────────────────────
        if provider_class is None:
            provider_class = cls._resolve_provider(notification.notification_type)

        if not provider_class:
            logger.error(f"No valid provider class found for notification type: {notification.notification_type}")
            notification.mark_as_failed(error=f"No valid provider class found for notification type: {notification.notification_type}")
            return
        # ──────────────────────────────────────────────────────────────────────────

        # نمونه‌سازی از استراتژی ست شده
        provider = provider_class()
        
        logger.info(f"Attempting to send notification {notification.id} via {provider_class.__name__}")
        
        # صدا زدن متد ارسالِ پرووایدر
        success, provider_id, error_msg = provider.send(
            recipient=notification.recipient,
            body=notification.body,
            title=notification.title
        )

        if success:
            notification.mark_as_sent(provider_id=provider_id)
            logger.info(f"Notification {notification.id} sent successfully. Provider ID: {provider_id}")
        else:
            notification.mark_as_failed(error=error_msg or "Unknown provider error")
            logger.error(f"Notification {notification.id} failed to send. Error: {error_msg}")
            raise RuntimeError(f"Provider failed to deliver message: {error_msg}")
        
    @staticmethod
    def _resolve_provider(notification_type: str):
        """
        انتخاب provider بر اساس نوع notification و محیط (dev/prod)
        """
        from django.conf import settings
        
        is_production = not settings.DEBUG

        if notification_type == Notification.Type.SMS:
            if is_production:
                return KavenegarSMSProvider
            return ConsoleSMSProvider

        if notification_type == Notification.Type.EMAIL:
            if is_production:
                return SmtpEmailProvider
            return ConsoleEmailProvider

        return None