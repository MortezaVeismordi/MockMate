# Contributing to MockMate

Thanks for taking the time to contribute! This document explains how to get the project running locally and how to submit changes.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)

---

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Git
- An API key for at least one LLM provider (OpenAI, Anthropic, or OpenRouter)

### Local Setup

```bash
# 1. Fork the repo on GitHub, then clone your fork
git clone https://github.com/your-username/mockmate.git
cd mockmate

# 2. Copy the example env file and fill in your values
cp .env.example .env

# 3. Start all services
docker compose up --build

# 4. Seed the question bank
docker compose exec web python manage.py import_questions devops --limit 30
```

The API will be available at `http://localhost` and interactive docs at `http://localhost/api/schema/swagger-ui/`.

---

## Project Structure

```
mockmate/
├── apps/
│   ├── core/llm/          # LLM provider abstraction — add new providers here
│   ├── interviews/        # WebSocket consumer, session logic, Celery tasks
│   ├── questions/         # Question bank + GitHub ingestion pipeline
│   ├── notifications/     # SMS / email provider abstraction
│   └── users/             # Custom user model, JWT auth, OTP
├── config/settings/       # base / development / production settings
├── docker/                # Dockerfile and nginx config
├── scripts/               # entrypoint.sh, celery-entrypoint.sh
└── requirements/          # Pinned dependencies per environment
```

---

## Development Workflow

### Branching

Always branch off `main`:

```bash
git checkout main
git pull origin main
git checkout -b feat/your-feature-name
# or
git checkout -b fix/your-bug-description
```

Branch naming conventions:

| Prefix | Use for |
|---|---|
| `feat/` | New features |
| `fix/` | Bug fixes |
| `docs/` | Documentation only |
| `refactor/` | Code changes with no behavior change |
| `test/` | Adding or fixing tests |

### Making Changes

Run a shell inside the web container:

```bash
docker compose exec web bash
```

After changing models, create and apply migrations:

```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

### Adding a New LLM Provider

1. Create a new class in `apps/core/llm/` that implements the base provider interface
2. Register it in the provider registry
3. Add the corresponding `*_API_KEY` to `.env.example`
4. Update the `LLM_PROVIDER` choices in the settings docs

---

## Running Tests

```bash
# Run the full test suite
docker compose exec web python manage.py test --verbosity=2

# Run tests for a specific app
docker compose exec web python manage.py test apps.interviews
docker compose exec web python manage.py test apps.users
docker compose exec web python manage.py test apps.questions
```

All tests must pass before opening a pull request.

---

## Code Style

- Follow **PEP 8** for Python code
- Use **docstrings** for public classes and methods
- Keep views thin — business logic belongs in `services.py`
- Add logging for non-trivial operations using the standard `logging` module
- Persian comments inside the codebase are fine — the project has bilingual inline docs

---

## Submitting a Pull Request

1. Make sure all tests pass
2. Update or add docstrings where relevant
3. If you changed any API endpoints, update `README.md` accordingly
4. Push your branch and open a PR against `main`
5. Fill in the PR template — describe what changed and why
6. Link any related issues with `Closes #123`

PRs are reviewed within a few days. Feedback will be left as inline comments on GitHub.

---

## Reporting Bugs

Open an issue and include:

- Steps to reproduce
- Expected behavior
- Actual behavior
- Relevant logs (from `docker compose logs web`)
- Your environment (OS, Docker version)

---

## Suggesting Features

Open an issue with the `enhancement` label. Describe:

- The problem you're trying to solve
- Your proposed solution
- Any alternatives you considered

---

## Questions

If something in the codebase is unclear, open an issue with the `question` label.