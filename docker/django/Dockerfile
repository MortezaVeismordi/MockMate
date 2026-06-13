# ─── Stage 1: Builder ───────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# build dependencies — شامل graphviz برای pygraphviz
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    graphviz \
    graphviz-dev \
    pkg-config \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/

ARG DJANGO_ENV=development

RUN pip install --upgrade pip && \
    pip wheel --wheel-dir /wheels -r requirements/${DJANGO_ENV}.txt

# ─── Stage 2: Runtime ────────────────────────────────────────────
FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# runtime dependencies
# graphviz اینجا هم لازمه چون pygraphviz توی runtime بهش نیاز داره
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    graphviz \
    git \
    && rm -rf /var/lib/apt/lists/*

# ─── Non-root user ───────────────────────────────────────────────
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# wheelها رو از builder میگیریم
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/* && \
    rm -rf /wheels

# کد پروژه
COPY --chown=appuser:appgroup . .

# scripts رو executable میکنیم
RUN chmod +x scripts/entrypoint.sh && \
    chmod +x scripts/celery-entrypoint.sh

# دایرکتوری‌های لازم
RUN mkdir -p /app/static /app/media /app/logs && \
    chown -R appuser:appgroup /app/static /app/media /app/logs

USER appuser

EXPOSE 8000

# start_period رو بیشتر کردیم — Django زمان نیاز داره
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:8000/health/ || exit 1