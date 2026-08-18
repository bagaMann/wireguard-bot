#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/bagaMann/wireguard-bot.git"
INSTALL_DIR="/opt/wireguard-bot"
SERVICE_USER="wireguard-bot"
SERVICE_GROUP="wireguard-bot"
SERVICE_NAME="wireguard-bot.service"

log() {
    printf '\n==> %s\n' "$*"
}

fail() {
    printf '\nERROR: %s\n' "$*" >&2
    exit 1
}

need_root() {
    [[ ${EUID:-$(id -u)} -eq 0 ]] || fail "Запустите установщик от root."
}

check_os() {
    [[ -r /etc/os-release ]] || fail "Не найден /etc/os-release."
    # shellcheck disable=SC1091
    . /etc/os-release
    [[ ${ID:-} == "debian" ]] || fail "Установщик предназначен для Debian."
    if [[ ${VERSION_ID:-} != "13"* ]]; then
        fail "Требуется Debian 13. Обнаружено: ${PRETTY_NAME:-unknown}."
    fi
}

prompt() {
    local var_name=$1
    local text=$2
    local default=${3-}
    local value

    if [[ -n "$default" ]]; then
        read -r -p "$text [$default]: " value
        value=${value:-$default}
    else
        while true; do
            read -r -p "$text: " value
            [[ -n "$value" ]] && break
            printf 'Значение обязательно.\n'
        done
    fi

    printf -v "$var_name" '%s' "$value"
}

prompt_secret() {
    local var_name=$1
    local text=$2
    local value

    while true; do
        read -r -s -p "$text: " value
        printf '\n'
        [[ -n "$value" ]] && break
        printf 'Значение обязательно.\n'
    done

    printf -v "$var_name" '%s' "$value"
}

