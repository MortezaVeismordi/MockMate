# Project Context Documentation

**Generated on:** 2026-06-24

---

## 1. Project Overview & Problem Domain

The repository implements a **Django‑based interview‑assistant platform** that provides:
- **User management** (registration, login with password + OTP, profile handling) – see `apps/users/`.
- **Interview question & answer handling** – see `apps/questions/` (question ingestion, storage, services).
- **Real‑time interview notifications** via **WebSocket** and **Celery**‑driven background tasks – see `apps/notifications/`.
- **Extensible notification providers** (email, SMS) for delivering interview updates.
- **Dockerised deployment** for production and development environments.

The system is intended for **technical interview preparation** where candidates receive curated questions, answer them, and get real‑time feedback.

---

## 2. Folder Structure (selected files only) 

| Path | Description |
|------|-------------|
| `apps/__init__.py` | Marks `apps` as a Python package.
| `apps/users/__init__.py` | Package init for the *users* app.
| `apps/users/admin.py` | Django admin registration for user models.
| `apps/users/apps.py` | AppConfig for the *users* app.
| `apps/users/exception_handler.py` | Centralised API exception handling utilities.
| `apps/users/response.py` | Helper functions to build standardised JSON responses.
| `apps/users/selectors.py` | Query‑helper functions (e.g., `get_user_by_email`).
| `apps/users/signals.py` | Django signals (e.g., post‑save actions for OTP creation).
| `apps/users/models.py` | Core ORM models: `User`, `OTP`, `Profile`.
| `apps/users/managers.py` | Custom model managers for `User` and `OTP`.
| `apps/users/services.py` | Business‑logic layer: authentication, OTP verification, password reset.
| `apps/users/exception_handler.py` | Global DRF exception handling for the *users* app.
| `apps/notifications/__init__.py` | Package init for the *notifications* app.
| `apps/notifications/apps.py` | AppConfig for the *notifications* app.
| `apps/notifications/models.py` | Notification ORM model.
| `apps/notifications/providers/base.py` | Abstract base class for notification providers.
| `apps/notifications/providers/email.py` | Email provider implementation (uses Django `send_mail`).
| `apps/notifications/providers/sms.py` | SMS provider stub (integrates with external SMS gateway).
| `apps/notifications/tasks.py` | Celery tasks that dispatch notifications asynchronously.
| `apps/questions/__init__.py` | Package init for the *questions* app.
| `apps/questions/apps.py` | AppConfig for the *questions* app.
| `apps/questions/admin.py` | Django admin registration for question models.
| `apps/questions/models.py` | ORM models: `Question`, `Answer`, `Topic`.
| `apps/questions/services.py` | Service layer for CRUD, ingestion pipeline, and scoring.
| `apps/questions/management/commands/import_questions.py` | Custom Django management command to bulk‑import questions.
| `apps/questions/ingestion/__init__.py` | Package init for ingestion adapters.
| `apps/questions/ingestion/base_adapter.py` | Abstract base class for question‑source adapters.
| `apps/questions/ingestion/awesome_adapter.py` | Adapter that parses the *Awesome‑Interview‑Questions* repo format.
| `apps/questions/ingestion/pipeline.py` | Orchestrates ingestion steps (fetch → parse → save).
| `config/__init__.py` | Makes `config` a Python package.
| `config/settings/__init__.py` | Shared settings loader.
| `config/settings/base.py` | Base Django settings (common to all envs).
| `config/settings/development.py` | Development‑specific overrides (debug, local DB).
| `config/settings/production.py` | Production‑specific overrides (security, allowed hosts).
| `config/settings/logging.py` | Logging configuration dict.
| `config/settings/testing.py` | Settings for test suite execution.
| `config/celery.py` | Celery app configuration (broker, backend, task routing).
| `config/wsgi.py` | WSGI entry point for deployment.
| `docker/Dockerfile` | Docker image definition for the Django app.
| `docker-compose.yml` | Development compose file (services: `web`, `db`, `celery`, `redis`).
| `docker-compose.prod.yml` | Production compose (adds Nginx, gunicorn).
| `docker/nginx/proxy_params.conf` | Nginx proxy configuration used in prod.
| `requirements/development.txt` | Development‑time Python dependencies (with exact versions).
| `requirements/production.txt` | Production‑time Python dependencies (with exact versions).
| `manage.py` | Django management script.
| `scripts/celery-entrypoint.sh` | Entrypoint script for the Celery worker container.

---

## 3. Tech Stack (Exact Versions)

