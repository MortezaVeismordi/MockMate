from django.urls import re_path

from apps.interviews import consumers

websocket_urlpatterns = [
    # اتصال درخواست‌های وب‌سوکت به کانسومر مصاحبه real-time
    # استفاده از re_path همراه با Regex دقیق برای Validate کردن UUID4 در لایه روتینگ
    re_path(
        r"^ws/interviews/(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/$",
        consumers.InterviewConsumer.as_asgi(),
    ),
]
