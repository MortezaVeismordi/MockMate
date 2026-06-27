import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class BaseNotificationProvider(ABC):
    """
    رابط انتزاعی (Abstract Interface) پایه‌ برای تمامی پرووایدرهای سیستم اعلان.
    """

    @abstractmethod
    def send(
        self, recipient: str, body: str, title: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        pass


class ConsoleSMSProvider(BaseNotificationProvider):
    """
    پرووایدر مخصوص محیط لوکال/توسعه.
    پیامک را به پنل واقعی نمی‌فرستد، بلکه متن آن را در ترمینال ورکر Celery چاپ می‌کند.
    """

    def send(
        self, recipient: str, body: str, title: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        # چاپ پیام به شکل فرمت‌شده و واضح در ترمینال سلری
        logger.info(
            "\n"
            + "=" * 50
            + "\n📱 [SMS OUTBOX - LOCAL DEV]"
            + f"\nTo: {recipient}"
            + f"\nTitle: {title or 'N/A'}"
            + f"\nContent:\n{body}"
            + "\n"
            + "=" * 50
        )

        # برگرداندن وضعیت موفقیت‌آمیز به سرویس (success, provider_message_id, error_message)
        return True, "mock_local_msg_id_1001", None
