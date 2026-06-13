import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django_asgi_app = get_asgi_application()

import apps.interviews.routing
from apps.interviews.middleware import JWTAuthMiddleware  # ← اضافه شد

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(          # ← جای AuthMiddlewareStack
        URLRouter(
            apps.interviews.routing.websocket_urlpatterns
        )
    ),
})