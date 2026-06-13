# Changelog

All notable changes to MockMate will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-06-13

Initial public release of MockMate — an AI-powered interview simulator for software engineering positions.

### Added

**Core Interview Engine**
- Real-time WebSocket interview flow via Django Channels + Daphne (ASGI)
- Full session lifecycle: `setup → intro → questioning → drilling → completed`
- Automatic question progression with AI-driven drill-down follow-ups
- Session state management with per-question status tracking

**Authentication & Users**
- OTP-based phone authentication (send, verify, resend)
- JWT access + refresh token system with rotation and blacklisting
- Custom user model with profile fields (skills, experience, job title, avatar)
- Admin endpoints for user management: suspend, unsuspend, ban
- Rate limiting on OTP endpoints (5 requests/hour)

**Question Bank**
- Question model with types: technical, system design, architecture, behavioral, DevOps
- Seniority levels: junior, mid, senior
- Category system with hierarchical parent/child support
- GitHub ingestion pipeline via `import_questions` management command
- REST API trigger for ingestion: `POST /api/v1/questions/admin/ingest/github/`
- Random interview set generation endpoint

**LLM Integration**
- Pluggable provider abstraction layer in `apps/core/llm/`
- Support for OpenAI, Anthropic Claude, and OpenRouter
- Provider and model selection via environment variables (`LLM_PROVIDER`, `LLM_MODEL`)

**Evaluation & Reporting**
- Per-answer AI scoring and feedback via Celery async tasks
- Final session report generation after interview completion
- Report delivered to client over WebSocket (`report_ready` event)
- Admin endpoint to retrigger evaluation: `POST /api/v1/interviews/admin/answers/{id}/retrigger/`

**Infrastructure**
- Full Docker Compose setup: PostgreSQL 15, Redis 7, Daphne, Celery, Celery Beat, Flower, Nginx
- Custom `entrypoint.sh` with exponential backoff health checks for DB and Redis
- Graceful shutdown with signal handling (SIGTERM, SIGINT, SIGHUP)
- Structured JSON logging via Nginx
- Three environment configs: development, production, test
- JWT WebSocket authentication via custom `JWTAuthMiddleware` (query string token)
- Health check endpoint: `GET /health/`
- API documentation via drf-spectacular: `/api/schema/swagger-ui/`

---

## [Unreleased]

- Frontend client (React / Next.js)
- Support for code execution questions
- Interview history and progress tracking dashboard
- Webhook notifications on session completion