| Component | Version (as pinned in `requirements/*.txt`) |
|-----------|--------------------------------------------|
| Python | 3.11.9 |
| Django | 4.2.13 |
| djangorestframework | 3.15.1 |
| django‑cors‑headers | 4.3.1 |
| drf‑spectacular | 0.27.2 |
| celery | 5.4.0 |
| redis | 5.0.3 (used as broker/backend) |
| psycopg2‑binary | 2.9.9 |
| gunicorn | 22.0.0 |
| uvicorn | 0.30.1 (for optional ASGI support) |
| channels | 4.1.0 |
| channels‑redis | 4.2.0 |
| python‑dotenv | 1.0.1 |
| dj‑email‑url | 1.0.6 |
| django‑rest‑framework‑simplejwt | 5.3.1 |
| django‑otp | 1.2.0 |
| django‑allauth | 0.62.1 |
| requests | 2.32.3 |
| boto3 | 1.35.18 |
| pyjwt | 2.9.0 |
| pytest‑django | 4.8.0 |
| factory‑boy | 3.3.1 |
| coverage | 7.6.0 |
| black | 24.4.2 |
| isort | 5.13.2 |
| flake8 | 7.1.1 |
| mypy | 1.11.1 |
| pre‑commit | 3.8.0 |

---

## 4. Architecture & Design Patterns

| Pattern | Description | File(s) Demonstrating the Pattern |
|---------|-------------|----------------------------------|
| **App Config** | Each Django app defines an `AppConfig` for ready‑state initialisation. | `apps/users/apps.py`, `apps/notifications/apps.py`, `apps/questions/apps.py` |
| **Service Layer** | Business logic is isolated from views/serializers into service modules. | `apps/users/services.py`, `apps/questions/services.py` |
| **Repository / Selector Pattern** | Small query helper functions encapsulate ORM calls. | `apps/users/selectors.py` |
| **Adapter Pattern** | Ingestion adapters abstract over various question sources. | `apps/questions/ingestion/base_adapter.py`, `apps/questions/ingestion/awesome_adapter.py` |
| **Strategy / Provider Pattern** | Notification providers are interchangeable implementations of a common base. | `apps/notifications/providers/base.py`, `apps/notifications/providers/email.py`, `apps/notifications/providers/sms.py` |
| **Celery Task Queue** | Asynchronous work (e.g., sending notifications) is delegated to Celery workers. | `apps/notifications/tasks.py`, `config/celery.py` |
| **Signal‑Driven Side‑Effects** | Django signals trigger OTP creation and email dispatch after user creation. | `apps/users/signals.py` |
| **Command‑Pattern** | Custom management command to import questions. | `apps/questions/management/commands/import_questions.py` |
| **Settings Inheritance** | Settings are split into base, development, production, and testing modules. | `config/settings/base.py`, `config/settings/development.py`, `config/settings/production.py`, `config/settings/testing.py` |

---

## 5. Core Components

### 5.1 Users App (`apps/users/`)
| File | Responsibility | Key Classes / Functions (signature) | Dependencies |
|------|----------------|------------------------------------|--------------|
| `models.py` | ORM definitions for authentication and profile data. | `class User(AbstractBaseUser, PermissionsMixin)`, `class OTP(models.Model)`, `class Profile(models.Model)` | `django.contrib.auth`, `django.db.models` |
| `managers.py` | Custom managers for `User` and `OTP`. | `class UserManager(BaseUserManager)`, `class OTPManager(models.Manager)` | `django.contrib.auth.base_user` |
| `services.py` | Business logic for login, password auth, OTP verification, token generation. | `def authenticate(email: str, password: str) -> User`, `def send_otp(user: User) -> OTP`, `def verify_otp(user: User, code: str) -> bool`, `def generate_jwt(user: User) -> str` | `django.contrib.auth`, `django.utils.timezone`, `jwt` |
| `selectors.py` | Simple query helpers. | `def get_user_by_email(email: str) -> Optional[User]` | `apps.users.models` |
| `signals.py` | Post‑save signals for creating `Profile` and sending OTP emails. | `@receiver(post_save, sender=User) def create_profile_and_otp(sender, instance, created, **kwargs): ...` | `django.db.models.signals`, `apps.users.services` |
| `exception_handler.py` | DRF exception handling customisation. | `def custom_exception_handler(exc, context) -> Response` | `rest_framework.exceptions`, `rest_framework.response` |
| `response.py` | Helper to build standard JSON payloads. | `def success(data: Any, message: str = "OK") -> JsonResponse`, `def error(message: str, status: int = 400) -> JsonResponse` | `django.http` |
| `admin.py` | Registers models with Django admin. | `admin.site.register(User)`, `admin.site.register(Profile)`, `admin.site.register(OTP)` | `django.contrib.admin` |
| `apps.py` | AppConfig (`class UsersConfig(AppConfig): name = "apps.users"`). | — | `django.apps` |

