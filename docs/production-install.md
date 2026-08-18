# Чистая установка на Debian 13

Этот вариант предназначен для развёртывания нового production-экземпляра WireGuard Telegram Bot с пустой SQLite-базой.

Исходный тестовый сервер можно оставить без изменений как стенд разработки. Если production использует тот же Telegram `BOT_TOKEN`, старый экземпляр бота перед запуском нового необходимо остановить: одновременно два polling-процесса с одним токеном работать не должны.

Если production использует тот же RouterOS и тот же WireGuard interface, также необходимо проверить старые тестовые peers. Новая база начинается с чистого пула адресов и не знает о peers, созданных другим экземпляром бота.

## Что устанавливает install.sh

Установщик рассчитан на Debian 13 и выполняет:

- установку `git`, `python3`, `python3-venv`, `python3-pip`;
- установку `wireguard-tools` (`wg`);
- установку `sqlite3` для диагностики;
- клонирование проекта в `/opt/wireguard-bot`;
- создание `.venv`;
- установку всех Python-зависимостей из `pyproject.toml`;
- создание системного пользователя `wireguard-bot`;
- интерактивное создание `/opt/wireguard-bot/.env`;
- автоматическую генерацию `APP_FERNET_KEY`;
- создание чистой SQLite-базы;
- установку `wireguard-bot.service`;
- включение сервиса в автозагрузку.

Сервис в конце запускается только после отдельного подтверждения.

## Быстрый запуск на новой системе

Войти на Debian 13 под `root` и выполнить:

```bash
apt update
apt install -y git

git clone https://github.com/bagaMann/wireguard-bot.git /opt/wireguard-bot
cd /opt/wireguard-bot
bash scripts/install.sh
```

Установщик запросит:

- Telegram Bot Token;
- Telegram ID администратора;
- адрес и параметры RouterOS API;
- имя WireGuard interface;
- public key WireGuard-сервера;
- внешний WireGuard endpoint;
- клиентскую сеть;
- DNS;
- AllowedIPs;
- PersistentKeepalive;
- лимит QR по умолчанию.

Пароли и Telegram token вводятся без отображения на экране.

## После установки

Проверить unit:

```bash
systemctl status wireguard-bot --no-pager -l
```

Запустить, если при установке запуск был пропущен:

```bash
systemctl start wireguard-bot
```

Логи:

```bash
journalctl -u wireguard-bot -f
```

Последние 100 строк:

```bash
journalctl -u wireguard-bot -n 100 --no-pager
```

Проверить конфигурацию вручную:

```bash
cd /opt/wireguard-bot
runuser -u wireguard-bot -- .venv/bin/python -m bot.cli check-config
```

Проверить чистую базу:

```bash
sqlite3 -header -column /opt/wireguard-bot/data/bot.db 'SELECT * FROM users;'
sqlite3 -header -column /opt/wireguard-bot/data/bot.db 'SELECT * FROM wireguard_configs;'
```

На новой установке обе таблицы должны быть пустыми.

## Обновление production

```bash
cd /opt/wireguard-bot
git pull --ff-only
.venv/bin/python -m pip install -e .
.venv/bin/python -m compileall -q bot
systemctl restart wireguard-bot
systemctl status wireguard-bot --no-pager -l
```

## Важные файлы

Секреты и рабочие данные не находятся в GitHub:

```text
/opt/wireguard-bot/.env
/opt/wireguard-bot/data/bot.db
/opt/wireguard-bot/data/qr/
```

Их необходимо включать в резервное копирование production-сервера.

## Перенос production на другой сервер

Для переноса уже работающего экземпляра недостаточно просто клонировать GitHub. Нужно переносить вместе:

- `.env`;
- `data/bot.db`;
- `data/qr/`.

Особенно важен `APP_FERNET_KEY` из `.env`: приватные WireGuard-ключи в базе зашифрованы этим ключом. Если потерять `APP_FERNET_KEY`, существующие зашифрованные конфигурации восстановить из базы будет нельзя.
