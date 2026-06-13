#!/usr/bin/env bash
# =============================================================================
# entrypoint.sh — AI Interviewer Django Entry Point
# =============================================================================

set -euo pipefail
IFS=$'\n\t'

# ─── Constants ───────────────────────────────────────────────────────────────
readonly SCRIPT_VERSION="1.0.0"
readonly SCRIPT_NAME="$(basename "$0")"
readonly LOG_PREFIX="[AI-INTERVIEWER]"

# ─── Colors (فقط اگه terminal داریم) ─────────────────────────────────────────
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

# ─── Help ────────────────────────────────────────────────────────────────────
show_help() {
    cat <<EOF
Usage: $SCRIPT_NAME [OPTIONS]

Options:
  --help          این پیام رو نشون بده
  --skip-migrate  از اجرای migration صرف نظر کن
  --skip-collect  از collectstatic صرف نظر کن
  --dry-run       همه چیز رو چک کن ولی اجرا نکن
  --version       نسخه اسکریپت رو نشون بده

Modes (از DJANGO_ENV خونده میشه):
  development     migrate + daphne (ASGI)
  production      migrate + collectstatic + daphne (ASGI)
  test            migrate + test runner

EOF
    exit 0
}

# ─── Parse Arguments ─────────────────────────────────────────────────────────
SKIP_MIGRATE=false
SKIP_COLLECT=false
DRY_RUN=false

for arg in "$@"; do
    case $arg in
        --help)         show_help ;;
        --skip-migrate) SKIP_MIGRATE=true ;;
        --skip-collect) SKIP_COLLECT=true ;;
        --dry-run)      DRY_RUN=true ;;
        --version)      echo "$SCRIPT_NAME v$SCRIPT_VERSION"; exit 0 ;;
        *)              log_warn "آرگومان ناشناخته: $arg" ;;
    esac
done

# ─── Signal Handling ─────────────────────────────────────────────────────────
MAIN_PID=0