### 5.2 Questions App (`apps/questions/`)
| File | Responsibility | Key Classes / Functions | Dependencies |
|------|----------------|--------------------------|--------------|
| `models.py` | Question/Answer domain entities. | `class Topic(models.Model)`, `class Question(models.Model)`, `class Answer(models.Model)` | `django.db.models` |
| `services.py` | CRUD, ingestion pipeline orchestration, scoring logic. | `def create_question(data: dict) -> Question`, `def ingest_questions(source: str) -> List[Question]`, `def score_answer(answer: Answer) -> float` | `apps.questions.models`, `apps.questions.ingestion.pipeline` |
| `admin.py` | Admin registration for topic/question/answer. | `admin.site.register(Topic)`, `admin.site.register(Question)`, `admin.site.register(Answer)` | `django.contrib.admin` |
| `apps.py` | AppConfig (`class QuestionsConfig(AppConfig): name = "apps.questions"`). | — | `django.apps` |
| `ingestion/base_adapter.py` | Abstract base for adapters that fetch raw question data. | `class BaseAdapter(ABC): @abstractmethod def fetch(self) -> Any: ...` | `abc`, `typing` |
| `ingestion/awesome_adapter.py` | Concrete implementation for the *awesome‑interview‑questions* GitHub repo. | `class AwesomeAdapter(BaseAdapter): def fetch(self) -> List[dict]: ...` | `requests`, `BaseAdapter` |
| `ingestion/pipeline.py` | Coordinates ingestion steps: fetch → parse → persist. | `def run(source: str) -> List[Question]: ...` | `apps.questions.ingestion.base_adapter`, `apps.questions.services` |
| `management/commands/import_questions.py` | Django management command exposing the ingestion pipeline via CLI. | `class Command(BaseCommand): help = "Import interview questions from a source"
    def add_arguments(self, parser): parser.add_argument('source')
    def handle(self, *args, **options): ...` | `django.core.management.base`, `apps.questions.ingestion.pipeline` |

### 5.3 Notifications App (`apps/notifications/`)
| File | Responsibility | Key Classes / Functions | Dependencies |
|------|----------------|--------------------------|--------------|
| `models.py` | Stores notification records. | `class Notification(models.Model): user = models.ForeignKey(settings.AUTH_USER_MODEL, …)`, `type = models.CharField(max_length=30)`, `payload = JSONField()` | `django.db.models` |
| `providers/base.py` | Abstract base class for providers. | `class BaseProvider(ABC): @abstractmethod def send(self, notification: Notification) -> None: ...` | `abc` |
| `providers/email.py` | Email provider implementation using Django's email utilities. | `class EmailProvider(BaseProvider): def send(self, notification): send_mail(subject, body, from_email, [notification.user.email])` | `django.core.mail`, `BaseProvider` |
| `providers/sms.py` | SMS provider stub (integration point for external SMS gateway). | `class SMSProvider(BaseProvider): def send(self, notification): # placeholder for Twilio/MessageBird API` | `requests` (optional) |
| `tasks.py` | Celery tasks that dispatch notifications asynchronously. | `@shared_task def dispatch_notification(notification_id: int): notification = Notification.objects.get(pk=notification_id); provider = get_provider(notification.type); provider.send(notification)` | `celery`, `apps.notifications.models`, `apps.notifications.providers` |
| `apps.py` | AppConfig (`class NotificationsConfig(AppConfig): name = "apps.notifications"`). | — | `django.apps` |

### 5.4 Core Configuration (`config/`)
| File | Responsibility | Key Variables / Functions |
|------|----------------|----------------------------|
| `settings/base.py` | Shared Django settings (INSTALLED_APPS, MIDDLEWARE, DATABASES placeholder). | `INSTALLED_APPS = ["django.contrib.admin", "apps.users", "apps.questions", "apps.notifications", …]`<br>`DATABASES = {"default": env.db()}` |
| `settings/development.py` | Development overrides (DEBUG=True, local SQLite, console email backend). | `DEBUG = True`<br>`EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"` |
| `settings/production.py` | Production overrides (DEBUG=False, PostgreSQL, secure cookies, real email backend). | `DEBUG = False`<br>`ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")`<br>`SECURE_SSL_REDIRECT = True` |
| `settings/testing.py` | Test‑runner specific settings (uses in‑memory SQLite, disables password hashing). | `PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]` |
| `settings/logging.py` | Logging dict configuration (handlers for console, file, security). | `LOGGING = {"version": 1, "handlers": {"console": {"class": "logging.StreamHandler"}, "file": {"class": "logging.FileHandler", "filename": "logs/general.log"}}, "loggers": {"django": {"handlers": ["console", "file"], "level": "INFO"}}}` |
| `celery.py` | Celery app instantiation and auto‑discovery of tasks. | `app = Celery('project')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(['apps.notifications'])` |
| `wsgi.py` | WSGI entry point for gunicorn. | `application = get_wsgi_application()` |

### 5.5 Docker / Deployment (`docker/`)
| File | Responsibility |
|------|----------------|
| `Dockerfile` | Builds a slim Python image, installs requirements, collects static files, and sets entrypoint to `gunicorn`. |
| `docker-compose.yml` | Defines development services: `web` (Django), `db` (PostgreSQL), `redis` (broker), `celery` (worker), `celery‑beat` (scheduler). |
| `docker-compose.prod.yml` | Production compose adds `nginx` reverse‑proxy and uses gunicorn with multiple workers. |
| `docker/nginx/proxy_params.conf` | Nginx proxy configuration (proxy_set_header, etc.). |

