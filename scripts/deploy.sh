#!/usr/bin/env bash
# Author: Oleh Riabtsev
# File: scripts/deploy.sh
# Created: 2026-11-23
# Version: 1.0.0

# Deployment and update script for Mattermost Document Approval Workflow Engine on Ubuntu Linux.
# Supports initial repository setup, fast-forward Git updates, Alembic PostgreSQL migrations,
# Docker Compose orchestration, health verification, and configurable console language (en | de | ru).

set -Eeuo pipefail

REPO_URL="https://github.com/MasterUaKi/mattermost-workflow-engine.git"
DEFAULT_APP_DIR="/opt/mattermost-workflow-engine"
BRANCH="main"
CONSOLE_LANG_OVERRIDE=""
WITH_LOCAL_MATTERMOST="false"
SKIP_GIT="false"

# Resolve target directory automatically if executed from inside an existing clone
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"
if [[ -f "$PARENT_DIR/docker-compose.yml" ]]; then
    APP_DIR="$PARENT_DIR"
else
    APP_DIR="$DEFAULT_APP_DIR"
fi

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --dir <path>               Target installation directory (default: $APP_DIR)
  --branch <name>            Git branch to deploy (default: main)
  --lang <en|de|ru>          Console output language (overrides CONSOLE_LANG in .env)
  --with-local-mattermost    Also start the bundled local Mattermost test container
  --skip-git                 Skip git clone/pull and deploy current local files
  -h, --help                 Show this help message and exit
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)
            APP_DIR="$2"
            shift 2
            ;;
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --lang)
            CONSOLE_LANG_OVERRIDE="${2,,}"
            shift 2
            ;;
        --with-local-mattermost)
            WITH_LOCAL_MATTERMOST="true"
            shift
            ;;
        --skip-git)
            SKIP_GIT="true"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

# Helper to read a key value from .env without executing arbitrary shell code
read_env_value() {
    local env_file="$1"
    local key="$2"
    local default_val="${3:-}"
    if [[ ! -f "$env_file" ]]; then
        printf '%s' "$default_val"
        return
    fi
    local line
    line="$(grep -E "^[[:space:]]*${key}=" "$env_file" | tail -n 1 || true)"
    if [[ -z "$line" ]]; then
        printf '%s' "$default_val"
        return
    fi
    local val="${line#*=}"
    val="${val%\"}"
    val="${val#\"}"
    val="${val%\'}"
    val="${val#\'}"
    printf '%s' "$val"
}

ACTIVE_LANG="en"
if [[ -n "$CONSOLE_LANG_OVERRIDE" && "$CONSOLE_LANG_OVERRIDE" =~ ^(en|de|ru)$ ]]; then
    ACTIVE_LANG="$CONSOLE_LANG_OVERRIDE"
elif [[ -f "$APP_DIR/.env" ]]; then
    ENV_LANG="$(read_env_value "$APP_DIR/.env" "CONSOLE_LANG" "en")"
    ENV_LANG="${ENV_LANG,,}"
    if [[ "$ENV_LANG" =~ ^(en|de|ru)$ ]]; then
        ACTIVE_LANG="$ENV_LANG"
    fi
fi

# Localized console message dictionaries
declare -A MSG_EN=(
    [start]="Starting deployment of Mattermost Workflow Engine in '%s' (branch: %s)..."
    [missing_cmd]="Required command '%s' is not installed. Please install it first."
    [cloning_repo]="Directory '%s' not found. Cloning repository from %s..."
    [updating_repo]="Pulling latest changes from origin/%s..."
    [env_created]="Created '%s' from .env.example. Please configure MATTERMOST_URL, MATTERMOST_BOT_TOKEN, and MATTERMOST_WEBHOOK_SECRET, then re-run this script."
    [placeholder_token]="MATTERMOST_BOT_TOKEN in .env still contains a placeholder value. Update .env before deploying."
    [building_image]="Building Docker image for workflow-engine..."
    [starting_db]="Starting PostgreSQL container and waiting for healthy status..."
    [running_migrations]="Applying Alembic database migrations (alembic upgrade head)..."
    [starting_services]="Starting application containers..."
    [waiting_health]="Waiting for workflow-engine health endpoint at %s..."
    [health_ok]="Service is healthy and responding on %s."
    [health_failed]="Health check timed out. Showing recent workflow-engine logs:"
    [pruning_images]="Cleaning up dangling Docker images..."
    [deploy_done]="Deployment completed successfully."
)