cleanup() {
    local sig="${1:-TERM}"
    log_warn "سیگنال $sig دریافت شد — در حال shutdown graceful..."

    if [ "$MAIN_PID" -ne 0 ] && kill -0 "$MAIN_PID" 2>/dev/null; then
        log "ارسال سیگنال به پروسه اصلی (PID: $MAIN_PID)..."
        kill -"$sig" "$MAIN_PID" 2>/dev/null || true

        # صبر میکنیم پروسه تموم بشه (max 30s)
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

# ─── Environment Variables ────────────────────────────────────────────────────
DJANGO_ENV="${DJANGO_ENV:-development}"
DB_MAX_RETRIES="${DB_MAX_RETRIES:-30}"
DB_RETRY_INTERVAL="${DB_RETRY_INTERVAL:-2}"
REDIS_MAX_RETRIES="${REDIS_MAX_RETRIES:-15}"

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

    # validation پورت دیتابیس
    if ! [[ "${DB_PORT}" =~ ^[0-9]+$ ]] || \
       [ "${DB_PORT}" -lt 1 ] || [ "${DB_PORT}" -gt 65535 ]; then
        log_error "DB_PORT معتبر نیست: ${DB_PORT}"
        exit 1
    fi

    # validation SECRET_KEY (حداقل ۵۰ کاراکتر)
    if [ ${#SECRET_KEY} -lt 50 ]; then
        log_error "SECRET_KEY خیلی کوتاهه (حداقل ۵۰ کاراکتر)"
        exit 1
    fi

    log_ok "همه متغیرهای محیطی معتبرن"
}

# ─── Directory Setup ──────────────────────────────────────────────────────────
setup_directories() {
    log "در حال ساخت دایرکتوری‌های مورد نیاز..."

    local dirs=("/app/static" "/app/media" "/app/logs")
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            log "دایرکتوری ساخته شد: $dir"
        fi
    done

    # بررسی write permission
    for dir in "${dirs[@]}"; do
        if [ ! -w "$dir" ]; then
            log_error "دسترسی نوشتن به $dir وجود نداره"
            exit 1
        fi
    done

    log_ok "دایرکتوری‌ها آماده‌ان"
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
except Exception as e:
    sys.exit(1)
" 2>/dev/null; do
        retries=$((retries + 1))

        if [ "$retries" -ge "$DB_MAX_RETRIES" ]; then
            log_error "دیتابیس بعد از $retries تلاش در دسترس نیست"
            exit 1
        fi

        # Exponential backoff (max 30s)
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

# ─── Django Setup ─────────────────────────────────────────────────────────────
run_migrations() {
    if [ "$SKIP_MIGRATE" = true ]; then
        log_warn "Migration رد شد (--skip-migrate)"
        return
    fi

    log "در حال اجرای migrations..."
    python manage.py migrate --noinput 2>&1 | \
        while IFS= read -r line; do log "  migrate | $line"; done

    log_ok "Migrations با موفقیت اجرا شدن"
}

run_collectstatic() {
    if [ "$SKIP_COLLECT" = true ] || [ "$DJANGO_ENV" = "development" ]; then
        log_warn "CollectStatic رد شد"
        return
    fi

    log "در حال اجرای collectstatic..."
    python manage.py collectstatic --noinput 2>&1 | \
        while IFS= read -r line; do log "  static | $line"; done

    log_ok "Static files جمع‌آوری شدن"
}

# ─── Pre/Post Hooks ───────────────────────────────────────────────────────────
run_hook() {
    local hook_name="$1"
    local hook_file="/app/scripts/hooks/${hook_name}.sh"

    if [ -f "$hook_file" ] && [ -x "$hook_file" ]; then
        log "در حال اجرای hook: $hook_name"
        bash "$hook_file" || {
            log_error "Hook $hook_name با خطا متوقف شد"
            exit 1
        }
        log_ok "Hook $hook_name با موفقیت اجرا شد"
    fi
}

# ─── Start Application ────────────────────────────────────────────────────────
start_app() {
    # ✅ اصلاح شد: هر دو mode از Daphne (ASGI) استفاده می‌کنن تا WebSocket کار کنه
    local port="${PORT:-8000}"

    case "$DJANGO_ENV" in
        production)
            log "شروع Daphne ASGI — production (port=$port)..."

            if [ "$DRY_RUN" = true ]; then
                log_warn "DRY RUN — اپ اجرا نمیشه"
                return
            fi

            exec daphne \
                -b 0.0.0.0 \
                -p "$port" \
                --access-log - \
                --proxy-headers \
                config.asgi:application
            ;;

        development)
            log "شروع Daphne ASGI — development (port=$port)..."

            if [ "$DRY_RUN" = true ]; then
                log_warn "DRY RUN — اپ اجرا نمیشه"
                return
            fi

            # ✅ -v 2 برای verbose logging در development
            exec daphne \
                -b 0.0.0.0 \
                -p "$port" \
                -v 2 \
                config.asgi:application
            ;;

        test)
            log "در حال اجرای تست‌ها..."
            exec python manage.py test --verbosity=2
            ;;

        *)
            log_error "DJANGO_ENV نامعتبر: $DJANGO_ENV"
            exit 1
            ;;
    esac

    MAIN_PID=$!
    log_ok "اپ با PID $MAIN_PID شروع شد"
    wait "$MAIN_PID"
}

# ─── Clean Sensitive Env Vars ─────────────────────────────────────────────────
clean_sensitive_vars() {
    log "پاک کردن متغیرهای حساس از محیط..."

    if [ "$DJANGO_ENV" = "production" ]; then
        unset DB_PASSWORD
    else
        log_warn "Development mode — متغیرها پاک نشدن"
    fi

    log_ok "متغیرهای حساس پاک شدن"
}

# ─── Main ─────────────────────────────────────────────────────────────────────
main() {
    log "================================================"
    log " AI Interviewer entrypoint v$SCRIPT_VERSION"
    log " Mode: $DJANGO_ENV"
    log " User: $(whoami) (UID: $(id -u))"
    log "================================================"

    validate_env
    setup_directories
    wait_for_db
    wait_for_redis

    run_hook "pre-start"

    run_migrations
    run_collectstatic

    clean_sensitive_vars

    run_hook "post-start"

    start_app
}

main "$@"