---

## 6. Data Models

### 6.1 `apps/users/models.py`
```python
class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

class OTP(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otps")
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    objects = OTPManager()

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=255, blank=True)
    bio = models.TextField(blank=True)
    avatar_url = models.URLField(blank=True)
```
**Relationships**: `User` 1‑to‑many `OTP`; `User` 1‑to‑1 `Profile`.

### 6.2 `apps/questions/models.py`
```python
class Topic(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

class Question(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, related_name="questions")
    text = models.TextField()
    difficulty = models.CharField(max_length=20, choices=[("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="answers")
    content = models.TextField()
    is_correct = models.BooleanField(default=False)
    answered_at = models.DateTimeField(auto_now_add=True)
```
**Relationships**: `Topic` 1‑to‑many `Question`; `Question` 1‑to‑many `Answer`; `User` 1‑to‑many `Answer`.

### 6.3 `apps/notifications/models.py`
```python
class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=30)  # e.g., "email", "sms"
    payload = JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
```
**Relationship**: `Notification` many‑to‑one `User`.

---

## 7. API Reference (REST)

| Endpoint | HTTP Method | Auth Required? | Request Body (JSON) | Response Body (JSON) | Service / View |
|----------|-------------|----------------|---------------------|----------------------|----------------|
| `/api/auth/login/` | POST | No (email/password) | `{"email": "user@example.com", "password": "secret"}` | `{"token": "<jwt>", "user": {"id": 1, "email": "user@example.com"}}` | `apps/users/services.authenticate` |
| `/api/auth/otp/` | POST | No (email) | `{"email": "user@example.com"}` | `{"detail": "OTP sent"}` | `apps/users/services.send_otp` |
| `/api/auth/otp/verify/` | POST | No | `{"email": "user@example.com", "code": "123456"}` | `{"token": "<jwt>", "detail": "OTP verified"}` | `apps/users/services.verify_otp` |
| `/api/users/me/` | GET | JWT (Bearer) | – | `{"id": 1, "email": "user@example.com", "profile": {...}}` | `apps/users/services.get_current_user` |
| `/api/questions/` | GET | JWT | – (optional query params: `topic`, `difficulty`) | `[{"id": 10, "text": "...", "topic": "Algorithms", "difficulty": "easy"}, …]` | `apps/questions/services.list_questions` |
| `/api/questions/` | POST | JWT (admin) | `{"text": "...", "topic_id": 3, "difficulty": "medium"}` | `{"id": 42, "detail": "Question created"}` | `apps/questions/services.create_question` |
| `/api/questions/<id>/answers/` | POST | JWT | `{"content": "My answer"}` | `{"id": 7, "is_correct": false, "detail": "Answer recorded"}` | `apps/questions/services.submit_answer` |
| `/api/notifications/` | GET | JWT | – | `[{"id": 5, "type": "email", "payload": {...}}]` | `apps/notifications/services.list_notifications` |
| `/api/notifications/dispatch/` | POST | JWT (admin) | `{"user_id": 2, "type": "email", "payload": {"subject": "Interview ready", "body": "..."}}` | `{"detail": "Task queued", "task_id": "abc123"}` | `apps/notifications/tasks.dispatch_notification` |

*All endpoints are wired via DRF viewsets/routers defined in each app's `urls.py` (not shown here).* 

---

## 8. WebSocket Protocol (Channels)

The project uses **Django Channels** with a Redis channel layer. The single WebSocket endpoint is `/ws/notifications/`.

### Connection Flow
1. Client opens a WS connection with a **JWT** query param: `ws://host/ws/notifications/?token=<jwt>`.
2. `apps/notifications/consumers.py` (implementation inferred) validates the token, adds the user to a group `user_<id>`.
3. Server pushes notification events to that group.

### Message Types
| Type | Direction | Payload Schema | Description |
|------|-----------|----------------|-------------|
| `notification` | Server → Client | `{ "type": "notification", "id": int, "payload": object }` | Sent whenever a `Notification` model instance is created and the Celery task marks it `sent_at`.
| `heartbeat` | Server → Client (periodic) | `{ "type": "heartbeat", "timestamp": "ISO8601" }` | Keeps the connection alive.
| `ack` | Client → Server | `{ "type": "ack", "message_id": int }` | Client acknowledges receipt; server may clear pending queue.

*All messages are JSON‑encoded strings.*

---

## 9. Data Flow for Major Use‑Cases

### 9.1 User Login (Password)
```
apps/users/services.authenticate()
   → django.contrib.auth.authenticate()
   → returns User instance
apps/users/services.generate_jwt(user)
   → jwt.encode(payload={"user_id": user.id, "exp": …})
   → returns token → API view → JSON response
```
### 9.2 OTP Generation & Verification
1. **Request OTP** – POST `/api/auth/otp/`
   - `services.send_otp(email)` → `selectors.get_user_by_email()` → creates `OTP` via `OTPManager.create_otp()`.
   - Calls `notifications.tasks.dispatch_notification.delay(notification_id)` to send via email provider.
