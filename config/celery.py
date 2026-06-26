# config/celery.py
import os

from celery import Celery

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.development"
)

app = Celery("ai_interviewer")

app.config_from_object(
    "django.conf:settings",
    namespace="CELERY"
)

# همه tasks.py توی appها رو auto-discover میکنه
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
