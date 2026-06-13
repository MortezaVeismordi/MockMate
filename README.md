# MockMate

> **AI-Powered Interview Simulator** — Open Source · Self-Hosted · Multi-Provider LLM

MockMate is a self-hosted interview simulator that uses AI to conduct realistic technical interviews for software engineering positions. It supports multiple LLM providers (OpenAI, Anthropic, OpenRouter, and more) so you can bring your own API key and run everything on your own infrastructure.

The platform conducts full end-to-end interviews over **WebSocket** — asking questions, drilling down on answers, and producing a scored evaluation report — all in real-time.

---

## Features

**Real-Time Interview Engine**
- Full-duplex WebSocket communication via Django Channels + Daphne (ASGI)
- Streaming AI responses for natural, low-latency conversation
- Automatic question progression, drill-down follow-ups, and session state management

**Multi-Provider LLM Support**
- Pluggable abstraction layer — swap providers with a single env variable
- Supported: OpenAI, Anthropic Claude, OpenRouter (90%+ of public providers)

**Intelligent Question Bank**
- Automated question ingestion from GitHub repositories via management command and REST API
- Questions categorized by type: technical, system design, architecture, behavioral, DevOps
- Seniority-aware filtering: junior / mid / senior

**Evaluation & Reporting**
- AI-generated scoring and feedback after each answer
- Final session report with overall score and per-question breakdown
- Async report generation via Celery task queue

**Production-Ready Infrastructure**
- Full Docker Compose setup: Django, PostgreSQL, Redis, Celery, Nginx, Flower
- JWT authentication with refresh token rotation and blacklisting
- OTP-based phone auth, rate limiting, structured JSON logging

---

## Tech Stack

| Category | Technology |
|---|---|
| Backend | Django 4.2, Django REST Framework, Django Channels |
| ASGI Server | Daphne |
| Database | PostgreSQL 15 |
| Cache / Broker | Redis 7 |
| Task Queue | Celery + django-celery-beat + Flower |
| Auth | JWT via djangorestframework-simplejwt |
| LLM | OpenAI / Anthropic / OpenRouter (configurable) |
| Reverse Proxy | Nginx (HTTP + WebSocket) |
| Containerization | Docker + Docker Compose |
| API Docs | drf-spectacular (OpenAPI 3) |

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- An API key for your preferred LLM provider

### 1. Clone & Configure

```bash
git clone https://github.com/your-username/mockmate.git
cd mockmate
cp .env.example .env
```

Edit `.env` and fill in your values:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key (min 50 chars) |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | PostgreSQL credentials |
| `REDIS_URL` | e.g. `redis://redis:6379/0` |
| `LLM_PROVIDER` | `openai` \| `anthropic` \| `openrouter` |
| `OPENAI_API_KEY` | Your OpenAI key (if using OpenAI) |
| `ANTHROPIC_API_KEY` | Your Anthropic key (if using Anthropic) |
| `OPENROUTER_API_KEY` | Your OpenRouter key (if using OpenRouter) |

### 2. Start Services

```bash
docker compose up --build
```

Starts: PostgreSQL, Redis, Django (Daphne), Celery worker, Celery Beat, Flower (`:5555`), Nginx (`:80`).

### 3. Seed Questions

**Option A — Management command (CLI):**
```bash
docker compose exec web python manage.py import_questions devops
docker compose exec web python manage.py import_questions devops --limit 50
docker compose exec web python manage.py import_questions devops --level senior --path docker
```

**Option B — REST API:**
```http
POST /api/v1/questions/admin/ingest/github/
```

---

## API Reference

### Authentication

MockMate uses OTP-based phone authentication:

```http
POST /api/v1/auth/send-otp/       # Request OTP
POST /api/v1/auth/verify-otp/     # Verify OTP → returns JWT tokens
POST /api/v1/auth/resend-otp/     # Resend OTP
POST /api/v1/auth/refresh-token/  # Refresh access token
POST /api/v1/auth/logout/         # Blacklist refresh token
```

Pass the access token as `Authorization: Bearer <token>` on all REST calls,
and as `?token=<token>` on the WebSocket URL.

---

### User Profile

```http
GET    /api/v1/me/                  # Get profile
POST   /api/v1/me/complete-profile/ # Set name, skills, experience
POST   /api/v1/me/avatar/           # Upload avatar
DELETE /api/v1/me/delete/           # Delete account
```

---

### Interview Sessions