declare -A MSG_DE=(
    [start]="Starte Bereitstellung von Mattermost Workflow Engine in '%s' (Branch: %s)..."
    [missing_cmd]="Erforderlicher Befehl '%s' ist nicht installiert. Bitte zuerst installieren."
    [cloning_repo]="Verzeichnis '%s' nicht gefunden. Klone Repository von %s..."
    [updating_repo]="Rufe aktuelle Änderungen von origin/%s ab..."
    [env_created]="'%s' aus .env.example erstellt. Bitte konfigurieren Sie MATTERMOST_URL, MATTERMOST_BOT_TOKEN und MATTERMOST_WEBHOOK_SECRET und führen Sie das Skript erneut aus."
    [placeholder_token]="MATTERMOST_BOT_TOKEN in .env enthält noch einen Platzhalterwert. Bitte .env vor der Bereitstellung aktualisieren."
    [building_image]="Erstelle Docker-Image für workflow-engine..."
    [starting_db]="Starte PostgreSQL-Container und warte auf Healthy-Status..."
    [running_migrations]="Führe Alembic-Datenbankmigrationen aus (alembic upgrade head)..."
    [starting_services]="Starte Anwendungscontainer..."
    [waiting_health]="Warte auf Health-Endpunkt von workflow-engine unter %s..."
    [health_ok]="Dienst ist aktiv und antwortet unter %s."
    [health_failed]="Zeitüberschreitung bei der Health-Prüfung. Aktuelle Logs von workflow-engine:"
    [pruning_images]="Bereinige ungenutzte Docker-Images..."
    [deploy_done]="Bereitstellung erfolgreich abgeschlossen."
)

declare -A MSG_RU=(
    [start]="Запуск развертывания Mattermost Workflow Engine в '%s' (ветка: %s)..."
    [missing_cmd]="Необходимая утилита '%s' не установлена. Установите её перед запуском."
    [cloning_repo]="Каталог '%s' не найден. Клонирование репозитория из %s..."
    [updating_repo]="Получение последних изменений из origin/%s..."
    [env_created]="Создан файл '%s' из .env.example. Заполните MATTERMOST_URL, MATTERMOST_BOT_TOKEN и MATTERMOST_WEBHOOK_SECRET, затем повторно запустите скрипт."
    [placeholder_token]="Параметр MATTERMOST_BOT_TOKEN в .env всё ещё содержит значение-заглушку. Обновите .env перед запуском."
    [building_image]="Сборка Docker-образа для workflow-engine..."
    [starting_db]="Запуск контейнера PostgreSQL и ожидание готовности..."
    [running_migrations]="Применение миграций базы данных Alembic (alembic upgrade head)..."
    [starting_services]="Запуск контейнеров приложения..."
    [waiting_health]="Ожидание готовности /health сервиса workflow-engine по адресу %s..."
    [health_ok]="Сервис успешно запущен и отвечает по адресу %s."
    [health_failed]="Превышено время ожидания проверки /health. Последние логи workflow-engine:"
    [pruning_images]="Очистка неиспользуемых промежуточных Docker-образов..."
    [deploy_done]="Развертывание успешно завершено."
)

log_msg() {
    local level="$1"
    local key="$2"
    shift 2
    local template=""
    case "$ACTIVE_LANG" in
        de) template="${MSG_DE[$key]:-${MSG_EN[$key]}}" ;;
        ru) template="${MSG_RU[$key]:-${MSG_EN[$key]}}" ;;
        *)  template="${MSG_EN[$key]}" ;;
    esac
    local timestamp
    timestamp="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    # shellcheck disable=SC2059
    printf '[%s] [%s] '"$template"'\n' "$timestamp" "$level" "$@"
}

