from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from django.utils import timezone


def health_check(request):
    """
    بررسی وضعیت سرویس‌های اصلی.
    Nginx و Docker healthcheck از این استفاده میکنن.
    """
    checks = {
        "status": "ok",
        "timestamp": timezone.now().isoformat(),
        "services": {}
    }

    # ── چک Database ───────────────────────────
    try:
        connection.ensure_connection()
        checks["services"]["database"] = "ok"
    except Exception:
        checks["services"]["database"] = "error"
        checks["status"] = "degraded"

    # ── چک Redis ──────────────────────────────
    try:
        cache.set("health_check", "ok", timeout=5)
        cache.get("health_check")
        checks["services"]["redis"] = "ok"
    except Exception:
        checks["services"]["redis"] = "error"
        checks["status"] = "degraded"

    status_code = 200 if checks["status"] == "ok" else 503
    return JsonResponse(checks, status=status_code)


urlpatterns = [
    path("super-admin/",    admin.site.urls),
    path("health/",   health_check, name="health-check"),
    path("api/v1/",   include("apps.users.urls", namespace="users")),
    path('api/v1/questions/', include('apps.questions.urls', namespace='v1-questions')),
    path("api/v1/interviews/", include("apps.interviews.urls", namespace="interviews")),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