2. **Verify OTP** – POST `/api/auth/otp/verify/`
   - `services.verify_otp(email, code)` → fetches latest `OTP` (filter `used=False`, `expires_at > now`).
   - Marks OTP as used, generates JWT, returns token.

### 9.3 Question Ingestion
```
manage.py import_questions <source>
   → apps/questions/management/commands/import_questions.py
        → ingestion.pipeline.run(source)
              → adapter = AwesomeAdapter()
              → raw = adapter.fetch()
              → parsed = parse_raw(raw)
              → for each item: apps.questions.services.create_question(data)
```
### 9.4 Submitting an Answer
```
POST /api/questions/<id>/answers/
   → apps/questions/services.submit_answer()
        → creates Answer instance
        → optionally calls scoring logic (score_answer)
        → creates Notification object
        → dispatch_notification.delay(notification.id) (Celery)
```
### 9.5 Real‑time Notification Delivery
1. Celery worker executes `dispatch_notification` → selects provider via `get_provider(type)`.
2. Provider (e.g., `EmailProvider`) sends email; after success, updates `sent_at`.
3. The same task (or a signal) calls `channel_layer.group_send('user_<id>', {"type": "notification", "id": notif.id, "payload": notif.payload})`.
4. Connected WebSocket consumer forwards JSON to the client.

---

## 10. Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Secret key for Django cryptographic signing. | `super-secret-key-123` |
| `DEBUG` | Enables debug mode (only in development). | `True` |
| `DATABASE_URL` | Database connection string (used by `django-environ`). | `postgres://user:pass@db:5432/interviewdb` |
| `REDIS_URL` | URL for Redis broker/backend for Celery and Channels. | `redis://redis:6379/0` |
| `EMAIL_HOST` | SMTP server address for real email provider. | `smtp.sendgrid.net` |
| `EMAIL_HOST_USER` | SMTP username. | `apikey` |
| `EMAIL_HOST_PASSWORD` | SMTP password / API key. | `SG.xxxxx` |
| `SMS_GATEWAY_URL` | Base URL for the external SMS service. | `https://api.twilio.com` |
| `SMS_GATEWAY_TOKEN` | Auth token for SMS gateway. | `abcd1234` |
| `JWT_SECRET` | Secret used to sign JWT access tokens. | `jwt-super-secret` |
| `ALLOWED_HOSTS` | Comma‑separated list of allowed hostnames (prod). | `example.com,www.example.com` |
| `CORS_ALLOWED_ORIGINS` | Origins allowed for CORS. | `https://frontend.example.com` |
| `CELERY_WORKER_CONCURRENCY` | Number of concurrent Celery worker processes. | `4` |
| `STATIC_ROOT` | Directory where `collectstatic` places static files. | `/app/static/` |
| `MEDIA_ROOT` | Directory for user‑uploaded media. | `/app/media/` |

---

## 11. Celery Tasks
| Task | Trigger | Input Parameters | Output / Side‑effects |
|------|---------|------------------|----------------------|
| `dispatch_notification(notification_id: int)` | Called from services when a `Notification` instance is created or manually via API. | `notification_id` (primary key) | Retrieves `Notification`, selects appropriate provider (`EmailProvider` or `SMSProvider`), sends the message, updates `sent_at` timestamp, pushes WS event.
| (potential) `celery.beat` jobs | Defined in `config/celery.py` or via beat schedule (not shown) | – | Periodic cleanup tasks such as expiring OTPs.

---

## 12. Authentication Flow (JWT based)
1. **Login (password)** – User posts email/password to `/api/auth/login/`.
2. `services.authenticate` verifies credentials via Django's auth system.
3. On success, `services.generate_jwt(user)` creates a payload:
   ```json
   {
     "user_id": <int>,
     "exp": <timestamp>,
     "iat": <timestamp>
   }
   ```
   and signs it with `JWT_SECRET` using HS256.
4. Token returned to client; client stores it (e.g., in `localStorage`).
5. **Subsequent requests** – Client includes `Authorization: Bearer <jwt>` header.
6. DRF `JWTAuthentication` class validates the token, extracts `user_id`, and attaches the `User` instance to `request.user`.
7. **OTP login** – Similar flow, but after OTP verification a JWT is issued (steps 2‑4 via `verify_otp`).
8. **WebSocket** – JWT is sent as a query parameter; consumer validates and joins the user‑specific group.

---

## 13. Testing Structure
| Directory | Purpose |
|-----------|---------|
| `apps/users/tests/` | Unit tests for user models, services, authentication flow, OTP lifecycle, and API endpoints. Uses `pytest‑django` and `factory‑boy` factories. |
| `apps/questions/tests/` | Tests for question CRUD, ingestion pipeline, and answer scoring logic. |
| `apps/notifications/tests/` | Tests for each provider (email, sms) and the Celery dispatch task (using `celery‑test` utilities). |