dotenv_quote() {
    local value=$1
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//\$/\\$}
    value=${value//\`/\\\`}
    printf '"%s"' "$value"
}

write_env() {
    local env_file="$INSTALL_DIR/.env"

    if [[ -f "$env_file" ]]; then
        printf '\nФайл %s уже существует.\n' "$env_file"
        read -r -p "Сохранить существующую конфигурацию? [Y/n]: " keep_env
        if [[ ! ${keep_env:-Y} =~ ^[NnНн]$ ]]; then
            return
        fi
        cp -a "$env_file" "$env_file.backup-$(date +%Y%m%d-%H%M%S)"
    fi

    printf '\nНастройка Telegram и RouterOS. Секретные значения не отображаются.\n\n'

    prompt_secret BOT_TOKEN "BOT_TOKEN Telegram-бота"
    prompt ADMIN_IDS "Telegram ID администратора (несколько через запятую)"

    prompt ROUTEROS_HOST "IP/имя RouterOS" "192.168.11.220"
    prompt ROUTEROS_PORT "Порт RouterOS API" "8728"
    prompt ROUTEROS_SSL "Использовать API-SSL (true/false)" "false"
    prompt ROUTEROS_USERNAME "Пользователь RouterOS API" "wg-bot"
    prompt_secret ROUTEROS_PASSWORD "Пароль RouterOS API"
    prompt ROUTEROS_INTERFACE "WireGuard interface на RouterOS" "wg0"

    prompt WG_SERVER_PUBLIC_KEY "Public key WireGuard-сервера"
    prompt WG_ENDPOINT "Публичный endpoint WireGuard, например vpn.example.com:51820"
    prompt WG_CLIENT_NETWORK "Сеть клиентов" "10.200.0.0/24"
    prompt WG_SERVER_ADDRESS "Адрес WireGuard-сервера" "10.200.0.1/24"
    prompt WG_DNS "DNS для клиентов (пустое значение не поддерживается установщиком)" "10.200.0.1"
    prompt WG_CLIENT_ALLOWED_IPS "AllowedIPs клиентов" "0.0.0.0/0"
    prompt WG_CLIENT_KEEPALIVE "PersistentKeepalive" "25"
    prompt DEFAULT_QR_LIMIT "Лимит QR по умолчанию" "1"

    APP_FERNET_KEY=$(cd "$INSTALL_DIR" && .venv/bin/python -m bot.cli generate-fernet-key)

    umask 027
    {
        printf 'BOT_TOKEN=%s\n' "$(dotenv_quote "$BOT_TOKEN")"
        printf 'ADMIN_IDS=%s\n\n' "$(dotenv_quote "$ADMIN_IDS")"
        printf 'APP_FERNET_KEY=%s\n\n' "$(dotenv_quote "$APP_FERNET_KEY")"
        printf 'DATABASE_PATH=/opt/wireguard-bot/data/bot.db\n'
        printf 'QR_DIR=/opt/wireguard-bot/data/qr\n\n'
        printf 'ROUTEROS_HOST=%s\n' "$(dotenv_quote "$ROUTEROS_HOST")"
        printf 'ROUTEROS_PORT=%s\n' "$(dotenv_quote "$ROUTEROS_PORT")"
        printf 'ROUTEROS_SSL=%s\n' "$(dotenv_quote "$ROUTEROS_SSL")"
        printf 'ROUTEROS_USERNAME=%s\n' "$(dotenv_quote "$ROUTEROS_USERNAME")"
        printf 'ROUTEROS_PASSWORD=%s\n\n' "$(dotenv_quote "$ROUTEROS_PASSWORD")"
        printf 'ROUTEROS_INTERFACE=%s\n\n' "$(dotenv_quote "$ROUTEROS_INTERFACE")"
        printf 'WG_SERVER_PUBLIC_KEY=%s\n' "$(dotenv_quote "$WG_SERVER_PUBLIC_KEY")"
        printf 'WG_ENDPOINT=%s\n' "$(dotenv_quote "$WG_ENDPOINT")"
        printf 'WG_CLIENT_NETWORK=%s\n' "$(dotenv_quote "$WG_CLIENT_NETWORK")"
        printf 'WG_SERVER_ADDRESS=%s\n' "$(dotenv_quote "$WG_SERVER_ADDRESS")"
        printf 'WG_DNS=%s\n' "$(dotenv_quote "$WG_DNS")"
        printf 'WG_CLIENT_ALLOWED_IPS=%s\n' "$(dotenv_quote "$WG_CLIENT_ALLOWED_IPS")"
        printf 'WG_CLIENT_KEEPALIVE=%s\n\n' "$(dotenv_quote "$WG_CLIENT_KEEPALIVE")"
        printf 'DEFAULT_QR_LIMIT=%s\n' "$(dotenv_quote "$DEFAULT_QR_LIMIT")"
    } > "$env_file"
}

install_packages() {
    log "Установка системных зависимостей"
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        ca-certificates \
        git \
        python3 \
        python3-pip \
        python3-venv \
        sqlite3 \
        wireguard-tools
}

install_source() {
    log "Установка исходного кода"

    if [[ -d "$INSTALL_DIR/.git" ]]; then
        git -C "$INSTALL_DIR" fetch --prune origin
        git -C "$INSTALL_DIR" pull --ff-only
        return
    fi

    if [[ -e "$INSTALL_DIR" ]]; then
        if [[ -n $(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null) ]]; then
            fail "$INSTALL_DIR уже существует и не является Git-репозиторием."
        fi
        rmdir "$INSTALL_DIR" || true
    fi

    git clone "$REPO_URL" "$INSTALL_DIR"
}

install_python() {
    log "Создание Python virtualenv и установка зависимостей"
    python3 -m venv "$INSTALL_DIR/.venv"
    "$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
    "$INSTALL_DIR/.venv/bin/python" -m pip install -e "$INSTALL_DIR"
}

create_service_user() {
    log "Создание системного пользователя"
    if ! getent group "$SERVICE_GROUP" >/dev/null; then
        groupadd --system "$SERVICE_GROUP"
    fi
    if ! id "$SERVICE_USER" >/dev/null 2>&1; then
        useradd \
            --system \
            --gid "$SERVICE_GROUP" \
            --home-dir "$INSTALL_DIR" \
            --shell /usr/sbin/nologin \
            "$SERVICE_USER"
    fi
}

prepare_permissions() {
    log "Настройка каталогов и прав"
    mkdir -p "$INSTALL_DIR/data/qr"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/data"
    chmod 750 "$INSTALL_DIR/data" "$INSTALL_DIR/data/qr"

    chown root:"$SERVICE_GROUP" "$INSTALL_DIR/.env"
    chmod 640 "$INSTALL_DIR/.env"
}

init_database() {
    log "Проверка конфигурации и создание чистой базы"
    cd "$INSTALL_DIR"
    runuser -u "$SERVICE_USER" -- .venv/bin/python -m bot.cli check-config
    runuser -u "$SERVICE_USER" -- .venv/bin/python -m bot.cli init-db
}

install_systemd() {
    log "Установка systemd unit"
    install -o root -g root -m 0644 \
        "$INSTALL_DIR/systemd/wireguard-bot.service" \
        "/etc/systemd/system/$SERVICE_NAME"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
}

finish() {
    printf '\n============================================================\n'
    printf 'WireGuard Telegram Bot установлен.\n'
    printf 'Каталог: %s\n' "$INSTALL_DIR"
    printf 'База:    %s/data/bot.db\n' "$INSTALL_DIR"
    printf 'Service: %s\n' "$SERVICE_NAME"
    printf '============================================================\n\n'

    printf 'ВАЖНО: если старый сервер использует тот же BOT_TOKEN, сначала\n'
    printf 'остановите на нём бота. Одновременно два polling-процесса с\n'
    printf 'одним Telegram token запускать нельзя.\n\n'

    printf 'Если новый бот использует тот же RouterOS/WireGuard interface,\n'
    printf 'убедитесь, что тестовые peers старого экземпляра удалены или\n'
    printf 'не пересекаются с пулом адресов новой чистой базы.\n\n'

    read -r -p "Запустить сервис сейчас? [y/N]: " start_now
    if [[ ${start_now:-N} =~ ^[YyДд]$ ]]; then
        systemctl start "$SERVICE_NAME"
        systemctl --no-pager --full status "$SERVICE_NAME" || true
    else
        printf '\nСервис установлен и включён в автозагрузку, но сейчас не запущен.\n'
        printf 'Запуск: systemctl start %s\n' "$SERVICE_NAME"
    fi

    printf '\nЛоги: journalctl -u %s -f\n' "$SERVICE_NAME"
}

main() {
    need_root
    check_os
    install_packages
    install_source
    install_python
    create_service_user
    write_env
    prepare_permissions
    init_database
    install_systemd
    finish
}

main "$@"
