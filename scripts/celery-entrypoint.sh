#!/usr/bin/env bash
# =============================================================================
# celery-entrypoint.sh — AI Interviewer Celery Entry Point
# =============================================================================

set -euo pipefail
IFS=$'\n\t'

# ─── Constants ───────────────────────────────────────────────────────────────
SCRIPT_VERSION="1.0.0"
SCRIPT_NAME="$(basename "$0")"
LOG_PREFIX="[AI-INTERVIEWER]"

# ─── Colors ──────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    RED='\033[0;31m'; YELLOW='\033[1;33m'
    GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
else
    RED=''; YELLOW=''; GREEN=''; BLUE=''; NC=''
fi

# ─── Logging ─────────────────────────────────────────────────────────────────
log()      { echo -e "${BLUE}$(date -u '+%Y-%m-%dT%H:%M:%SZ')${NC} ${LOG_PREFIX} [INFO]    $*" >&1; }
log_warn() { echo -e "${YELLOW}$(date -u '+%Y-%m-%dT%H:%M:%SZ')${NC} ${LOG_PREFIX} [WARNING] $*" >&2; }
log_error(){ echo -e "${RED}$(date -u '+%Y-%m-%dT%H:%M:%SZ')${NC} ${LOG_PREFIX} [ERROR]   $*" >&2; }
log_ok()   { echo -e "${GREEN}$(date -u '+%Y-%m-%dT%H:%M:%SZ')${NC} ${LOG_PREFIX} [OK]      $*" >&1; }

# ─── Defaults ────────────────────────────────────────────────────────────────
DJANGO_ENV="${DJANGO_ENV:-development}"
CELERY_APP="${CELERY_APP:-config.celery}"
CELERY_MODE="${CELERY_MODE:-worker}"
CELERY_QUEUES="${CELERY_QUEUES:-default}"
CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-2}"
CELERY_LOG_LEVEL="${CELERY_LOG_LEVEL:-info}"
DB_MAX_RETRIES="${DB_MAX_RETRIES:-30}"
REDIS_MAX_RETRIES="${REDIS_MAX_RETRIES:-15}"

# ─── Help ────────────────────────────────────────────────────────────────────
show_help() {
    cat <<EOF
Usage: $SCRIPT_NAME [OPTIONS]

Options:
  --help              این پیام
  --mode MODE         worker | beat (default: worker)
  --queues QUEUES     صف‌های Celery با کاما (default: default)
  --concurrency N     تعداد worker (default: 2)
  --dry-run           چک کن ولی اجرا نکن
  --version           نسخه

Environment Variables:
  CELERY_MODE         worker | beat
  CELERY_QUEUES       default,notifications,interviews
  CELERY_CONCURRENCY  تعداد concurrent worker
  CELERY_LOG_LEVEL    debug | info | warning | error
EOF
    exit 0
}

# ─── Parse Arguments ─────────────────────────────────────────────────────────
DRY_RUN=false

for arg in "$@"; do
    case $arg in
        --help)           show_help ;;
        --mode=*)         CELERY_MODE="${arg#*=}" ;;
        --queues=*)       CELERY_QUEUES="${arg#*=}" ;;
        --concurrency=*)  CELERY_CONCURRENCY="${arg#*=}" ;;
        --dry-run)        DRY_RUN=true ;;
        --version)        echo "$SCRIPT_NAME v$SCRIPT_VERSION"; exit 0 ;;
        *)                log_warn "آرگومان ناشناخته: $arg" ;;
    esac
done

# ─── Signal Handling ─────────────────────────────────────────────────────────
MAIN_PID=0

cleanup() {
    local sig="${1:-TERM}"
    log_warn "سیگنال $sig دریافت شد — در حال shutdown graceful..."

    if [ "$MAIN_PID" -ne 0 ] && kill -0 "$MAIN_PID" 2>/dev/null; then
        kill -"$sig" "$MAIN_PID" 2>/dev/null || true
        local timeout=30
        while kill -0 "$MAIN_PID" 2>/dev/null && [ $timeout -gt 0 ]; do
            sleep 1
            ((timeout--))
        done
        if kill -0 "$MAIN_PID" 2>/dev/null; then
            log_warn "پروسه جواب نداد — force kill..."
            kill -KILL "$MAIN_PID" 2>/dev/null || true
        fi
    fi

    log "Cleanup تموم شد."
    exit 0
}

trap 'cleanup TERM' SIGTERM
trap 'cleanup INT'  SIGINT
trap 'cleanup HUP'  SIGHUP