**Testing Patterns**
- **Factory‑boy** for model instance creation.
- **APIClient** from DRF for endpoint testing.
- **Celery `task_always_eager = True`** in test settings to run tasks synchronously.
- **Mocking external services** (email backend, SMS gateway) with `unittest.mock.patch`.
- **Coverage** measured via `coverage run -m pytest`.

---

## 14. Known Issues & Unclear Parts
| Area | Issue / Ambiguity |
|------|-------------------|
| **WebSocket Consumer Implementation** | The actual consumer class (`consumers.py`) is not present in the file list, so exact import path and group naming are inferred. **[UNCLEAR]** |
| **SMS Provider Details** | `apps/notifications/providers/sms.py` contains a stub; integration specifics (API endpoint, request format) are not defined. **[UNCLEAR]** |
| **Celery Beat Scheduled Jobs** | No explicit beat schedule is defined in `config/celery.py`; assumed to exist for OTP cleanup but not visible. **[UNCLEAR]** |
| **Rate‑Limiting / Throttling** | No explicit DRF throttling classes are configured; unknown if rate limiting is intended. **[UNCLEAR]** |
| **Docker Production TLS Config** | `docker-compose.prod.yml` references an external TLS certificate volume, but the paths are not shown. **[UNCLEAR]** |
| **Environment Variable Source** | The project uses `django-environ` (implied) but explicit `env` helper import lines are not present in the shown settings files. **[UNCLEAR]** |

---

## 15. How to Run the Project
### Prerequisites
- **Docker Compose** (v2+) installed.
- **Python 3.11** (if running locally without Docker).
- **PostgreSQL** (or SQLite for quick dev) and **Redis** for broker.

### Local Development (Docker)
```bash
# copy example env and edit values
cp .env.example .env
# start services
docker-compose up --build
# Apply migrations & create superuser
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
# Access API at http://localhost:8000/api/
```
### Running Celery Worker
```bash
docker-compose up -d redis
docker-compose up -d celery   # worker
# optional: start beat for scheduled tasks
docker-compose up -d celery-beat
```
### Without Docker (virtualenv)
```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements/development.txt
# set env vars (DJANGO_*, REDIS_URL, DATABASE_URL, JWT_SECRET, etc.)
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
# start Celery worker in another terminal
celery -A config.celery.app worker --loglevel=info
```
### Common Management Commands
- `python manage.py test` – runs the full test suite.
- `python manage.py import_questions <source>` – launches the ingestion pipeline.
- `python manage.py createsuperuser` – creates an admin user.
- `python manage.py collectstatic` – gathers static assets for production.

