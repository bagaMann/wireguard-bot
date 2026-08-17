# Конфигурация

Все секреты находятся в `.env`.

## Telegram

`BOT_TOKEN` — токен BotFather.

`ADMIN_IDS` — Telegram ID администраторов через запятую.

## RouterOS

`ROUTEROS_HOST` — IP MikroTik.

`ROUTEROS_PORT` — 8728 для API или 8729 для API-SSL.

`ROUTEROS_SSL` — `true`/`false`.

`ROUTEROS_USERNAME` и `ROUTEROS_PASSWORD` — отдельная учётная запись API.

`ROUTEROS_INTERFACE` — WireGuard interface.

## WireGuard

`WG_SERVER_PUBLIC_KEY` — public key WireGuard-интерфейса MikroTik.

`WG_ENDPOINT` — внешний адрес MikroTik и порт WireGuard.

`WG_CLIENT_NETWORK` — пул клиентских адресов.

`WG_DNS` — DNS, который будет записан в клиентский конфиг.

`WG_CLIENT_ALLOWED_IPS` — AllowedIPs клиента.

`WG_CLIENT_KEEPALIVE` — PersistentKeepalive.

`DEFAULT_QR_LIMIT` — лимит нового пользователя после подтверждения.