# ─── Validate Environment ────────────────────────────────────────────────────
validate_env() {
    log "در حال اعتبارسنجی متغیرهای محیطی..."

    local required_vars=(
        "SECRET_KEY"
        "DB_NAME"
        "DB_USER"
        "DB_PASSWORD"
        "DB_HOST"
        "DB_PORT"
        "REDIS_URL"
    )

    local missing=()
    for var in "${required_vars[@]}"; do
        if [ -z "${!var:-}" ]; then
            missing+=("$var")
        fi
    done

    if [ ${#missing[@]} -ne 0 ]; then
        log_error "متغیرهای ضروری تعریف نشدن: ${missing[*]}"
        exit 1
    fi

    # validation concurrency
    if ! [[ "$CELERY_CONCURRENCY" =~ ^[0-9]+$ ]] || \
       [ "$CELERY_CONCURRENCY" -lt 1 ] || \
       [ "$CELERY_CONCURRENCY" -gt 32 ]; then
        log_error "CELERY_CONCURRENCY معتبر نیست: $CELERY_CONCURRENCY (باید بین ۱ تا ۳۲ باشه)"
        exit 1
    fi

    # validation mode
    case "$CELERY_MODE" in
        worker|beat) ;;
        *)
            log_error "CELERY_MODE نامعتبر: $CELERY_MODE (worker | beat)"
            exit 1
            ;;
    esac

    # validation log level
    case "$CELERY_LOG_LEVEL" in
        debug|info|warning|error|critical) ;;
        *)
            log_warn "CELERY_LOG_LEVEL نامعتبر، از info استفاده میشه"
            CELERY_LOG_LEVEL="info"
            ;;
    esac

    log_ok "همه متغیرهای محیطی معتبرن"
}

# ─── Wait for Database ───────────────────────────────────────────────────────
wait_for_db() {
    log "در حال انتظار برای PostgreSQL (${DB_HOST}:${DB_PORT})..."

    local retries=0
    local wait_time=1

    until python -c "
import sys, psycopg2, os
try:
    psycopg2.connect(
        dbname=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        host=os.environ['DB_HOST'],
        port=os.environ['DB_PORT'],
        connect_timeout=3
    ).close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
        retries=$((retries + 1))
        if [ "$retries" -ge "$DB_MAX_RETRIES" ]; then
            log_error "دیتابیس بعد از $retries تلاش در دسترس نیست"
            exit 1
        fi
        wait_time=$(( wait_time * 2 > 30 ? 30 : wait_time * 2 ))
        log_warn "تلاش $retries/$DB_MAX_RETRIES — صبر ${wait_time}s..."
        sleep "$wait_time"
    done

    log_ok "PostgreSQL آماده‌ست"
}

# ─── Wait for Redis ───────────────────────────────────────────────────────────
wait_for_redis() {
    log "در حال انتظار برای Redis..."

    local retries=0
    local wait_time=1

    until python -c "
import sys, redis, os
try:
    r = redis.from_url(os.environ['REDIS_URL'], socket_connect_timeout=3)
    r.ping()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
        retries=$((retries + 1))
        if [ "$retries" -ge "$REDIS_MAX_RETRIES" ]; then
            log_error "Redis بعد از $retries تلاش در دسترس نیست"
            exit 1
        fi
        wait_time=$(( wait_time * 2 > 30 ? 30 : wait_time * 2 ))
        log_warn "تلاش $retries/$REDIS_MAX_RETRIES — صبر ${wait_time}s..."
        sleep "$wait_time"
    done

    log_ok "Redis آماده‌ست"
}

# ─── Celery Worker ────────────────────────────────────────────────────────────
start_worker() {
    log "شروع Celery Worker..."
    log "  صف‌ها      : $CELERY_QUEUES"
    log "  Concurrency: $CELERY_CONCURRENCY"
    log "  Log Level  : $CELERY_LOG_LEVEL"

    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY RUN — worker اجرا نمیشه"
        return
    fi

    # Command تمیز و بدون خطاهای parsing
    exec celery -A "$CELERY_APP" worker \
        --queues="$CELERY_QUEUES" \
        --concurrency="$CELERY_CONCURRENCY" \
        --loglevel="$CELERY_LOG_LEVEL" \
        -E \
        --without-mingle \
        --without-heartbeat \
        -Ofair
}

# ─── Celery Beat ──────────────────────────────────────────────────────────────
start_beat() {
    log "شروع Celery Beat Scheduler..."

    # beat نباید چند instance داشته باشه
    if pgrep -f "celery.*beat" > /dev/null 2>&1; then
        log_error "یه instance از Celery Beat داره اجرا میشه!"
        exit 1
    fi

    local schedule_dir="/app/logs"
    mkdir -p "$schedule_dir"

    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY RUN — beat اجرا نمیشه"
        return
    fi

    exec celery -A "$CELERY_APP" beat \
        --loglevel="$CELERY_LOG_LEVEL" \
        --scheduler django_celery_beat.schedulers:DatabaseScheduler \
        --pidfile="" &

    MAIN_PID=$!
    log_ok "Celery Beat با PID $MAIN_PID شروع شد"
    wait "$MAIN_PID"
}

# ─── Main ─────────────────────────────────────────────────────────────────────
main() {
    log "================================================"
    log " AI Interviewer Celery v$SCRIPT_VERSION"
    log " Mode : $CELERY_MODE"
    log " User : $(whoami) (UID: $(id -u))"
    log "================================================"

    validate_env
    wait_for_db
    wait_for_redis

    case "$CELERY_MODE" in
        worker) start_worker ;;
        beat)   start_beat ;;
        *)
            log_error "Mode ناشناخته: $CELERY_MODE"
            exit 1
            ;;
    esac
}

main "$@"