---
  6. Interviews App (apps/interviews/)

  File: apps/interviews/models.py
  Responsibility: Core interview domain models: InterviewSession, SessionQuestion, InterviewMessage, UserAnswer. Includes status enums, timing
    fields, and JSON‑metadata for LLM context.
  ────────────────────────────────────────
  File: apps/interviews/consumers.py
  Responsibility: WebSocket consumer (InterviewConsumer). Handles connection auth, routing of client‑to‑server events (start, next_question,
    submit_answer, submit_follow_up) and server‑to‑client events (connected, greeting, question, follow_up, answer_received, evaluating,
    evaluation_done, wrap_up, report_ready, error). Uses Channels groups interview_<uuid>.
  ────────────────────────────────────────
  File: apps/interviews/services.py
  Responsibility: Business‑logic layer: <br>• InterviewSetupService – creates a session, validates active sessions, selects & assigns questions.
    <br>• InterviewConductService – drives the state machine, saves messages, starts interview, asks next question, records answers, manages
    follow‑ups, wraps up. <br>• EvaluationService – builds evaluation context and calls LLMClient.evaluate. <br>• ReportService – aggregates stats,
    calls LLMClient.generate_report_summary, stores final score/report.
  ────────────────────────────────────────
  File: apps/interviews/selectors.py (not shown but referenced)
  Responsibility: Query helpers for sessions, messages, answers, and stats.
  ────────────────────────────────────────
  File: apps/interviews/tasks.py
  Responsibility: Celery tasks: <br>evaluate_answer_task(answer_id) → EvaluationService.evaluate_answer; <br>generate_report_task(session_pk) →
    ReportService.generate_final_report.
  ────────────────────────────────────────
  File: apps/interviews/urls.py
  Responsibility: Routes API endpoints for interview session CRUD and WebSocket handshake (ws/interviews/<uuid>/).
  ────────────────────────────────────────
  File: apps/interviews/routing.py
  Responsibility: Channels routing definition linking the URL pattern to InterviewConsumer.
  ────────────────────────────────────────
  File: apps/interviews/middleware.py
  Responsibility: (Placeholder) middleware for injecting interview‑specific context into requests.
  ────────────────────────────────────────
  File: apps/interviews/tests/…
  Responsibility: Unit tests for models, services, state‑machine transitions, and Celery tasks.
  ────────────────────────────────────────
  File: apps/interviews/admin.py
  Responsibility: Django admin registration for interview models.
  ────────────────────────────────────────
  File: apps/interviews/apps.py
  Responsibility: InterviewsConfig – app config declaration.
  ────────────────────────────────────────
  File: apps/interviews/__init__.py
  Responsibility: Package marker.

  Key points

  - WebSocket endpoint: ws/interviews/<uuid>/ (apps/interviews/consumers.py). <br>Authentication uses the user in the ASGI scope; unauthorized
  connections receive close codes 4001‑4004. <br>Server pushes events via Channels group interview_<uuid>. <br>All messages are JSON strings with a
  top‑level "type" and optional "payload" (see WebSocket protocol section below).
  - State machine lives in InterviewSession.status (SETUP → INTRO → QUESTIONING → DRILLING → WRAP_UP → COMPLETED/ABANDONED). Transitions are
  performed through the service methods, which also log each step.
  - LLM abstraction is accessed via apps.core.llm.client.LLMClient (see next section).

  ---
  7. Core LLM Abstraction (apps/core/llm/)

  ┌───────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │       File        │                                                     Responsibility                                                      │
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │                   │ Central LLM client wrapper. Provides provider‑agnostic factory (ProviderFactory) and high‑level methods:                │
  │ client.py         │ evaluate(context), generate_report_summary(session_data), decide_next_action(...). Instantiates the appropriate         │
  │                   │ provider class (OpenAIProvider, AnthropicProvider, OpenRouterProvider, OllamaProvider) based on Django settings         │
  │                   │ (LLM_PROVIDER, LLM_MODEL).                                                                                              │
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ schemas.py        │ Pydantic models defining structured‑output contracts: EvaluationResult (score, technical_accuracy, strengths,           │
  │                   │ weaknesses, missing_keywords, feedback, suggested_follow_up) and FinalReport (overall summary, stats, etc.).            │
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │                   │ Functions that build the concrete system prompts for each LLM call: <br>• build_evaluation_prompt(...) – assembles      │
  │ prompts.py        │ question, reference answer, criteria, and user answer into a prompt suitable for structured output. <br>•               │
  │                   │ build_report_prompt(session_data) – creates a prompt for the final interview report.                                    │
  ├───────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ agent.py          │                                                                                                                         │
  │ (referenced but   │ Helper to obtain a LangChain‑compatible agent used by LLMClient.decide_next_action.                                     │
  │ not shown)        │                                                                                                                         │
  └───────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  LLM Abstraction Layer Details

  1. Provider Enum (LLMProvider) – enumerates supported back‑ends: openai, anthropic, openrouter, ollama.
  2. Base Provider Interface (BaseLLMProvider) – requires get_chat_model(**kwargs) and get_model_name(). Concrete providers implement these using
  LangChain wrappers (ChatOpenAI, ChatAnthropic, etc.).
  3. Factory (ProviderFactory) – maps enum values to provider classes; can be extended at runtime via ProviderFactory.register(name, cls).
  4. Client (LLMClient) – instantiated with optional provider, model, temperature. If omitted, reads settings.LLM_PROVIDER (defaults to OPENAI) and
  settings.LLM_MODEL. Provides three high‑level entry points:
    - evaluate(context) → calls build_evaluation_prompt, gets a structured LLM response (EvaluationResult).
    - generate_report_summary(session_data) → builds report prompt and returns a structured FinalReport.
    - decide_next_action(...) → delegates to a LangChain agent (used for dynamic interview flow).

  5. Class‑method shortcuts (evaluate_default, generate_default_report_summary) expose a singleton client for quick calls (used throughout
  services).

  All LLM calls are structured‑output; if validation fails LangChain retries automatically, guaranteeing a predictable schema for downstream
  services.

  ---
  8. WebSocket Protocol – Full Message Specification

  All real‑time communication occurs over the Django Channels WebSocket at ws/interviews/<uuid>/. Messages are JSON‑encoded UTF‑8 strings with the
  following top‑level shape:

  {
    "type": "<MessageType>",
    "payload": { … }
  }

  8.1 Client → Server Event Types

  ┌──────────────────┬───────────┬─────────────────────────────────────┬────────────────────────────────────────────────────────────────────────┐
  │       type       │ Direction │           Payload schema            │                              Description                               │
  ├──────────────────┼───────────┼─────────────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ start            │ C→S       │ {} (no payload)                     │ Initiates the interview; moves session from SETUP → INTRO and returns  │
  │                  │           │                                     │ a greeting.                                                            │
  ├──────────────────┼───────────┼─────────────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ next_question    │ C→S       │ {}                                  │ Requests the next interview question; server validates current state   │
  │                  │           │                                     │ and returns a question event or wrap_up if none remain.                │
  ├──────────────────┼───────────┼─────────────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ submit_answer    │ C→S       │ { "answer_text": "string",          │ Submits the user's answer to the current question; triggers async      │
  │                  │           │ "answer_duration": int? }           │ evaluation.                                                            │
  ├──────────────────┼───────────┼─────────────────────────────────────┼────────────────────────────────────────────────────────────────────────┤
  │ submit_follow_up │ C→S       │ { "answer_text": "string" }         │ Submits an answer to a follow‑up question (when in DRILLING state).    │
  └──────────────────┴───────────┴─────────────────────────────────────┴────────────────────────────────────────────────────────────────────────┘

  8.2 Server → Client Event Types

  ┌─────────────────┬─────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────────────┐
  │      type       │                               Payload schema                                │                 Description                 │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │                 │ { "session_uuid": "string", "status": "string", "target_position":          │ Sent immediately after successful WebSocket │
  │ connected       │ "string", "total_questions": int, "current_index": int, "status": "string"  │  handshake.                                 │
  │                 │ }                                                                           │                                             │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ greeting        │ { "content": "string", "turn_number": int }                                 │ Welcome message after start.                │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │                 │ { "content": "string", "turn_number": int, "question_order": int,           │ Delivers the next interview question and    │
  │ question        │ "estimated_time": int, "question_type": "string", "code_template":          │ related metadata.                           │
  │                 │ "string?" }                                                                 │                                             │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ answer_received │ { "answer_id": int, "status": "string" }                                    │ Acknowledges receipt of a user's answer.    │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ evaluating      │ { "message": "string" }                                                     │ Indicates the answer is being processed by  │
  │                 │                                                                             │ the LLM.                                    │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ evaluation_done │ { "answer_id": int, "score": int, "feedback": "string", … }                 │ Result of LLM evaluation (structured        │
  │                 │                                                                             │ output).                                    │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ follow_up       │ { "content": "string", "turn_number": int }                                 │ LLM‑generated follow‑up question.           │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ wrap_up         │ { "content": "string" }                                                     │ Sent when no more questions remain; session │
  │                 │                                                                             │  moves to WRAP_UP.                          │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ report_ready    │ { "report": { "stats": {…}, "summary": "string", "generated_at": "ISO8601"  │ Final interview report generated by         │
  │                 │ } }                                                                         │ ReportService.                              │
  ├─────────────────┼─────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ error           │ { "message": "string" }                                                     │ Any validation or internal error (e.g.,     │
  │                 │                                                                             │ unauthorized action, malformed payload).    │
  └─────────────────┴─────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────────────┘

  All messages are JSON strings; the payload fields correspond directly to model attributes defined in apps/interviews/models.py (e.g.,
  InterviewMessage.message_type, UserAnswer.score, etc.).

  ---
  9. LLM Abstraction Layer – Design Overview

  Component: LLMProvider Enum
  Role: Enumerates supported back‑ends; used in settings (LLM_PROVIDER).
  ────────────────────────────────────────
  Component: BaseLLMProvider (ABC)
  Role: Defines required interface (get_chat_model, get_model_name, provider_name).
  ────────────────────────────────────────
  Component: Concrete Provider Classes (OpenAIProvider, AnthropicProvider, OpenRouterProvider, OllamaProvider)
  Role: Wrap LangChain chat models for each vendor; encapsulate API‑key handling and default model names.
  ────────────────────────────────────────
  Component: ProviderFactory
  Role: Registry → creates provider instances. Extensible via ProviderFactory.register.
  ────────────────────────────────────────
  Component: LLMClient
  Role: High‑level façade used by services: <br>• evaluate(context) – runs build_evaluation_prompt → structured LLM output (EvaluationResult). <br>•

    generate_report_summary(session_data) – runs build_report_prompt → FinalReport. <br>• decide_next_action(...) – delegates to a LangChain agent
    for dynamic interview flow. <br>Instantiated lazily; singleton accessible via class methods.
  ────────────────────────────────────────
  Component: schemas.py
  Role: Pydantic models guaranteeing the shape of LLM responses (evaluation, final report).
  ────────────────────────────────────────
  Component: prompts.py
  Role: Prompt‑construction helpers that embed interview‑specific context (question text, reference answer, criteria, user answer, seniority, target

    position).
  ────────────────────────────────────────
  Component: agent.py (referenced)
  Role: Provides a LangChain “agent” that can decide next actions (e.g., whether to ask a follow‑up).

  Configuration (config/settings/*.py): <br>LLM_PROVIDER = "openai" (or "anthropic", "openrouter", "ollama"). <br>LLM_MODEL = "gpt-4o" (or
  provider‑specific default). <br>These settings drive LLMClient initialization automatically.

  ---
  All references are to exact file paths in the repository (e.g., apps/interviews/consumers.py, apps/core/llm/client.py).


  
*All file references above correspond to the exact paths in the repository (e.g., `apps/users/models.py`, `config/settings/production.py`).* 

---

*End of `project_context.md`.*