```http
POST   /api/v1/interviews/           # Create session
GET    /api/v1/interviews/           # List sessions
GET    /api/v1/interviews/active/    # Get active session
GET    /api/v1/interviews/stats/     # User interview stats
GET    /api/v1/interviews/{uuid}/    # Session detail
GET    /api/v1/interviews/{uuid}/report/  # Final report
```

**Create session — request body:**
```json
{
    "target_position": "Senior Django Developer",
    "seniority_level": "senior",
    "total_questions": 5,
    "focus_topics": [],
    "job_description": ""
}
```

**Create session — response:**
```json
{
    "success": true,
    "data": {
        "uuid": "2c1a1d1e-5b6d-43ab-9847-2a34af3e7e9e",
        "status": "setup",
        "ws_url": "/ws/interviews/2c1a1d1e-5b6d-43ab-9847-2a34af3e7e9e/"
    }
}
```

---

### WebSocket Interview Flow

```
ws://localhost/ws/interviews/{uuid}/?token={access_token}
```

| Direction | Event | Description |
|---|---|---|
| ← Server | `greeting` | Welcome message, session info |
| → Client | `next_question` | Request next question |
| ← Server | `question` | Question text and metadata |
| → Client | `answer` | Submit your answer |
| ← Server | `evaluation` | AI score and feedback |
| ← Server | `report_ready` | Final score and session complete |

**Start the interview:**
```json
{ "type": "next_question", "payload": {} }
```

---

### Question Bank

```http
GET /api/v1/questions/              # List questions (filterable)
GET /api/v1/questions/{id}/         # Question detail
GET /api/v1/questions/random-set/   # Random interview set
GET /api/v1/questions/categories/   # List categories
```

**Admin endpoints:**
```http
GET/POST   /api/v1/questions/admin/questions/       # List / create
GET/PUT/DELETE /api/v1/questions/admin/questions/{id}/  # Detail / edit / delete
POST       /api/v1/questions/admin/ingest/github/   # Trigger GitHub ingestion
POST       /api/v1/questions/admin/categories/      # Create category
```

---

### Admin Panel

```http
GET    /api/v1/admin/users/                        # List users
GET    /api/v1/admin/users/{id}/                   # User detail
POST   /api/v1/admin/users/{id}/suspend/           # Suspend user
POST   /api/v1/admin/users/{id}/unsuspend/         # Unsuspend user
POST   /api/v1/admin/users/{id}/ban/               # Ban user
GET    /api/v1/admin/otp-history/{user_id}/        # OTP history
GET    /api/v1/admin/stats/                        # Platform stats

GET    /api/v1/interviews/admin/sessions/          # All sessions
GET    /api/v1/interviews/admin/sessions/{uuid}/   # Session detail
GET    /api/v1/interviews/admin/answers/{id}/      # Answer detail
POST   /api/v1/interviews/admin/answers/{id}/retrigger/  # Re-run AI evaluation
```

**Interactive docs:** `http://localhost/api/schema/swagger-ui/`

---

## LLM Configuration

Switch providers without changing any code:

```env
# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o

# Anthropic
LLM_PROVIDER=anthropic
LLM_MODEL=claude-opus-4-6

# OpenRouter
LLM_PROVIDER=openrouter
LLM_MODEL=meta-llama/llama-3.1-70b-instruct
```

---

## Project Structure

```
mockmate/
├── apps/
│   ├── core/llm/          # LLM provider abstraction layer
│   ├── interviews/        # WebSocket consumer, session logic, Celery tasks
│   │   ├── consumers.py   # Django Channels WebSocket consumer
│   │   ├── routing.py     # WebSocket URL routing
│   │   ├── views.py       # REST API views
│   │   └── urls.py        # REST URL patterns
│   ├── questions/         # Question bank + GitHub ingestion
│   │   ├── ingestion/     # Ingestion pipeline and adapters
│   │   └── management/commands/import_questions.py
│   ├── notifications/     # SMS / email provider abstraction
│   └── users/             # Custom user model, JWT auth, OTP
├── config/
│   └── settings/          # base / development / production
├── docker/                # Dockerfile, nginx.conf
├── scripts/               # entrypoint.sh, celery-entrypoint.sh
└── requirements/          # Pinned dependencies per environment
```

---

## Contributing

1. Fork the repository and create a feature branch
2. Run the test suite: `docker compose exec web python manage.py test`
3. Open a pull request with a clear description

Bug reports and feature requests are welcome via GitHub Issues.

---

## License

MockMate is released under the **MIT License**. See [LICENSE](LICENSE) for details.

---

<p align="center">Built with Django Channels · Daphne · Celery · Redis</p>