require_command() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log_msg "ERROR" "missing_cmd" "$cmd"
        exit 1
    fi
}

# 1. Verify required system dependencies
require_command "git"
require_command "docker"
require_command "curl"

if ! docker compose version >/dev/null 2>&1; then
    log_msg "ERROR" "missing_cmd" "docker compose"
    exit 1
fi

log_msg "INFO" "start" "$APP_DIR" "$BRANCH"

# 2. Clone or update repository
if [[ "$SKIP_GIT" != "true" ]]; then
    if [[ ! -d "$APP_DIR/.git" ]]; then
        log_msg "INFO" "cloning_repo" "$APP_DIR" "$REPO_URL"
        mkdir -p "$(dirname "$APP_DIR")"
        git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
    fi

    cd "$APP_DIR"
    # Ignore executable permission bit changes on Linux servers
    git config core.fileMode false
    log_msg "INFO" "updating_repo" "$BRANCH"
    git fetch origin "$BRANCH"
    git checkout "$BRANCH"
    git pull --ff-only origin "$BRANCH"
else
    cd "$APP_DIR"
fi

# 3. Ensure .env file exists and validate critical secrets
ENV_FILE="$APP_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$APP_DIR/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    log_msg "WARN" "env_created" "$ENV_FILE"
    exit 0
fi

# Re-evaluate CONSOLE_LANG after repository clone/update
if [[ -z "$CONSOLE_LANG_OVERRIDE" ]]; then
    ENV_LANG="$(read_env_value "$ENV_FILE" "CONSOLE_LANG" "en")"
    ENV_LANG="${ENV_LANG,,}"
    if [[ "$ENV_LANG" =~ ^(en|de|ru)$ ]]; then
        ACTIVE_LANG="$ENV_LANG"
    fi
fi

BOT_TOKEN="$(read_env_value "$ENV_FILE" "MATTERMOST_BOT_TOKEN" "")"
if [[ -z "$BOT_TOKEN" || "$BOT_TOKEN" == "your_mattermost_bot_access_token_here" || "$BOT_TOKEN" == "replace_with_generated_bot_token" ]]; then
    log_msg "ERROR" "placeholder_token"
    exit 1
fi

# Ensure runtime directories exist
mkdir -p "$APP_DIR/uploads" "$APP_DIR/logs"

# 4. Build Docker image and start PostgreSQL
log_msg "INFO" "building_image"
docker compose build workflow-engine

log_msg "INFO" "starting_db"
docker compose up -d db

# 5. Run Alembic database migrations explicitly
log_msg "INFO" "running_migrations"
docker compose run --rm workflow-engine alembic upgrade head

# 6. Start target application services
log_msg "INFO" "starting_services"
if [[ "$WITH_LOCAL_MATTERMOST" == "true" ]]; then
    docker compose up -d --remove-orphans
else
    docker compose up -d --no-deps workflow-engine
fi

# 7. Verify application health endpoint
APP_PORT="$(read_env_value "$ENV_FILE" "APP_PORT" "8000")"
HEALTH_URL="http://127.0.0.1:${APP_PORT}/health"
log_msg "INFO" "waiting_health" "$HEALTH_URL"

HEALTH_PASSED="false"
for _ in $(seq 1 30); do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
        HEALTH_PASSED="true"
        break
    fi
    sleep 1
done

if [[ "$HEALTH_PASSED" != "true" ]]; then
    log_msg "ERROR" "health_failed"
    docker compose logs --tail=40 workflow-engine
    exit 1
fi

log_msg "INFO" "health_ok" "$HEALTH_URL"

# 8. Prune old unused images and print final container status
log_msg "INFO" "pruning_images"
docker image prune -f >/dev/null 2>&1 || true

docker compose ps
log_msg "INFO" "deploy_done"
