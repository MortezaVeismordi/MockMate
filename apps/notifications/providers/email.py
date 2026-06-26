import logging
from smtplib import SMTPException
from typing import Optional, Tuple

from django.core.mail import send_mail

from .base import BaseNotificationProvider

logger = logging.getLogger(__name__)


class ConsoleEmailProvider(BaseNotificationProvider):
    """
    پرووایدر محیط توسعه (Development)
    محتوای ایمیل را بدون ارسال واقعی، در ترمینال کانتینر داکر چاپ می‌کند.
    """

    def send(self, recipient: str, body: str, title: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        subject = title or "AI Interviewer Notification"
        logger.info(f"[Console-Email] Simulating email delivery to {recipient}")

        # شبیه‌سازی بصری خروجی ایمیل برای دولوپر
        print("\n" + "═" * 60)
        print(" 📧 [EMAIL CONSOLE PROVIDER] — DEV MODE")
        print(f" 👤 گیرنده: {recipient}")
        print(f" 📌 موضوع: {subject}")
        print(f" 📝 متن بدنه:\n\n {body}\n")
        print("═" * 60 + "\n")

        return True, "mock_email_id_dev_only", None


class SmtpEmailProvider(BaseNotificationProvider):
    """
    پرووایدر محیط عملیاتی (Production)
    ارسال ایمیل واقعی از طریق پروتکل SMTP و مدیریت خطاهای لایه Mail Server.
    """

    def send(self, recipient: str, body: str, title: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        subject = title or "AI Interviewer — اعلان پلتفرم"
        logger.info(f"[Smtp-Email] Attempting to send live email to {recipient}")

        try:
            # استفاده از متد داخلی و بهینه جنگو
            # فرستنده (from_email) به‌صورت خودکار از settings.DEFAULT_FROM_EMAIL خوانده می‌شود
            send_mail(
                subject=subject,
                message=body,
                from_email=None,
                recipient_list=[recipient],
                fail_silently=False,  # عمداً False می‌گذاریم تا خطاها پرتاب شوند و بتوانیم لاگ کنیم
            )

            logger.info(f"[Smtp-Email] Email successfully dispatched to {recipient}")
            return True, "smtp_success_dispatched_id", None

        # مدیریت خطاهای تخصصی لایه پروتکل SMTP (تایم‌اوت، احراز هویت اشتباه سرور، رد شدن گیرنده)
        except SMTPException as e:
            error_msg = f"SMTP protocol error occurred: {str(e)}"
            logger.error(f"[Smtp-Email] Mail Server Refusal: {error_msg}")
            return False, None, error_msg

        except Exception as e:
            error_msg = f"Unexpected system error during email transport: {str(e)}"
            logger.error(f"[Smtp-Email] General Exception: {error_msg}")
            return False, None, error_msg
