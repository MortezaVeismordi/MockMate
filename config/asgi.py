import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django_asgi_app = get_asgi_application()

import apps.interviews.routing  # noqa: E402
from apps.interviews.middleware import JWTAuthMiddleware  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(          # ← جای AuthMiddlewareStack
        URLRouter(
            apps.interviews.routing.websocket_urlpatterns
        )
    ),
})
